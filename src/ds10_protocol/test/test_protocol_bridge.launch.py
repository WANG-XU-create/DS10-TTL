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

    def _await_publisher(self, topic):
        """Block until the bridge is publishing on `topic`, or fail."""
        end = time.time() + DISCOVERY_TIMEOUT
        while time.time() < end and self.node.count_publishers(topic) < 1:
            rclpy.spin_once(self.node, timeout_sec=0.1)
            time.sleep(0.05)
        self.assertGreaterEqual(
            self.node.count_publishers(topic), 1,
            f'bridge did not publish on {topic}')

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
    def _sensor_frame(station, seq, sensor_id=7, reading=1.0, flags=0x00):
        """Build a 0x10 frame: [flags 1B][seq u16 LE][sensor_id 1B][reading f32 LE]."""
        msg = Frame()
        msg.station_id = station
        msg.function_code = 0x10
        msg.data = list(struct.pack('<BHBf', flags, seq, sensor_id, reading))
        return msg

    @staticmethod
    def _control_frame(station, cmd_id=0x05, params=b'\xAA', flags=0x00):
        """Build a 0x12 frame: [flags 1B][cmd_id 1B][params...]."""
        msg = Frame()
        msg.station_id = station
        msg.function_code = 0x12
        msg.data = list(struct.pack('<BB', flags, cmd_id) + params)
        return msg

    def _wire_up_ack(self):
        """Watch the driver tx topic for ACKs while feeding the driver rx topic."""
        return self._wire_up(sub_topic=DRIVER_TX, await_publisher=True)

    def _send_sequence(self, pub, frames, settle=0.15):
        """
        Publish each frame exactly once, in order.

        Sequence tracking is stateful, so the retry loop used elsewhere would
        corrupt the very thing under test -- a republished frame is a genuine
        duplicate as far as the bridge is concerned. Publish once and give the
        bridge time to process before the next one.
        """
        for msg in frames:
            pub.publish(msg)
            end = time.time() + settle
            while time.time() < end:
                rclpy.spin_once(self.node, timeout_sec=0.02)

    def _watch(self, topic, await_publisher=False):
        """
        Collect everything the bridge publishes on `topic`.

        Returns the list the subscription callback appends to.

        `await_publisher` also waits for the bridge to be publishing there.
        Needed whenever the message is emitted during the very callback our
        publish triggers -- a subscription that has not matched yet would miss
        it, and the test would read as "nothing was sent" rather than "not
        connected".
        """
        received = []
        self.node.create_subscription(
            Frame, topic, lambda m: received.append(m), 10)
        if await_publisher:
            self._await_publisher(topic)
        return received

    def _wire_up(self, sub_topic=PROTOCOL_RX, pub_topic=DRIVER_RX, await_publisher=False):
        """
        Subscribe, publish and wait for both ends to match.

        Returns (received_list, publisher). Callers spin and then assert on
        the list's length.
        """
        received = self._watch(sub_topic, await_publisher)
        pub = self.node.create_publisher(Frame, pub_topic, 10)
        self._await_subscriber(pub)
        return received, pub

    def _collect(self, received, expected_count, timeout=2.0):
        """
        Spin until `expected_count` messages arrive or the timeout expires.

        Returns whatever arrived; callers assert on the count so that both
        "too few" and "too many" fail.
        """
        end = time.time() + timeout
        while time.time() < end and len(received) < expected_count:
            rclpy.spin_once(self.node, timeout_sec=0.05)
        return received

    def _assert_not_logged(self, proc_output, bridge_process, message):
        """
        Fail if the bridge logged exactly `message`.

        `proc_output[process]` only exposes part of the stream, so scanning it
        for "any line resembling this" silently matches nothing. Callers pass
        the exact string a regression would emit -- established by mutating
        the code and reading what it prints -- so the assertion fails loudly
        if that path is ever taken, and cannot pass vacuously against a string
        no code path can produce.
        """
        with self.assertRaises(AssertionError, msg=f'bridge wrongly logged: {message}'):
            proc_output.assertWaitFor(
                expected_output=message, process=bridge_process, timeout=0.5)

    def _assert_no_gap_reported(self, proc_output, bridge_process, expected, got, station):
        """Fail if the bridge reported this specific gap."""
        self._assert_not_logged(
            proc_output, bridge_process,
            f'Gap detected: expected seq={expected}, got seq={got} '
            f'(station={station}, function_code=0x10)')

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
        received, pub = self._wire_up()

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
        received, pub = self._wire_up()

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
            'Decoded 0x10: flags=0, seq=4660, sensor_id=7, reading=23.500000')

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

    def test_sequence_gaps_are_warned_but_forwarded(self, proc_output, bridge_process):
        """Sequence 1,3,5 reports two gaps, and all three frames still arrive."""
        received, pub = self._wire_up()

        station = 21
        self._send_sequence(pub, [self._sensor_frame(station, s) for s in (1, 3, 5)])

        proc_output.assertWaitFor(
            expected_output=f'Gap detected: expected seq=2, got seq=3 (station={station}',
            process=bridge_process, timeout=LOG_TIMEOUT)
        proc_output.assertWaitFor(
            expected_output=f'Gap detected: expected seq=4, got seq=5 (station={station}',
            process=bridge_process, timeout=LOG_TIMEOUT)

        # A gap means frames were lost on the link, not that the ones that
        # made it are suspect -- all three must reach the application.
        got = self._collect(received, 3)
        self.assertEqual(len(got), 3, f'expected 3 frames through, got {len(got)}')

    def test_duplicate_sequence_is_dropped(self, proc_output, bridge_process):
        """Sequence 1,1,2 delivers only two frames; the repeat is withheld."""
        received, pub = self._wire_up()

        station = 22
        self._send_sequence(pub, [self._sensor_frame(station, s) for s in (1, 1, 2)])

        proc_output.assertWaitFor(
            expected_output=f'Duplicate seq=1 (station={station})',
            process=bridge_process, timeout=LOG_TIMEOUT)

        # Wait for the two legitimate frames, then confirm a third never shows
        # up -- the drop is the whole point of the test.
        got = self._collect(received, 2)
        self.assertEqual(len(got), 2, f'expected 2 frames through, got {len(got)}')
        self._collect(received, 3, timeout=0.5)
        self.assertEqual(len(received), 2, 'duplicate frame was forwarded')

    def test_sequence_wraparound_is_not_a_gap(self, proc_output, bridge_process):
        """65534,65535,0,1 crosses the uint16 boundary without warning."""
        received, pub = self._wire_up()

        station = 23
        self._send_sequence(
            pub, [self._sensor_frame(station, s) for s in (65534, 65535, 0, 1)])

        got = self._collect(received, 4)
        self.assertEqual(len(got), 4, f'expected 4 frames through, got {len(got)}')

        # With modular arithmetic 65535 -> 0 is an ordinary increment. A
        # tracker that compared magnitudes reports a gap at that step, with
        # expected and got both reading 0 -- verified by mutating the tracker
        # and observing the message it emits. Assert on exactly that.
        self._assert_no_gap_reported(
            proc_output, bridge_process, expected=0, got=0, station=station)

    def test_stations_are_tracked_independently(self, proc_output, bridge_process):
        """A gap on one station does not implicate another."""
        received, pub = self._wire_up()

        gappy, clean = 24, 25
        self._send_sequence(pub, [
            self._sensor_frame(gappy, 1),
            self._sensor_frame(clean, 1),
            self._sensor_frame(gappy, 3),   # skips 2
            self._sensor_frame(clean, 2),   # consecutive
        ])

        proc_output.assertWaitFor(
            expected_output=f'Gap detected: expected seq=2, got seq=3 (station={gappy}',
            process=bridge_process, timeout=LOG_TIMEOUT)

        # A shared tracker would let station 24's jump to seq=3 set the
        # expectation station 25 is judged against, reporting a gap at its
        # seq=2. Assert on exactly that message.
        self._assert_no_gap_reported(
            proc_output, bridge_process, expected=4, got=2, station=clean)

        got = self._collect(received, 4)
        self.assertEqual(len(got), 4, f'expected 4 frames through, got {len(got)}')

    def test_control_command_requesting_ack_is_answered(self, proc_output, bridge_process):
        """A 0x12 frame with flags.bit0=1 draws a 0x00 reply to its sender."""
        received, pub = self._wire_up_ack()

        station = 30
        self._send_sequence(pub, [self._control_frame(station, flags=0x01)])

        got = self._collect(received, 1)
        self.assertEqual(len(got), 1, f'expected one ACK, got {len(got)}')
        self.assertEqual(got[0].station_id, station, 'ACK went to the wrong station')
        self.assertEqual(got[0].function_code, 0x00)
        # 0x12 carries no sequence number, so acked_seq is 0 by convention.
        self.assertEqual(bytes(got[0].data), struct.pack('<HB', 0, 0x12))

        # Assert the log positively as well as negatively (the no-ACK test
        # only proves the line is absent when it should be). Without this a
        # typo in the format string would pass every other test.
        proc_output.assertWaitFor(
            expected_output=(
                f'Auto-replied ACK to station={station} for function_code=0x12, seq=0'),
            process=bridge_process, timeout=LOG_TIMEOUT)

    def test_sensor_data_ack_carries_the_frame_sequence(self):
        """A 0x10 ACK names the seq it acknowledges, not a placeholder."""
        received, pub = self._wire_up_ack()

        station = 31
        self._send_sequence(pub, [self._sensor_frame(station, seq=42, flags=0x01)])

        got = self._collect(received, 1)
        self.assertEqual(len(got), 1, f'expected one ACK, got {len(got)}')
        self.assertEqual(bytes(got[0].data), struct.pack('<HB', 42, 0x10))

    def test_no_ack_when_not_requested(self, proc_output, bridge_process):
        """flags.bit0=0 means silence: no reply frame, no reply log."""
        received, pub = self._wire_up_ack()

        station = 32
        self._send_sequence(pub, [self._sensor_frame(station, seq=7, flags=0x00)])

        # Give an unwanted ACK time to show up before declaring it absent.
        self._collect(received, 1, timeout=1.0)
        self.assertEqual(len(received), 0, f'unrequested ACK sent: {received}')

        # An implementation that ignored the flag would emit exactly this.
        self._assert_not_logged(
            proc_output, bridge_process,
            f'Auto-replied ACK to station={station} for function_code=0x10, seq=7')

    def test_undecodable_frame_requesting_ack_is_not_answered(self, proc_output,
                                                              bridge_process):
        """An unknown function code draws no ACK: its flags byte is a guess."""
        received, pub = self._wire_up_ack()

        sent = Frame()
        sent.station_id = 33
        sent.function_code = 0xFF
        sent.data = [0x01, 0xDE, 0xAD]  # byte 0 would be flags.bit0=1 if parsed

        self._send_sequence(pub, [sent])

        self._collect(received, 1, timeout=1.0)
        self.assertEqual(len(received), 0, f'ACK sent for an undecoded frame: {received}')

        proc_output.assertWaitFor(
            expected_output='Unknown or unimplemented function_code=0xFF from station=33',
            process=bridge_process, timeout=LOG_TIMEOUT)

    def test_ack_does_not_consume_the_frame(self):
        """Replying is additive: the acknowledged frame still reaches the app."""
        forwarded, pub = self._wire_up()
        acks = self._watch(DRIVER_TX, await_publisher=True)

        station = 34
        sent = self._control_frame(station, flags=0x01)
        self._send_sequence(pub, [sent])

        got = self._collect(forwarded, 1)
        self.assertEqual(len(got), 1, 'acknowledged frame was not forwarded')
        self._assert_same_frame(got[0], sent)
        self.assertEqual(len(self._collect(acks, 1)), 1, 'no ACK alongside the forward')

    def test_duplicate_frame_is_still_acknowledged(self, proc_output, bridge_process):
        """A repeat is withheld from the app but still answered on the wire."""
        received, pub = self._wire_up_ack()

        station = 35
        frame = self._sensor_frame(station, seq=1, flags=0x01)
        self._send_sequence(pub, [frame, frame])

        # The likeliest reason a peer repeats itself is that our previous ACK
        # was lost. Staying silent because we recognise the duplicate would
        # leave it retransmitting forever, so the reply precedes the drop.
        proc_output.assertWaitFor(
            expected_output=f'Duplicate seq=1 (station={station})',
            process=bridge_process, timeout=LOG_TIMEOUT)

        got = self._collect(received, 2)
        self.assertEqual(len(got), 2, f'expected an ACK for each copy, got {len(got)}')

    def test_control_commands_bypass_sequence_tracking(self, proc_output, bridge_process):
        """0x12 carries no seq, so repeats are not duplicates."""
        received, pub = self._wire_up()

        cmd = Frame()
        cmd.station_id = 26
        cmd.function_code = 0x12
        cmd.data = [0x00, 0x05]

        # The same command three times over is three legitimate commands.
        self._send_sequence(pub, [cmd, cmd, cmd])

        got = self._collect(received, 3)
        self.assertEqual(len(got), 3, f'expected 3 frames through, got {len(got)}')


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_exit_codes(self, proc_info):
        launch_testing.asserts.assertExitCodes(proc_info)
