#!/usr/bin/env python3
"""DS10 主机中继 — 转发目标由从机在回复里指定 (手动输入, 一次一条)。

链路:
  1. 手动输入文本, 主机发给从机1        /master/tx (station_id=slave1)
  2. 从机1 按载荷内容选一个目标站号 dst  由 ds10_relay_responder.py 完成
  3. 主机收到回复, 读出 dst             /master/rx (station_id=slave1)
  4. 主机把业务载荷转发给 dst 指定的从机  /master/tx (station_id=dst)

路由权在从机:
  主机自己不持有转发目标, 只校验 dst 合法 (1..247 且不等于来源站号)。
  dst=0 表示从机要求"回复我但别转发"。新增目标站号只需改从机的路由表,
  主机无需重启或改配置。

线上格式:
  请求  F1 F1 <txn_hi> <txn_lo> <payload...>
  回复  F1 F2 <txn_hi> <txn_lo> <dst> <payload...>
        ^^^^^ 回复用不同魔数
  用不同魔数是必要的: 请求与回复长度重叠, 单靠长度无法区分。沿用同一魔数时,
  旧格式回复(4B头)的载荷首字节会被误读为 dst, 而可见 ASCII(32-126)全在合法
  站号范围(1-247)内 —— 'Hello' 会被静默转发到站号 72。故让格式自描述。

事务配对:
  驱动的 Frame.tx_seq 不会上无线 (on_tx 只把 station_id/function_code/data 组帧),
  所以事务号必须嵌在 data 里。

重试:
  每条最多发 3 次 (1 次 + 2 重试), 收到匹配回复即停。首帧丢失是常态 ——
  无线本身丢帧, 且从机侧应答节点是否就绪主机观测不到 (真实部署中两侧是
  独立 ROS 图, 只靠电台相连), 故重试是协议的一部分, 不是调试开关。

用法:
  # 终端1
  ./start_ds10.sh
  # 终端2 (从机1 侧应答器, 必须先起; 路由表决定转发目标)
  python3 test/ds10_relay_responder.py --route "temp:2,humid:3"
  # 终端3 (本脚本)
  python3 test/ds10_relay_master.py
  python3 test/ds10_relay_master.py --timeout 2.0      # 链路远/慢时放宽超时
  python3 test/ds10_relay_master.py --retries 0        # 关掉重试, 看裸链路首发成功率
"""

import argparse
import sys
import threading
import time

try:
    import rclpy
    from ds10_interfaces.msg import Frame
    from rclpy.logging import LoggingSeverity
    from rclpy.node import Node
except (ModuleNotFoundError, ImportError) as e:
    sys.exit(
        f"错误: 无法导入 ROS 2 模块 ({e}) —— 请先 source 环境:\n"
        "  source /opt/ros/humble/setup.bash\n"
        "  source install/setup.bash\n"
        "(需在 ~/DS10_Modbus 目录下, 且已 colcon build)"
    )

MARKER = b"\xF1\xF1"        # 请求魔数
REPLY_MARKER = b"\xF1\xF2"  # 回复魔数 (含 dst)
HDR_LEN = 4                 # 请求头: 魔数(2) + txn(2)
REPLY_HDR_LEN = 5           # 回复头: 魔数(2) + txn(2) + dst(1)
FUNC_TEXT = 0x10            # 文本数据功能码, 与监控脚本约定一致

NO_FORWARD = 0
MIN_STATION = 1
MAX_STATION = 247

# 驱动单帧上限 4095B = station+fc(2) + data + CRC(2), 故 data <= 4091B。
MAX_DATA = 4091
MAX_TEXT = MAX_DATA - HDR_LEN


def try_decode(payload):
    """把载荷还原成可读形式, 失败则 hex 摘要。"""
    raw = bytes(payload)
    try:
        return repr(raw.decode("utf-8"))
    except UnicodeDecodeError:
        if len(raw) <= 32:
            return "hex:" + raw.hex(" ")
        return "hex:" + raw[:32].hex(" ") + f"...({len(raw)}B)"


