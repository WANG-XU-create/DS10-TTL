# Copyright 2026 wangxu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
PTY-backed integration test for the DS10 driver node (test seam 2).

A pseudo-terminal pair fakes the serial link: the node opens the slave end of
the PTY, the test drives the master end. This exercises the full path
tx topic -> encode -> serial write, and serial read -> hybrid delimiter ->
rx topic, with a real node and a real fd, without any DS10 hardware.
"""

import os
import pty
import time
import unittest

import launch
import launch_ros.actions
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from ds10_interfaces.msg import Frame


def modbus_crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def build_frame(station: int, func: int, data: bytes) -> bytes:
    body = bytes((station, func)) + data
    return body + modbus_crc16(body)


@pytest.mark.launch_test
def generate_test_description():
    # Create the PTY pair here so the node can be pointed at the slave end.
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)

    node = launch_ros.actions.Node(
        package='ds10_driver',
        executable='ds10_node',
        name='ds10_master',
        parameters=[{
            'port': slave_name,
            'baud': 115200,
            'role': 'master',
            'frame_timeout_ms': 20,
        }],
    )

    context = {'master_fd': master_fd, 'slave_fd': slave_fd}
    return (
        launch.LaunchDescription([
            node,
            launch_testing.actions.ReadyToTest(),
        ]),
        context,
    )


class TestDs10Bridge(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.node = rclpy.create_node('ds10_test_peer')

    def tearDown(self):
        self.node.destroy_node()

    def test_serial_to_rx(self, master_fd):
        """A Modbus frame written to the PTY appears on ~/rx with fields intact."""
        received = []
        self.node.create_subscription(
            Frame, '/ds10_master/rx', lambda m: received.append(m), 10)

        # Give the node time to open the PTY and start its reader thread.
        time.sleep(1.0)

        payload = bytes(range(16))
        frame = build_frame(3, 0x10, payload)
        os.write(master_fd, frame)

        end = time.time() + 5.0
        while time.time() < end and not received:
            rclpy.spin_once(self.node, timeout_sec=0.1)

        self.assertEqual(len(received), 1, 'expected exactly one rx Frame')
        msg = received[0]
        self.assertEqual(msg.station_id, 3)
        self.assertEqual(msg.function_code, 0x10)
        self.assertEqual(bytes(msg.data), payload)

    def test_tx_to_serial(self, master_fd):
        """A Frame published to ~/tx is encoded and emitted on the PTY."""
        pub = self.node.create_publisher(Frame, '/ds10_master/tx', 10)

        # Wait for the node's ~/tx subscription to match before publishing,
        # otherwise early messages are dropped before discovery completes.
        end = time.time() + 5.0
        while time.time() < end and pub.get_subscription_count() < 1:
            rclpy.spin_once(self.node, timeout_sec=0.1)
            time.sleep(0.05)
        self.assertGreaterEqual(
            pub.get_subscription_count(), 1, 'node did not subscribe to ~/tx')

        msg = Frame()
        msg.station_id = 5
        msg.function_code = 0x03
        msg.data = list(b'\xAA\xBB\xCC')

        os.set_blocking(master_fd, False)
        expected = build_frame(5, 0x03, b'\xAA\xBB\xCC')
        got = b''
        end = time.time() + 5.0
        while time.time() < end and expected not in got:
            pub.publish(msg)
            rclpy.spin_once(self.node, timeout_sec=0.1)
            time.sleep(0.1)
            try:
                got += os.read(master_fd, 256)
            except BlockingIOError:
                pass

        self.assertIn(expected, got, f'encoded frame not found in {got!r}')


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_exit_codes(self, proc_info):
        launch_testing.asserts.assertExitCodes(proc_info)
