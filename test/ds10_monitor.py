#!/usr/bin/env python3
"""DS10 一主两从实时收发监控。

订阅所有驱动 topic, 实时打印收发情况。适配 start_ds10.sh 的 topic 命名:
  /master/tx  /master/rx    主机
  /slave1/tx  /slave1/rx    从机1
  /slave2/tx  /slave2/rx    从机2

用法:
  source /opt/ros/humble/setup.bash && source install/setup.bash          # 必须先 source, 否则 import 失败
  python3 test/ds10_monitor.py
  python3 test/ds10_monitor.py -v     # 详情模式 (打印 data 字段)
"""

import argparse
import sys
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

FUNC_TEXT = 0x10


def decode(data):
    try:
        return repr(bytes(data).decode("utf-8"))
    except UnicodeDecodeError:
        return "hex:" + bytes(data).hex(" ")


class Monitor(Node):

    def __init__(self, detail=False):
        super().__init__("ds10_monitor")
        self._detail = detail
        self._t0 = time.monotonic()

        # 汇总计数, key 与 _make_handler 传入的 count_key 一致
        self._counts = {
            "主 TX": 0, "主 RX": 0,
            "从1 TX": 0, "从1 RX": 0,
            "从2 TX": 0, "从2 RX": 0,
        }

        # (topic, 显示标签, 计数key, 是否主机侧接收)
        subs = [
            ("/master/tx", "主机 发送 ->串口", "主 TX", False),
            ("/master/rx", "主机 接收 <-无线", "主 RX", True),
            ("/slave1/tx", "从机1 发送 ->串口", "从1 TX", False),
            ("/slave1/rx", "从机1 接收 <-无线", "从1 RX", False),
            ("/slave2/tx", "从机2 发送 ->串口", "从2 TX", False),
            ("/slave2/rx", "从机2 接收 <-无线", "从2 RX", False),
        ]
        self._subs = [
            self.create_subscription(
                Frame, topic, self._make_handler(label, key, master_rx), 10)
            for topic, label, key, master_rx in subs
        ]

        self._timer = self.create_timer(5.0, self._report)

    def _make_handler(self, label, count_key, master_rx):
        def handler(msg):
            self._counts[count_key] += 1
            elapsed = time.monotonic() - self._t0
            # 主机 RX 的 station_id 是来源从机; 主机 TX 的是路由目标;
            # 从机侧 RX 恒为 0(来自主机), 没有展示价值。
            if master_rx:
                extra = f"  来源=从机{msg.station_id}"
            elif count_key == "主 TX":
                extra = f"  目标=从机{msg.station_id}"
            else:
                extra = ""
            body = f"  {label}  功能=0x{msg.function_code:02X}  seq={msg.tx_seq}{extra}"
            if self._detail and msg.data:
                body += f"  {decode(msg.data)}"
            print(f"[{elapsed:6.1f}s]{body}")
        return handler

    def _report(self):
        c = self._counts
        print(f"\n  --- 5s 汇总: 主 TX={c['主 TX']} RX={c['主 RX']}  "
              f"从1 TX={c['从1 TX']} RX={c['从1 RX']}  "
              f"从2 TX={c['从2 TX']} RX={c['从2 RX']} ---\n")


def main():
    parser = argparse.ArgumentParser(description="DS10 实时收发监控")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示 data 内容")
    args = parser.parse_args()

    rclpy.init()
    node = Monitor(detail=args.verbose)
    print("DS10 监控启动 — 实时收发显示 (每 5s 汇总一次)")
    print("  发送 ->串口 : 应用层写入驱动, 驱动组帧后写串口")
    print("  接收 <-无线 : 驱动从串口解出完整帧并发布")
    print("  Ctrl+C 退出")
    print()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())