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
End-to-end test for the protocol bridge over real ROS topics.

No serial port and no driver: the test itself plays both ends. It publishes on
the topics the driver would own and asserts the Frame comes out unchanged on
the application side, and vice versa. Decode logging is checked against the
node's captured output. This is the highest-level seam for the node -- it
exercises parameter resolution, topic creation, both callbacks and the decode
dispatch.
"""

import struct
import time
import unittest

import launch
import launch_ros.actions
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from ds10_interfaces.msg import Frame

# Non-default topic names, so the test also proves the parameters are honoured.
DRIVER_RX = '/test_driver/rx'
DRIVER_TX = '/test_driver/tx'
PROTOCOL_RX = '/test_protocol/rx'
PROTOCOL_TX = '/test_protocol/tx'

DISCOVERY_TIMEOUT = 5.0
DELIVERY_TIMEOUT = 5.0
LOG_TIMEOUT = 5.0


@pytest.mark.launch_test
def generate_test_description():
    node = launch_ros.actions.Node(
        package='ds10_protocol',
        executable='protocol_bridge',
        name='protocol_bridge',
        output='screen',
        parameters=[{
            'driver_rx_topic': DRIVER_RX,
            'driver_tx_topic': DRIVER_TX,
            'protocol_rx_topic': PROTOCOL_RX,
            'protocol_tx_topic': PROTOCOL_TX,
        }],
    )

    return (
        launch.LaunchDescription([
            node,
            launch_testing.actions.ReadyToTest(),
        ]),
        {'bridge_process': node},
    )


class TestProtocolBridge(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.node = rclpy.create_node('protocol_bridge_test_peer')

    def tearDown(self):
        self.node.destroy_node()

    def _await_subscriber(self, pub):
        """Block until the bridge has matched our publisher, or fail."""
        end = time.time() + DISCOVERY_TIMEOUT
        while time.time() < end and pub.get_subscription_count() < 1:
            rclpy.spin_once(self.node, timeout_sec=0.1)
            time.sleep(0.05)
        self.assertGreaterEqual(
            pub.get_subscription_count(), 1,
            f'bridge did not subscribe to {pub.topic_name}')

    def _pump_until(self, received, pub, msg):
        """Republish until a message arrives or the timeout expires."""
        end = time.time() + DELIVERY_TIMEOUT
        while time.time() < end and not received:
            pub.publish(msg)
            rclpy.spin_once(self.node, timeout_sec=0.1)
            time.sleep(0.05)

    def _publish_and_await_log(self, proc_output, bridge_process, msg, expected_log):
        """Publish to the driver rx topic until `expected_log` shows up."""
        pub = self.node.create_publisher(Frame, DRIVER_RX, 10)
        self._await_subscriber(pub)

        end = time.time() + LOG_TIMEOUT
        while time.time() < end:
            pub.publish(msg)
            rclpy.spin_once(self.node, timeout_sec=0.1)
            try:
                proc_output.assertWaitFor(
                    expected_output=expected_log, process=bridge_process, timeout=0.5)
                return
            except AssertionError:
                continue

        self.fail(f'bridge never logged {expected_log!r}')

    @staticmethod
    def _sample_frame():
        msg = Frame()
        msg.station_id = 7
        msg.function_code = 0x10
        msg.data = list(b'\x01\x02\x03\xFF')
        return msg

    def _assert_same_frame(self, got, sent):
        self.assertEqual(got.station_id, sent.station_id)
        self.assertEqual(got.function_code, sent.function_code)
        self.assertEqual(bytes(got.data), bytes(sent.data))

    def test_driver_rx_forwarded_to_protocol_rx(self):
        """A Frame from the driver side reaches the application side intact."""
        received = []
        self.node.create_subscription(
            Frame, PROTOCOL_RX, lambda m: received.append(m), 10)
        pub = self.node.create_publisher(Frame, DRIVER_RX, 10)
        self._await_subscriber(pub)

        sent = self._sample_frame()
        self._pump_until(received, pub, sent)

        self.assertTrue(received, 'no Frame arrived on the protocol rx topic')
        self._assert_same_frame(received[0], sent)

    def test_protocol_tx_forwarded_to_driver_tx(self):
        """A Frame from the application side reaches the driver side intact."""
        received = []
        self.node.create_subscription(
            Frame, DRIVER_TX, lambda m: received.append(m), 10)
        pub = self.node.create_publisher(Frame, PROTOCOL_TX, 10)
        self._await_subscriber(pub)

        sent = Frame()
        sent.station_id = 3
        sent.function_code = 0x12
        sent.data = list(b'\xAA\xBB')
        self._pump_until(received, pub, sent)

        self.assertTrue(received, 'no Frame arrived on the driver tx topic')
        self._assert_same_frame(received[0], sent)

    def test_empty_payload_survives_round_trip(self):
        """An empty data field is forwarded, not dropped or padded."""
        received = []
        self.node.create_subscription(
            Frame, PROTOCOL_RX, lambda m: received.append(m), 10)
        pub = self.node.create_publisher(Frame, DRIVER_RX, 10)
        self._await_subscriber(pub)

        sent = Frame()
        sent.station_id = 1
        sent.function_code = 0x00
        sent.data = []
        self._pump_until(received, pub, sent)

        self.assertTrue(received, 'no Frame arrived on the protocol rx topic')
        self._assert_same_frame(received[0], sent)

    def test_control_command_is_decoded_and_logged(self, proc_output, bridge_process):
        """A 0x12 frame has its fields logged, and is still forwarded."""
        received = []
        self.node.create_subscription(
            Frame, PROTOCOL_RX, lambda m: received.append(m), 10)

        sent = Frame()
        sent.station_id = 1
        sent.function_code = 0x12
        sent.data = [0x01, 0x05, 0xAA, 0xBB]  # flags=1, cmd_id=5, params=2 bytes

        self._publish_and_await_log(
            proc_output, bridge_process, sent,
            'Decoded 0x12: flags=1, cmd_id=5, params_len=2')

        # Decoding must not swallow the frame.
        end = time.time() + DELIVERY_TIMEOUT
        while time.time() < end and not received:
            rclpy.spin_once(self.node, timeout_sec=0.1)
        self.assertTrue(received, 'decoded frame was not forwarded')
        self._assert_same_frame(received[0], sent)

    def test_sensor_data_is_decoded_and_logged(self, proc_output, bridge_process):
        """A 0x10 frame has its fields logged."""
        sent = Frame()
        sent.station_id = 2
        sent.function_code = 0x10
        # [flags 1B][seq u16 LE][sensor_id 1B][reading f32 LE]
        sent.data = list(struct.pack('<BHBf', 0x00, 4660, 7, 23.5))

        self._publish_and_await_log(
            proc_output, bridge_process, sent,
            'Decoded 0x10: flags=0, seq=4660, sensor_id=7')

    def test_unknown_function_code_warns(self, proc_output, bridge_process):
        """A function code with no decoder warns but is still forwarded."""
        received = []
        self.node.create_subscription(
            Frame, PROTOCOL_RX, lambda m: received.append(m), 10)

        sent = Frame()
        sent.station_id = 9
        sent.function_code = 0xFF
        sent.data = [0xDE, 0xAD]

        self._publish_and_await_log(
            proc_output, bridge_process, sent,
            'Unknown or unimplemented function_code=0xFF from station=9')

        end = time.time() + DELIVERY_TIMEOUT
        while time.time() < end and not received:
            rclpy.spin_once(self.node, timeout_sec=0.1)
        self.assertTrue(received, 'unknown-code frame was not forwarded')
        self._assert_same_frame(received[0], sent)

    def test_undersized_payload_errors_but_still_forwards(self, proc_output, bridge_process):
        """A 0x10 frame too short to decode logs an error and is forwarded."""
        received = []
        self.node.create_subscription(
            Frame, PROTOCOL_RX, lambda m: received.append(m), 10)

        sent = Frame()
        sent.station_id = 4
        sent.function_code = 0x10
        sent.data = [0x00, 0x01, 0x02]  # 3 bytes; 0x10 needs 8

        self._publish_and_await_log(
            proc_output, bridge_process, sent,
            'Failed to decode function_code=0x10: data size=3 (expected >=8)')

        end = time.time() + DELIVERY_TIMEOUT
        while time.time() < end and not received:
            rclpy.spin_once(self.node, timeout_sec=0.1)
        self.assertTrue(received, 'undecodable frame was not forwarded')
        self._assert_same_frame(received[0], sent)


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_exit_codes(self, proc_info):
        launch_testing.asserts.assertExitCodes(proc_info)
