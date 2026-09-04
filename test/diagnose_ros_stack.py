#!/usr/bin/env python3
"""诊断 ROS 2 协议栈的数据流"""

import rclpy
from rclpy.node import Node
from ds10_interfaces.msg import Frame
import time

class StackDiagnostic(Node):
    def __init__(self):
        super().__init__('stack_diagnostic')

        # 订阅所有关键 topic
        self.create_subscription(Frame, '/ds10_master/tx', self.on_master_driver_tx, 10)
        self.create_subscription(Frame, '/ds10_master/rx', self.on_master_driver_rx, 10)
        self.create_subscription(Frame, '/master/protocol/tx', self.on_master_app_tx, 10)
        self.create_subscription(Frame, '/master/protocol/rx', self.on_master_app_rx, 10)

        self.create_subscription(Frame, '/ds10_slave1/tx', self.on_slave1_driver_tx, 10)
        self.create_subscription(Frame, '/ds10_slave1/rx', self.on_slave1_driver_rx, 10)
        self.create_subscription(Frame, '/slave1/protocol/tx', self.on_slave1_app_tx, 10)
        self.create_subscription(Frame, '/slave1/protocol/rx', self.on_slave1_app_rx, 10)

        # 发布测试消息
        self.master_pub = self.create_publisher(Frame, '/master/protocol/tx', 10)

        self.get_logger().info("诊断节点启动，订阅所有关键 topic")

    def on_master_driver_tx(self, msg):
        self.get_logger().info(f"[主机驱动发送] 站{msg.station_id} 功能0x{msg.function_code:02X} {len(msg.data)}B")

    def on_master_driver_rx(self, msg):
        self.get_logger().info(f"[主机驱动接收] 站{msg.station_id} 功能0x{msg.function_code:02X} {len(msg.data)}B")

    def on_master_app_tx(self, msg):
        self.get_logger().info(f"[主机应用发送] 站{msg.station_id} 功能0x{msg.function_code:02X} {len(msg.data)}B")

    def on_master_app_rx(self, msg):
        self.get_logger().info(f"[主机应用接收] 站{msg.station_id} 功能0x{msg.function_code:02X} {len(msg.data)}B")

    def on_slave1_driver_tx(self, msg):
        self.get_logger().info(f"[从机1驱动发送] 站{msg.station_id} 功能0x{msg.function_code:02X} {len(msg.data)}B")

    def on_slave1_driver_rx(self, msg):
        self.get_logger().info(f"[从机1驱动接收] 站{msg.station_id} 功能0x{msg.function_code:02X} {len(msg.data)}B")

    def on_slave1_app_tx(self, msg):
        self.get_logger().info(f"[从机1应用发送] 站{msg.station_id} 功能0x{msg.function_code:02X} {len(msg.data)}B")

    def on_slave1_app_rx(self, msg):
        self.get_logger().info(f"[从机1应用接收] 站{msg.station_id} 功能0x{msg.function_code:02X} {len(msg.data)}B")

    def send_test_frame(self):
        """发送一个测试帧"""
        msg = Frame()
        msg.station_id = 1  # 发给从机1
        msg.function_code = 0x10
        msg.data = [0xFF, 0, 1, 0, 10, 0x11, 0x22, 0x33, 0x44]
        self.master_pub.publish(msg)
        self.get_logger().info("发送测试帧到 /master/protocol/tx")

def main():
    rclpy.init()
    node = StackDiagnostic()

    # 发送一个测试帧
    time.sleep(2)
    node.send_test_frame()

    # 持续监听
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
