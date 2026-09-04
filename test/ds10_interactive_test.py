#!/usr/bin/env python3
"""DS10 一主两从交互式数据传输测试。

驱动节点由 start_ds10.sh 启动, 本脚本直连驱动 topic:
  /master/tx  /master/rx    主机
  /slave1/tx  /slave1/rx    从机1 (station_id=1)
  /slave2/tx  /slave2/rx    从机2 (station_id=2)

四个测试场景 (数据全部由用户手动输入):
  1  主机 -> 两个从机同时
  2  两个从机 -> 主机同时
  3  主机->从机1 与 从机2->主机 同时双向
  4  自由发送 (任选方向, 反复发)

发送的是文本数据: UTF-8 编码后放入 Modbus 帧的 data 字段, 功能码 0x10。
接收侧按 UTF-8 解码显示, 解不开则退回 hex。

用法:
  source /opt/ros/humble/setup.bash && source install/setup.bash          # 必须先 source, 否则 import 失败
  python3 test/ds10_interactive_test.py
"""

import sys
import threading
import time

try:
    import rclpy
    from rclpy.node import Node

    from ds10_interfaces.msg import Frame
except ModuleNotFoundError as e:
    sys.exit(
        f"错误: 无法导入 {e.name} —— ROS 2 环境未加载。\n"
        "请先在本终端执行:\n"
        "  source /opt/ros/humble/setup.bash\n"
        "  source install/setup.bash\n"
        "(需在 ~/DS10_Modbus 目录下, 且已 colcon build)"
    )

FUNC_TEXT = 0x10          # 文本数据功能码, 与监控脚本约定一致
RECV_WAIT = 3.0           # 每轮发送后等待接收的秒数


def decode_text(data):
    """把 data 字段还原成可读文本, 失败则显示 hex。"""
    try:
        return repr(bytes(data).decode("utf-8"))
    except UnicodeDecodeError:
        return "hex:" + bytes(data).hex(" ")


class InteractiveTester(Node):

    def __init__(self):
        super().__init__("ds10_interactive_tester")

        self.master_tx = self.create_publisher(Frame, "/master/tx", 10)
        self.slave1_tx = self.create_publisher(Frame, "/slave1/tx", 10)
        self.slave2_tx = self.create_publisher(Frame, "/slave2/tx", 10)

        self.create_subscription(Frame, "/master/rx", self._on_master_rx, 10)
        self.create_subscription(Frame, "/slave1/rx", self._on_slave1_rx, 10)
        self.create_subscription(Frame, "/slave2/rx", self._on_slave2_rx, 10)

        # 收件箱: 每轮测试前清空, 结束后核对
        self._lock = threading.Lock()
        self.master_inbox = []      # [(来源站号, 文本)]
        self.slave1_inbox = []
        self.slave2_inbox = []

        self._seq = 0

    # ---- 接收回调 ----

    def _on_master_rx(self, msg):
        with self._lock:
            self.master_inbox.append((msg.station_id, decode_text(msg.data)))
        print(f"  << 主机收到 [来自从机{msg.station_id}] {decode_text(msg.data)}")

    def _on_slave1_rx(self, msg):
        with self._lock:
            self.slave1_inbox.append((msg.station_id, decode_text(msg.data)))
        print(f"  << 从机1收到 [来自主机] {decode_text(msg.data)}")

    def _on_slave2_rx(self, msg):
        with self._lock:
            self.slave2_inbox.append((msg.station_id, decode_text(msg.data)))
        print(f"  << 从机2收到 [来自主机] {decode_text(msg.data)}")

    # ---- 发送 ----

    def clear_inboxes(self):
        with self._lock:
            self.master_inbox.clear()
            self.slave1_inbox.clear()
            self.slave2_inbox.clear()

    def _frame(self, station, text):
        self._seq += 1
        msg = Frame()
        msg.station_id = station
        msg.function_code = FUNC_TEXT
        msg.data = list(text.encode("utf-8"))
        msg.tx_seq = self._seq
        return msg

    def master_send(self, station, text):
        """主机发给指定从机, station 决定路由目标。"""
        self.master_tx.publish(self._frame(station, text))
        print(f"  >> 主机 -> 从机{station}: {text!r}")

    def slave_send(self, which, text):
        """从机发给主机, station_id 由驱动按启动参数覆盖。"""
        pub = self.slave1_tx if which == 1 else self.slave2_tx
        pub.publish(self._frame(0, text))
        print(f"  >> 从机{which} -> 主机: {text!r}")

    def counts(self):
        with self._lock:
            from_s1 = sum(1 for st, _ in self.master_inbox if st == 1)
            from_s2 = sum(1 for st, _ in self.master_inbox if st == 2)
            return {
                "主机<-从机1": from_s1,
                "主机<-从机2": from_s2,
                "从机1": len(self.slave1_inbox),
                "从机2": len(self.slave2_inbox),
            }


