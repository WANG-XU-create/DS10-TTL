#!/usr/bin/env python3
"""DS10 从机1 交互式应答器 —— 人工打回复 (含转发目标 dst)。

与自动应答器 (ds10_relay_responder.py, 按 route_map 自动选 dst) 不同: 本脚本把
「回复什么内容、转发给谁」交给你手动决定, 用于人在环的手动测试。

工作方式:
  订阅 /slave1/rx, 收到主机请求后打印出来; 你在本终端敲入回复内容和目标站号 dst,
  脚本组回复帧 (F1 F2 + txn + dst + payload) 发到 /slave1/tx。主机中继收到后按
  dst 转发。

配套 (三终端):
  终端1  ./start_ds10.sh                                     # 只起驱动, 不要用 start_relay.sh
  终端2  python3 test/ds10_relay_master.py --timeout 60 --retries 0   # 主机: 你敲请求
  终端3  python3 test/ds10_relay_responder_interactive.py            # 从机1: 你敲回复(本脚本)

  为什么主机要 --timeout 60 --retries 0: 人工打回复耗时远超默认 1.5s, 否则主机会
  超时重发, 你会看到同一 txn 反复到达。

线上格式 (与 C++ 包/自动脚本一致):
  请求  F1 F1 <txn_hi> <txn_lo> <payload...>
  回复  F1 F2 <txn_hi> <txn_lo> <dst> <payload...>
  回复用不同魔数 F1 F2 是必要的: 与请求长度重叠时靠魔数区分, 否则载荷首字节会被
  主机误读成 dst (可见 ASCII 全在合法站号范围内, 会静默错投)。

用法:
  python3 test/ds10_relay_responder_interactive.py
  python3 test/ds10_relay_responder_interactive.py --default-dst 2
  python3 test/ds10_relay_responder_interactive.py --tx-topic /slave1/tx --rx-topic /slave1/rx
"""

import argparse
import queue
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

MARKER = b"\xF1\xF1"        # 请求魔数
REPLY_MARKER = b"\xF1\xF2"  # 回复魔数 (含 dst)
HDR_LEN = 4                 # 请求头: 魔数(2) + txn(2)

NO_FORWARD = 0
MIN_STATION = 1
MAX_STATION = 247

# 驱动单帧上限 4095B -> data<=4091B; 回复头占 5B, 故回复载荷 <= 4086B。
MAX_REPLY_PAYLOAD = 4091 - 5


def try_decode(payload):
    """把载荷还原成可读形式, 失败则 hex 摘要。"""
    raw = bytes(payload)
    try:
        return repr(raw.decode("utf-8"))
    except UnicodeDecodeError:
        if len(raw) <= 32:
            return "hex:" + raw.hex(" ")
        return "hex:" + raw[:32].hex(" ") + f"...({len(raw)}B)"


class InteractiveResponder(Node):
    """从机1 人工应答器: 收到请求入队, 主线程逐条提示你打回复。"""

    def __init__(self, tx_topic, rx_topic):
        super().__init__("ds10_relay_responder_interactive")
        self._tx_topic = tx_topic
        self._tx_pub = self.create_publisher(Frame, tx_topic, 10)
        self.create_subscription(Frame, rx_topic, self._on_rx, 10)
        # 收到的请求排队, 主线程逐条处理; 手动节奏下不会堆积。
        self._requests = queue.Queue()
        self.answered = 0
        self.get_logger().info(f"交互式应答器已启动: {rx_topic} → {tx_topic}")

    def _on_rx(self, msg):
        data = bytes(msg.data)
        if len(data) < HDR_LEN or data[:2] != MARKER:
            self.get_logger().warn(f"收到非请求格式的帧, 忽略: {try_decode(data)}")
            return
        txn = (data[2] << 8) | data[3]
        payload = data[HDR_LEN:]
        self._requests.put((txn, payload, msg.function_code))

    def next_request(self, timeout=0.5):
        """取下一条待回复的请求, 无则返回 None (让主线程能响应 Ctrl+C)。"""
        try:
            return self._requests.get(timeout=timeout)
        except queue.Empty:
            return None

    def send_reply(self, txn, dst, payload, function_code):
        out = Frame()
        # station_id 会被驱动覆盖为本机站号
        out.function_code = function_code
        out.data = list(
            REPLY_MARKER + bytes(((txn >> 8) & 0xFF, txn & 0xFF, dst)) + payload)
        self._tx_pub.publish(out)
        self.answered += 1

    def other_responder_present(self):
        """本话题上是否还有别的发布者 (自动应答器也发这里 -> 会抢答)。"""
        # count_publishers 含自身, >1 即有他人。
        return self.count_publishers(self._tx_topic) > 1


