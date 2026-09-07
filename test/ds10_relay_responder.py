#!/usr/bin/env python3
"""DS10 从机应答器 — 按载荷内容决定回复该转发给谁。

工作方式:
  订阅 /slave1/rx, 收到主机的请求后:
    1. 剥掉 4B 请求头 (F1 F1 + txn), 取出业务载荷
    2. 用路由表按载荷内容选一个目标站号 dst (关键字匹配, 首个命中者胜)
    3. 组 5B 回复头 (F1 F2 + txn + dst) + 原载荷, 发到 /slave1/tx

  转发目标由**从机**决定, 主机只做合法性校验、不覆盖。dst=0 表示"回复我但别转发"。

回复头用 F1 F2 而非 F1 F1 是必要的, 不是美观问题: 请求与回复长度重叠, 单靠长度
无法区分。若沿用同一魔数, 旧格式回复(4B头)的载荷首字节会被误读成 dst —— 而可见
ASCII(32-126)全在合法站号范围(1-247)内, 于是 'Hello' 会被转发到站号 72。静默错投
比丢弃更糟, 故让格式自描述。

用法:
  # 终端1: 启动驱动
  ./start_ds10.sh

  # 终端2: 应答器, 载荷含 temp 的转给站号2, 含 humid 的转给站号3
  python3 test/ds10_relay_responder.py --route "temp:2,humid:3"

  # 中文关键字同样可用 (按 UTF-8 字节匹配)
  python3 test/ds10_relay_responder.py --route "温度:2,湿度:3" --default-dst 0

  # 终端3: 主机中继
  python3 test/ds10_relay_master.py
"""

import argparse
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
REPLY_MARKER = b"\xF1\xF2"  # 回复魔数 (含 dst), 与请求区分
HDR_LEN = 4                 # 请求头: 魔数(2) + txn(2)
REPLY_HDR_LEN = 5           # 回复头: 魔数(2) + txn(2) + dst(1)

NO_FORWARD = 0              # dst=0: 回复但不转发
MIN_STATION = 1
MAX_STATION = 247


def parse_route(spec):
    """把 "temp:2,humid:3" 解析成 [(keyword, station), ...]。

    格式错误立即抛错而非静默跳过 —— 打错一个字就静默不路由, 会让应答器看起来
    健康却什么都不转。
    """
    routes = []
    for entry in spec.split(","):
        entry = entry.strip()
        if not entry:
            continue
        keyword, sep, station_text = entry.rpartition(":")
        if not sep or not keyword or not station_text:
            raise ValueError(f"路由项须为 'keyword:station', 得到 {entry!r}")
        try:
            station = int(station_text)
        except ValueError:
            raise ValueError(f"站号须为整数, 得到 {station_text!r} (项 {entry!r})")
        if not MIN_STATION <= station <= MAX_STATION:
            raise ValueError(f"站号须在 1..247, 得到 {station} (项 {entry!r})")
        routes.append((keyword.encode("utf-8"), station))
    return routes


def route_lookup(routes, payload, default_dst):
    """按载荷内容选目标站号, 首个命中的关键字胜; 都不命中则用默认值。"""
    for keyword, station in routes:
        if keyword in payload:
            return station
    return default_dst


def try_decode(payload):
    """把载荷还原成可读形式, 失败则 hex 摘要。"""
    try:
        return repr(payload.decode("utf-8"))
    except UnicodeDecodeError:
        if len(payload) <= 32:
            return "hex:" + payload.hex(" ")
        return "hex:" + payload[:32].hex(" ") + f"...({len(payload)}B)"


class RelayResponder(Node):
    """从机应答器: /slave1/rx → 按内容选 dst → /slave1/tx。"""

    def __init__(self, routes, default_dst, tx_topic, rx_topic):
        super().__init__("ds10_relay_responder")
        self._routes = routes
        self._default_dst = default_dst
        self._tx_pub = self.create_publisher(Frame, tx_topic, 10)
        self.create_subscription(Frame, rx_topic, self._on_rx, 10)
        self.count = 0

        self.get_logger().info(f"RelayResponder 已启动: {rx_topic} → {tx_topic}")
        if routes:
            table = ", ".join(
                f"{k.decode('utf-8', 'replace')}→站号{s}" for k, s in routes)
            self.get_logger().info(f"路由表: {table} | 默认 dst={default_dst}")
        else:
            self.get_logger().warn(
                f"路由表为空, 所有回复都用默认 dst={default_dst}"
                f"{' (不转发)' if default_dst == NO_FORWARD else ''}。"
                f'用 --route "temp:2,humid:3" 让载荷决定目标。')

    def _on_rx(self, msg):
        data = bytes(msg.data)
        if len(data) < HDR_LEN or data[:2] != MARKER:
            self.get_logger().debug("请求缺少事务头, 丢弃")
            return
        txn = (data[2] << 8) | data[3]
        payload = data[HDR_LEN:]

        # 核心: 由从机自己按内容决定转发目标
        dst = route_lookup(self._routes, payload, self._default_dst)

        out = Frame()
        # station_id 会被驱动覆盖为本机站号
        out.function_code = msg.function_code
        out.data = list(
            REPLY_MARKER + bytes(((txn >> 8) & 0xFF, txn & 0xFF, dst)) + payload)
        self._tx_pub.publish(out)
        self.count += 1

        where = "不转发" if dst == NO_FORWARD else f"转给站号{dst}"
        self.get_logger().info(
            f"  << 请求 txn={txn} [{len(payload)}B] {try_decode(payload)}"
            f"  >> 回复 #{self.count} dst={dst} ({where})")


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 从机应答器 (按内容决定转发目标)")
    ap.add_argument("--route", default="",
                    help='路由表 "keyword:station,..." (如 "temp:2,humid:3")')
    ap.add_argument("--default-dst", type=int, default=NO_FORWARD,
                    help="无关键字命中时的目标站号, 0=不转发 (默认 0)")
    ap.add_argument("--tx-topic", default="/slave1/tx", help="驱动 tx 话题")
    ap.add_argument("--rx-topic", default="/slave1/rx", help="驱动 rx 话题")
    return ap.parse_args()


def main():
    args = parse_args()
    try:
        routes = parse_route(args.route)
    except ValueError as e:
        sys.exit(f"--route 参数错误: {e}")
    if args.default_dst != NO_FORWARD and not (
            MIN_STATION <= args.default_dst <= MAX_STATION):
        sys.exit(f"--default-dst 须为 0 或 1..247, 得到 {args.default_dst}")

    rclpy.init()
    node = RelayResponder(routes, args.default_dst, args.tx_topic, args.rx_topic)
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,))
    spin_thread.start()
    try:
        # 循环条件用 rclpy.ok(): rclpy 自己接管了 SIGTERM, 只关闭 context 而不会
        # 在主线程抛异常。若这里写 while True, SIGTERM/pkill 杀不掉本进程。
        while rclpy.ok():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            rclpy.shutdown()      # 让 spin() 返回
        spin_thread.join(timeout=2.0)
        node.destroy_node()
        print(f"\n共应答 {node.count} 次, 退出。")


if __name__ == "__main__":
    sys.exit(main())