class RelayMaster(Node):
    """主机侧中继: 发请求给从机1, 按回复里的 dst 转发。

    一次只跑一个事务 (手动输入天然串行), 故用单个 pending 事务号即可,
    不需要事务表。
    """

    def __init__(self, timeout, slave1):
        super().__init__("ds10_relay_master")
        self._timeout = timeout
        self._slave1 = slave1
        self._tx_pub = self.create_publisher(Frame, "/master/tx", 10)
        self.create_subscription(Frame, "/master/rx", self._on_rx, 10)

        self._lock = threading.Lock()
        self._txn = 0
        self._pending = None      # 等待中的事务号, None = 空闲
        self._sent_text = None    # 本次发出的原文, 用于逐字节比对
        self._t0 = None
        self._done = threading.Event()
        self._reply = None        # (payload, dst, rtt, 转发是否成功)

        self._stats = {"total": 0, "ok": 0, "failed": 0, "retried": 0,
                       "timeout": 0, "mismatch": 0, "ignored": 0,
                       "no_forward": 0, "bad_dst": 0}

    # ---- 接收 ----

    def _on_rx(self, msg):
        """/master/rx 回调: 站号与事务号都匹配才按 dst 转发。

        站号过滤很关键 —— 若别的从机也在上报, 不过滤会把无关数据当回复。
        丢弃分支一律 debug 级: 空闲时收帧、事务号过期都是正常现象
        (无线重传、上一轮的迟到回复), 不是错误。
        """
        if msg.station_id != self._slave1:
            self._stats["ignored"] += 1
            self.get_logger().debug(
                f"忽略来自从机{msg.station_id} 的帧 (只等从机{self._slave1})")
            return

        data = bytes(msg.data)
        with self._lock:
            pending = self._pending
            t0 = self._t0

        if pending is None:
            self._stats["ignored"] += 1
            self.get_logger().debug("空闲中收到帧, 丢弃 (无等待中的事务)")
            return

        # 回复必须是回复格式 (F1 F2)。收到请求格式说明对端版本不匹配,
        # 单独计数而不是当成 dst=0, 让版本问题可见。
        if len(data) < REPLY_HDR_LEN or data[:2] != REPLY_MARKER:
            self._stats["bad_dst"] += 1
            self.get_logger().warn(
                "回复不是回复格式 (缺 F1 F2 + dst), 对端可能是旧版本; 不转发")
            return

        got_txn = (data[2] << 8) | data[3]
        if got_txn != pending:
            self._stats["ignored"] += 1
            self.get_logger().debug(
                f"事务号不匹配 (期望 {pending}, 收到 {got_txn}), 丢弃")
            return

        dst = data[4]
        payload = data[REPLY_HDR_LEN:]
        rtt = (time.monotonic() - t0) * 1000.0

        print(f"  << [2] 从机{self._slave1} 回复 [{len(payload)}B] "
              f"txn={got_txn} dst={dst}  往返 {rtt:.1f}ms")

        ok = self._forward(dst, payload, msg.function_code)

        with self._lock:
            self._reply = (payload, dst, rtt, ok)
            self._pending = None
        self._done.set()

    def _forward(self, dst, payload, function_code):
        """按从机指定的 dst 转发业务载荷 (事务头是主机↔从机1 的账, 不带走)。"""
        if dst == NO_FORWARD:
            self._stats["no_forward"] += 1
            print("  -- [3] 从机要求不转发 (dst=0)")
            return True     # 这是从机的合法选择, 不算失败

        if not MIN_STATION <= dst <= MAX_STATION:
            self._stats["bad_dst"] += 1
            print(f"  !! [3] dst={dst} 超出合法站号 1..247, 不转发")
            return False
        if dst == self._slave1:
            # 转回给应答者会让它自己的回复看起来像新回复, 中继会自己追自己
            self._stats["bad_dst"] += 1
            print(f"  !! [3] dst={dst} 就是来源站号, 拒绝回环转发")
            return False
        if len(payload) > MAX_DATA:
            print(f"  !! [3] 载荷 {len(payload)}B 超过单帧上限 {MAX_DATA}B, 不转发")
            return False

        out = Frame()
        out.station_id = dst
        out.function_code = function_code
        out.data = list(payload)
        self._tx_pub.publish(out)
        print(f"  >> [3] 主机 -> 从机{dst} 转发 [{len(payload)}B] (从机指定的目标)")
        return True

    # ---- 发起事务 ----

    def run_once(self, text, retries=2):
        """跑一次完整事务 (含重试), 返回 True 表示成功走完。"""
        payload = text.encode("utf-8")
        if len(payload) > MAX_TEXT:
            print(f"  !! 文本 {len(payload)}B 超限, 最大 {MAX_TEXT}B "
                  f"(单帧 4095B 减去帧头/CRC/事务头)")
            return False

        self._stats["total"] += 1
        for attempt in range(1, retries + 2):
            if attempt > 1:
                self._stats["retried"] += 1
                print(f"  .. 重试第 {attempt - 1} 次")
            if self._attempt(payload, text):
                self._stats["ok"] += 1
                return True
        self._stats["failed"] += 1
        print(f"  !! {retries + 1} 次尝试均失败")
        print("     检查: ds10_relay_responder.py 是否在跑、DS10 配对/信道/RUN 档、")
        print("           tail -f /tmp/ds10_slave1.log")
        return False

    def _attempt(self, payload, text):
        """单次尝试: 发请求 → 等回复 → 按 dst 转发。返回是否成功。"""
        with self._lock:
            self._txn = (self._txn + 1) & 0xFFFF
            txn = self._txn
            self._pending = txn
            self._sent_text = payload
            self._reply = None
            self._t0 = time.monotonic()
        self._done.clear()

        data = MARKER + bytes(((txn >> 8) & 0xFF, txn & 0xFF)) + payload
        msg = Frame()
        msg.station_id = self._slave1
        msg.function_code = FUNC_TEXT
        msg.data = list(data)
        self._tx_pub.publish(msg)
        print(f"  >> [1] 主机 -> 从机{self._slave1} [{len(data)}B] "
              f"txn={txn} {text!r}")

        if not self._done.wait(self._timeout):
            with self._lock:
                self._pending = None
            self._stats["timeout"] += 1
            print(f"  !! 超时 {self._timeout:.1f}s 未收到从机{self._slave1} 回复")
            return False

        with self._lock:
            reply_payload, dst, rtt, fwd_ok = self._reply
            sent = self._sent_text

        # 是否与请求逐字节相同, 只是信息, 不是成败判据: 应答器可能原样回显(回车),
        # 也可能人工打了自定义回复。二者都合法, 中继的职责是"收到回复并按 dst 转发"。
        # 只有在回显模式下不一致才提示可能丢字节/串帧。
        if reply_payload == sent:
            print(f"  == 回复与请求一致(回显) ({len(sent)}B)")
        else:
            self._stats["mismatch"] += 1
            print(f"  ~~ 回复与请求不同(自定义回复) 请求 {len(sent)}B / "
                  f"回复 {len(reply_payload)}B: {try_decode(reply_payload)}")

        if not fwd_ok:
            return False
        print(f"  ✓ 完成, 端到端 {rtt:.1f}ms")
        return True

    def print_stats(self):
        s = self._stats
        print(f"\n统计: 共 {s['total']} 条 | 成功 {s['ok']} | 失败 {s['failed']} | "
              f"重试 {s['retried']} 次 | 超时 {s['timeout']} 次 | "
              f"自定义回复 {s['mismatch']} 次")
        if s["no_forward"]:
            print(f"      从机要求不转发 (dst=0) {s['no_forward']} 次")
        if s["bad_dst"]:
            print(f"      dst 非法/格式不符 {s['bad_dst']} 次")
        if s["ignored"]:
            # 丢弃数不为 0 时才提, 但一定要提 —— 静默丢帧会掩盖重复应答器、
            # 无线重传、超时标定过紧等真实问题。
            print(f"      另丢弃无关/过期帧 {s['ignored']} 个 "
                  f"(正常现象; 数量异常大时加 --debug 看原因)")