def ask(prompt):
    """读一行, Ctrl+D/Ctrl+C 抛出以便主循环退出。"""
    return input(prompt)


def ask_dst(default_dst):
    """提示输入转发目标站号, 回车用默认, 校验 0 或 1..247。"""
    while True:
        s = ask(f"  转发给哪个站号? (0=不转发, 回车=默认 {default_dst}): ").strip()
        if not s:
            return default_dst
        try:
            dst = int(s)
        except ValueError:
            print("    请输入整数")
            continue
        if dst == NO_FORWARD or MIN_STATION <= dst <= MAX_STATION:
            return dst
        print("    站号须为 0 或 1..247")


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 从机1 交互式应答器 (人工打回复)")
    ap.add_argument("--default-dst", type=int, default=2,
                    help="回车时使用的转发目标站号, 0=不转发 (默认 2)")
    ap.add_argument("--tx-topic", default="/slave1/tx", help="驱动 tx 话题")
    ap.add_argument("--rx-topic", default="/slave1/rx", help="驱动 rx 话题")
    return ap.parse_args()


BANNER = """
==========================================
DS10 从机1 交互式应答器 (人工打回复)
==========================================
等主机发来请求 -> 显示 -> 你敲回复内容和目标站号 -> 发回主机
回复内容回车留空 = 原样回显请求载荷
Ctrl-C / Ctrl-D 退出
"""


def main():
    args = parse_args()
    if args.default_dst != NO_FORWARD and not (
            MIN_STATION <= args.default_dst <= MAX_STATION):
        sys.exit(f"--default-dst 须为 0 或 1..247, 得到 {args.default_dst}")

    rclpy.init()
    node = InteractiveResponder(args.tx_topic, args.rx_topic)
    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()

    print(BANNER)
    time.sleep(1.5)   # 等发现, 再判断有没有别的应答器
    if node.other_responder_present():
        print("警告: 检测到另一个应答器也在发布 " + args.tx_topic + " ——")
        print("      多半是 start_relay.sh 的自动应答器在跑, 会与你抢答造成重复回复。")
        print("      交互测试请改用 ./start_ds10.sh (只起驱动)。\n")

    try:
        # 循环条件用 rclpy.ok(): rclpy 接管了 SIGTERM, 只关闭 context 而不在主线程
        # 抛异常。若这里写 while True, 空闲等请求时 SIGTERM/pkill/timeout 都杀不掉。
        while rclpy.ok():
            req = node.next_request()
            if req is None:
                continue
            txn, payload, function_code = req
            print(f"\n<< 收到请求 txn={txn} [{len(payload)}B] {try_decode(payload)}")

            try:
                text = ask("  回复内容 (回车=原样回显): ")
            except (EOFError, KeyboardInterrupt):
                break
            reply_payload = payload if text == "" else text.encode("utf-8")

            if len(reply_payload) > MAX_REPLY_PAYLOAD:
                print(f"    回复 {len(reply_payload)}B 超上限 {MAX_REPLY_PAYLOAD}B, 已截断")
                reply_payload = reply_payload[:MAX_REPLY_PAYLOAD]

            try:
                dst = ask_dst(args.default_dst)
            except (EOFError, KeyboardInterrupt):
                break

            node.send_reply(txn, dst, reply_payload, function_code)
            where = "不转发" if dst == NO_FORWARD else f"主机将转发给站号{dst}"
            print(f">> 已回复 txn={txn} dst={dst} [{len(reply_payload)}B] ({where})")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        print(f"\n共应答 {node.answered} 次, 退出中...")
        rclpy.shutdown()
        spin.join(timeout=2.0)
        node.destroy_node()
    return 0


if __name__ == "__main__":
    sys.exit(main())
