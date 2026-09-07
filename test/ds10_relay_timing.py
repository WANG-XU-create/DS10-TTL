#!/usr/bin/env python3
"""DS10 三跳中继端到端耗时测试 (自动, 固定收发内容)。

三台 DS10 挂同一台 Jetson, 本脚本同时扮演三个角色, 但每一跳仍真实过无线
(经各自的驱动), 所以测出的是真实往返耗时:

  [t0] 主机 --请求--> 从机1        "上海赛索德智能科技有限公司位于上海市虹口"
       下行无线, 到 /slave1/rx
  [  ] 从机1 识别转发请求 --回复--> 主机  "好的，已收到贵公司准确地址上海虹口区四川北路"
       (dst=2, 即请从主机转发给从机2)
       上行无线, 到 /master/rx
  [  ] 主机 --转发--> 从机2         (原样转发回复载荷)
       下行无线, 到 /slave2/rx
  [t1] 从机2 收到 -> 总耗时 = t1 - t0

脚本记录每一跳与总耗时。因为三个角色都在本脚本内, 无需另起应答器/中继节点。

前置: 只起驱动, 不要跑 start_relay.sh 或单独的应答器/中继 (会与本脚本抢角色):
  ./start_ds10.sh

用法:
  source /opt/ros/humble/setup.bash && source install/setup.bash
  python3 test/ds10_relay_timing.py
  python3 test/ds10_relay_timing.py --count 20          # 跑 20 次出统计
  python3 test/ds10_relay_timing.py --count 20 --interval 0.3
"""

import argparse
import statistics
import sys
import threading
import time

try:
    import rclpy
    from ds10_interfaces.msg import Frame
    from rclpy.node import Node
except (ModuleNotFoundError, ImportError) as e:
    sys.exit(
        f"错误: 无法导入 ROS 2 模块 ({e}) —— 请先 source 环境:\n"
        "  source /opt/ros/humble/setup.bash\n"
        "  source install/setup.bash\n"
        "(需在 ~/DS10_Modbus 目录下, 且已 colcon build)"
    )

REQUEST_TEXT = "上海赛索德智能科技有限公司位于上海市虹口"
REPLY_TEXT = "好的，已收到贵公司准确地址上海虹口区四川北路"
FORWARD_DST = 2            # 从机1 要求主机把回复转发给站号2
SLAVE1_ID = 1

MARKER = b"\xF1\xF1"        # 请求魔数
REPLY_MARKER = b"\xF1\xF2"  # 回复魔数 (含 dst)
HDR_LEN = 4                 # 请求头: 魔数(2) + txn(2)
REPLY_HDR_LEN = 5           # 回复头: 魔数(2) + txn(2) + dst(1)