def parse_args():
    ap = argparse.ArgumentParser(
        description="DS10 主机中继 (转发目标由从机在回复里指定)")
    ap.add_argument("-t", "--timeout", type=float, default=1.5,
                    help="等回复的超时秒数 (默认 1.5, 按实测最坏 764ms 留余量)")
    ap.add_argument("-r", "--retries", type=int, default=2,
                    help="超时后的重试次数, 0=不重试 (默认 2)")
    ap.add_argument("--slave1", type=int, default=1,
                    help="被请求的从机站号 (默认 1)")
    ap.add_argument("--debug", action="store_true",
                    help="打印被丢弃帧的原因 (排查重复应答/超时标定用)")
    return ap.parse_args()


BANNER = """
==========================================
DS10 三跳中继测试 (手动输入, 一次一条)
==========================================
链路: 手输文本 -> 从机1 -> 从机1 按内容选 dst -> 主机 -> 转发给 dst
输入文本回车即发送, 空行或 Ctrl-D/Ctrl-C 退出。
"""


def wait_for_driver(node, timeout=10.0):
    """等 /master/tx 出现订阅者 (驱动或桥) 再返回。

    固定 sleep 不可靠: DDS 发现耗时不定, 抢跑时第一帧会发进虚空, 表现为
    莫名其妙的超时。这里轮询到发现完成为止, 返回 False 表示确实没人订阅。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if node.count_subscribers("/master/tx") > 0:
            return True
        time.sleep(0.2)
    return False


def main():
    args = parse_args()
    rclpy.init()
    node = RelayMaster(args.timeout, args.slave1)
    if args.debug:
        node.get_logger().set_level(LoggingSeverity.DEBUG)

    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()

    print("等待驱动节点上线...")
    if not wait_for_driver(node):
        print("\n警告: /master/tx 始终没有订阅者 —— 驱动节点似乎没在运行。")
        print("      请先在另一个终端执行 ./start_ds10.sh")
        print("      (仍可继续, 但发出的帧不会到任何地方)\n")

    print(BANNER)
    try:
        while True:
            try:
                text = input("文本> ").strip()
            except EOFError:
                break
            if not text:
                break
            print()
            node.run_once(text, retries=args.retries)
            print()
    except KeyboardInterrupt:
        pass
    finally:
        node.print_stats()
        print("退出中...")
        # 先 shutdown 让 spin 退出, 再 join, 最后 destroy_node。
        # 顺序颠倒会在 spin 线程仍持有 node 时销毁它, 触发 C++ 层 abort
        # ("terminate called without an active exception")。
        rclpy.shutdown()
        spin.join(timeout=2.0)
        node.destroy_node()
    return 0


if __name__ == "__main__":
    sys.exit(main())