def ask(prompt):
    """读一行输入, 空行返回 None, Ctrl+D/Ctrl+C 抛 EOFError。"""
    try:
        s = input(prompt).strip()
    except EOFError:
        raise
    return s if s else None


def wait_and_report(node, expect, label):
    """等接收窗口结束, 打印实收 vs 预期。"""
    print(f"\n  等待接收 ({RECV_WAIT:.0f}s)...")
    time.sleep(RECV_WAIT)
    got = node.counts()
    print(f"\n  {label} 结果:")
    ok = True
    for key, want in expect.items():
        have = got.get(key, 0)
        mark = "OK" if have >= want else "缺失"
        if have < want:
            ok = False
        print(f"    {key}: {have}/{want}  {mark}")
    print("  => 通过" if ok else "  => 未达预期(检查 DS10 配对/信道/RUN 档)")


def scenario_1(node):
    print("\n--- 场景1: 主机同时发给两个从机 ---")
    t1 = ask("给从机1的文本: ")
    t2 = ask("给从机2的文本: ")
    if not t1 or not t2:
        print("  输入为空, 跳过")
        return
    node.clear_inboxes()
    print()
    node.master_send(1, t1)
    node.master_send(2, t2)
    wait_and_report(node, {"从机1": 1, "从机2": 1}, "场景1")


def scenario_2(node):
    print("\n--- 场景2: 两个从机同时发给主机 ---")
    t1 = ask("从机1发送的文本: ")
    t2 = ask("从机2发送的文本: ")
    if not t1 or not t2:
        print("  输入为空, 跳过")
        return
    node.clear_inboxes()
    print()
    node.slave_send(1, t1)
    node.slave_send(2, t2)
    wait_and_report(node, {"主机<-从机1": 1, "主机<-从机2": 1}, "场景2")


def scenario_3(node):
    print("\n--- 场景3: 主机->从机1 与 从机2->主机 同时 ---")
    t1 = ask("主机发给从机1的文本: ")
    t2 = ask("从机2发给主机的文本: ")
    if not t1 or not t2:
        print("  输入为空, 跳过")
        return
    node.clear_inboxes()
    print()
    node.master_send(1, t1)
    node.slave_send(2, t2)
    wait_and_report(node, {"从机1": 1, "主机<-从机2": 1}, "场景3")


def scenario_4(node):
    print("\n--- 场景4: 自由发送 (回车空行返回菜单) ---")
    print("  方向: m1=主机->从机1  m2=主机->从机2  s1=从机1->主机  s2=从机2->主机")
    while True:
        d = ask("方向: ")
        if not d:
            return
        if d not in ("m1", "m2", "s1", "s2"):
            print("  方向无效")
            continue
        text = ask("文本: ")
        if not text:
            continue
        node.clear_inboxes()
        print()
        if d == "m1":
            node.master_send(1, text)
        elif d == "m2":
            node.master_send(2, text)
        elif d == "s1":
            node.slave_send(1, text)
        else:
            node.slave_send(2, text)
        time.sleep(RECV_WAIT)
        print()


MENU = """
==========================================
DS10 一主两从交互式测试
==========================================
  1  主机同时发给两个从机
  2  两个从机同时发给主机
  3  主机->从机1 与 从机2->主机 同时
  4  自由发送 (任选方向, 反复发)
  q  退出
"""


def main():
    rclpy.init()
    node = InteractiveTester()

    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()

    print("等待 ROS 2 连接建立...")
    time.sleep(2)

    # 没有驱动在跑的话, 早点告诉用户, 而不是让他对着 0/1 结果猜
    if node.count_subscribers("/master/tx") == 0:
        print("\n警告: /master/tx 没有订阅者 —— 驱动节点似乎没在运行。")
        print("      请先在另一个终端执行 ./start_ds10.sh\n")

    handlers = {"1": scenario_1, "2": scenario_2, "3": scenario_3, "4": scenario_4}
    try:
        while True:
            print(MENU)
            try:
                choice = input("选择: ").strip().lower()
            except EOFError:
                break
            if choice in ("q", "quit", "exit"):
                break
            handler = handlers.get(choice)
            if handler is None:
                print("  无效选择")
                continue
            try:
                handler(node)
            except EOFError:
                break
    except KeyboardInterrupt:
        pass
    finally:
        print("\n退出中...")
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