class TimingTest(Node):
    """一次事务串起三跳, 记录各段时间戳。单事务串行, 用一个 txn 即可。"""

    def __init__(self):
        super().__init__("ds10_relay_timing")
        self._master_tx = self.create_publisher(Frame, "/master/tx", 10)
        self._slave1_tx = self.create_publisher(Frame, "/slave1/tx", 10)
        self.create_subscription(Frame, "/slave1/rx", self._on_slave1_rx, 10)
        self.create_subscription(Frame, "/master/rx", self._on_master_rx, 10)
        self.create_subscription(Frame, "/slave2/rx", self._on_slave2_rx, 10)

        self._reply_bytes = REPLY_TEXT.encode("utf-8")
        self._lock = threading.Lock()
        self._txn = 0
        self._pending = None
        self._expect_slave2 = False
        self._t = {}                 # 各阶段时间戳 (time.monotonic)
        self._done = threading.Event()

    # --- 从机1 侧: 收到请求, 识别转发请求, 回复 ---
    def _on_slave1_rx(self, msg):
        data = bytes(msg.data)
        if len(data) < HDR_LEN or data[:2] != MARKER:
            return
        txn = (data[2] << 8) | data[3]
        with self._lock:
            if txn != self._pending:
                return
            self._t["req_recv"] = time.monotonic()      # 下行到达从机1
            # 从机1 决定: 回复固定内容, 并请求转发给站号 FORWARD_DST
            out = Frame()
            out.function_code = msg.function_code
            out.data = list(
                REPLY_MARKER + bytes(((txn >> 8) & 0xFF, txn & 0xFF, FORWARD_DST))
                + self._reply_bytes)
            self._slave1_tx.publish(out)
            self._t["reply_sent"] = time.monotonic()

    # --- 主机侧: 收到从机1 回复, 读 dst, 转发 ---
    def _on_master_rx(self, msg):
        if msg.station_id != SLAVE1_ID:
            return
        data = bytes(msg.data)
        if len(data) < REPLY_HDR_LEN or data[:2] != REPLY_MARKER:
            return
        txn = (data[2] << 8) | data[3]
        with self._lock:
            if txn != self._pending:
                return
            self._t["reply_recv"] = time.monotonic()    # 上行到达主机
            dst = data[4]
            payload = data[REPLY_HDR_LEN:]
            out = Frame()
            out.station_id = dst
            out.function_code = msg.function_code
            out.data = list(payload)                    # 转发只带业务载荷
            self._master_tx.publish(out)
            self._t["fwd_sent"] = time.monotonic()
            self._expect_slave2 = True

    # --- 从机2 侧: 收到转发, 事务结束 ---
    def _on_slave2_rx(self, msg):
        with self._lock:
            if not self._expect_slave2:
                return
            if bytes(msg.data) != self._reply_bytes:
                return                                  # 不是本次转发的内容
            self._t["fwd_recv"] = time.monotonic()      # 转发到达从机2 = 终点
            self._expect_slave2 = False
        self._done.set()

    def run_once(self, timeout):
        """跑一次完整三跳, 返回时间戳字典或 None(超时)。"""
        with self._lock:
            self._txn = (self._txn + 1) & 0xFFFF
            txn = self._txn
            self._pending = txn
            self._expect_slave2 = False
            self._t = {}
            self._t["req_sent"] = time.monotonic()      # t0
        self._done.clear()

        payload = REQUEST_TEXT.encode("utf-8")
        msg = Frame()
        msg.station_id = SLAVE1_ID
        msg.function_code = 0x10
        msg.data = list(MARKER + bytes(((txn >> 8) & 0xFF, txn & 0xFF)) + payload)
        self._master_tx.publish(msg)

        ok = self._done.wait(timeout)
        with self._lock:
            self._pending = None
            t = dict(self._t)
        return t if ok else t     # 超时也返回已到达的阶段, 便于定位卡在哪跳

    def wait_ready(self, timeout=10.0):
        """等三个驱动都订阅上各自的 tx 话题。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if (self.count_subscribers("/master/tx") > 0 and
                    self.count_subscribers("/slave1/tx") > 0):
                return True
            time.sleep(0.2)
        return False

    def conflict_present(self):
        """本脚本要独占三个角色; 若 /master/tx 或 /slave1/tx 已有别的发布者, 说明
        还跑着中继/应答器, 会抢角色。count_publishers 含自身, >1 即有他人。"""
        return (self.count_publishers("/master/tx") > 1 or
                self.count_publishers("/slave1/tx") > 1)


def fmt_ms(t, a, b):
    """两个阶段的时间差(ms), 缺任一阶段则返回占位。"""
    if a in t and b in t:
        return f"{(t[b] - t[a]) * 1000:.1f}ms"
    return "—(未到达)"


def report_one(t):
    """打印一次事务的分段耗时。返回总耗时(ms)或 None。"""
    print(f"  [1] 下行  主机 -> 从机1        {fmt_ms(t, 'req_sent', 'req_recv')}")
    print(f"  [2] 从机1 处理(识别+组回复)    {fmt_ms(t, 'req_recv', 'reply_sent')}")
    print(f"  [3] 上行  从机1 -> 主机        {fmt_ms(t, 'reply_sent', 'reply_recv')}")
    print(f"  [4] 主机  处理(读 dst+转发)    {fmt_ms(t, 'reply_recv', 'fwd_sent')}")
    print(f"  [5] 下行  主机 -> 从机2(转发)  {fmt_ms(t, 'fwd_sent', 'fwd_recv')}")
    if "req_sent" in t and "fwd_recv" in t:
        total = (t["fwd_recv"] - t["req_sent"]) * 1000
        print(f"  === 总耗时 (从机2 收到)        {total:.1f}ms ===")
        return total
    # 定位卡在哪一跳
    reached = [k for k in ("req_sent", "req_recv", "reply_sent",
                           "reply_recv", "fwd_sent", "fwd_recv") if k in t]
    print(f"  !! 未走完, 最远到达阶段: {reached[-1] if reached else '无'}")
    return None


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 三跳中继耗时测试")
    ap.add_argument("-n", "--count", type=int, default=1, help="事务次数 (默认 1)")
    ap.add_argument("-i", "--interval", type=float, default=0.5,
                    help="每次之间的间隔秒数 (默认 0.5)")
    ap.add_argument("-t", "--timeout", type=float, default=5.0,
                    help="单次事务超时秒数 (默认 5.0)")
    return ap.parse_args()


def main():
    args = parse_args()
    rclpy.init()
    node = TimingTest()
    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()

    print("等待三个驱动就绪...")
    if not node.wait_ready():
        print("\n警告: /master/tx 或 /slave1/tx 没有订阅者 —— 驱动似乎没起全。")
        print("      请先在另一个终端执行 ./start_ds10.sh\n")
    time.sleep(0.5)
    if node.conflict_present():
        print("\n警告: 检测到 /master/tx 或 /slave1/tx 上有别的发布者 ——")
        print("      多半是 start_relay.sh 的中继/应答器在跑, 会与本脚本抢角色。")
        print("      耗时测试请只用 ./start_ds10.sh (只起驱动)。\n")

    print("=" * 52)
    print("DS10 三跳中继耗时测试")
    print(f"  请求: {REQUEST_TEXT!r}")
    print(f"        ({len(REQUEST_TEXT.encode('utf-8'))}B, +4B 头)")
    print(f"  回复: {REPLY_TEXT!r}")
    print(f"        ({len(REPLY_TEXT.encode('utf-8'))}B, +5B 头, dst={FORWARD_DST})")
    print("=" * 52)

    totals = []
    failures = 0
    try:
        for i in range(args.count):
            print(f"\n--- 第 {i + 1}/{args.count} 次 ---")
            t = node.run_once(args.timeout)
            total = report_one(t)
            if total is None:
                failures += 1
            else:
                totals.append(total)
            if i + 1 < args.count and args.interval > 0:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n中断。")
    finally:
        if args.count > 1:
            print("\n" + "=" * 52)
            print(f"汇总: 成功 {len(totals)}/{args.count}  失败 {failures}")
            if totals:
                print(f"  总耗时 min={min(totals):.1f}  "
                      f"p50={statistics.median(totals):.1f}  "
                      f"mean={statistics.mean(totals):.1f}  "
                      f"max={max(totals):.1f}  (ms)")
            print("=" * 52)
        rclpy.shutdown()
        spin.join(timeout=2.0)
        node.destroy_node()
    return 0


if __name__ == "__main__":
    sys.exit(main())
