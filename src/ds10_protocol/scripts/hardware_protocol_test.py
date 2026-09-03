#!/usr/bin/env python3
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
End-to-end protocol test over two real DS10 radios.

DS10 radios in transparent mode exhibit a strong echo / loopback: every frame
sent by either side is received by BOTH sides, including the sender. This is
not a bug -- it is the radio's normal operating mode. The protocol bridge's
sequence tracker treats the echo copies as duplicates (per §帧去留清单 row 6),
so the test asserts that the *desired behaviour* happened (e.g. at least one
ACK was auto-replied, the duplicate was detected, the frame was forwarded)
rather than asserting exact frame counts.

Usage:
  python3 hardware_protocol_test.py --master-port /dev/ttyUSB0 \
      --slave-port /dev/ttyUSB1 --slave-station 2
"""

import argparse
import os
import re
import signal
import struct
import subprocess
import sys
import tempfile
import time

import rclpy
from rclpy.node import Node
from ds10_interfaces.msg import Frame

DISCOVERY_TIMEOUT = 15.0
SETTLE = 0.5


def sensor_data(flags, seq, sensor_id, reading):
    return list(struct.pack('<BHBf', flags, seq, sensor_id, reading))


def control_command(flags, cmd_id, params=b''):
    return list(bytes([flags, cmd_id]) + params)


class Stack:

    def __init__(self, master_port, slave_port, slave_station):
        self.master_port = master_port
        self.slave_port = slave_port
        self.slave_station = slave_station
        self.procs = []
        self.logs = {}
        self._files = []

    def _spawn(self, name, args):
        handle = tempfile.NamedTemporaryFile(
            mode='w+', suffix=f'.{name}.log', delete=False)
        self._files.append(handle)
        self.logs[name] = handle.name
        proc = subprocess.Popen(
            args, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        self.procs.append(proc)
        return proc

    def start(self):
        self._spawn('master_driver', [
            'ros2', 'run', 'ds10_driver', 'ds10_node', '--ros-args',
            '-p', f'port:={self.master_port}', '-p', 'role:=master',
            '-r', '__node:=ds10_master'])
        self._spawn('slave_driver', [
            'ros2', 'run', 'ds10_driver', 'ds10_node', '--ros-args',
            '-p', f'port:={self.slave_port}', '-p', 'role:=slave',
            '-p', f'station_id:={self.slave_station}',
            '-r', '__node:=ds10_slave'])
        self._spawn('master_bridge', [
            'ros2', 'run', 'ds10_protocol', 'protocol_bridge', '--ros-args',
            '-p', 'driver_rx_topic:=/ds10_master/rx',
            '-p', 'driver_tx_topic:=/ds10_master/tx',
            '-p', 'protocol_rx_topic:=/master/protocol/rx',
            '-p', 'protocol_tx_topic:=/master/protocol/tx',
            '-r', '__node:=master_bridge'])
        self._spawn('slave_bridge', [
            'ros2', 'run', 'ds10_protocol', 'protocol_bridge', '--ros-args',
            '-p', 'driver_rx_topic:=/ds10_slave/rx',
            '-p', 'driver_tx_topic:=/ds10_slave/tx',
            '-p', 'protocol_rx_topic:=/slave/protocol/rx',
            '-p', 'protocol_tx_topic:=/slave/protocol/tx',
            '-r', '__node:=slave_bridge'])

    def stop(self):
        for proc in self.procs:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
        deadline = time.time() + 5.0
        for proc in self.procs:
            remaining = max(0.1, deadline - time.time())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()
        for handle in self._files:
            handle.flush()

    def log_text(self, name):
        with open(self.logs[name]) as f:
            return f.read()

    def died(self):
        return [n for n, p in zip(self.logs, self.procs) if p.poll() is not None]


class Peer(Node):

    def __init__(self):
        super().__init__('hardware_test_peer')
        self.master_rx = []
        self.slave_rx = []
        self.create_subscription(
            Frame, '/master/protocol/rx', self.master_rx.append, 10)
        self.create_subscription(
            Frame, '/slave/protocol/rx', self.slave_rx.append, 10)
        self.master_tx = self.create_publisher(Frame, '/master/protocol/tx', 10)
        self.slave_tx = self.create_publisher(Frame, '/slave/protocol/tx', 10)

    def spin(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.05)

    def wait(self):
        end = time.time() + DISCOVERY_TIMEOUT
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.1)
            ready = (self.count_publishers('/master/protocol/rx') >= 1
                     and self.count_publishers('/slave/protocol/rx') >= 1
                     and self.master_tx.get_subscription_count() >= 1
                     and self.slave_tx.get_subscription_count() >= 1)
            if ready:
                self.spin(1.0)
                return True
        return False

    def send(self, publisher, station, function_code, data):
        msg = Frame()
        msg.station_id = station
        msg.function_code = function_code
        msg.data = list(data)
        publisher.publish(msg)
        self.spin(SETTLE)


class Report:

    def __init__(self):
        self.rows = []

    def record(self, name, passed, detail, partial=False):
        verdict = 'PARTIAL' if partial else ('PASS' if passed else 'FAIL')
        self.rows.append((name, verdict, detail))
        print(f'[{verdict:^7}] {name}')
        for line in detail.splitlines():
            print(f'          {line}')

    def ok(self):
        return all(v == 'PASS' for _, v, _ in self.rows)


def s1_sensor_upstream(peer, stack, report):
    # Warm the radio link. The first frame after the stack comes up is
    # routinely lost while the DS10 pair completes its association -- the
    # earlier version of this test sent seq=1 into that window and read the
    # loss as a protocol failure. Use a seq far from the ones under test so
    # a surviving warm-up frame cannot be mistaken for one of them.
    peer.send(peer.slave_tx, 2, 0x10, sensor_data(0, 900, 3, 0.0))
    peer.spin(1.5)

    peer.master_rx.clear()
    before = stack.log_text('master_bridge')
    for seq in (1, 2, 3):
        peer.send(peer.slave_tx, 2, 0x10, sensor_data(0, seq, 3, 23.5))
    peer.spin(3.0)
    log = stack.log_text('master_bridge')[len(before):]
    unique = sorted(set(re.findall(
        r'Decoded 0x10: flags=0, seq=(\d+), sensor_id=3, reading=23\.500000', log)))
    dups = re.findall(r'Duplicate seq=(\d+) \(station=2\)', log)
    # Only 900 -> 1 counts as a gap here, and it is one the test itself
    # caused by rewinding the sequence; 1 -> 2 -> 3 must be clean.
    gaps = re.findall(r'Gap detected: expected seq=(\d+), got seq=(\d+)', log)
    consecutive_gaps = [g for g in gaps if g != ('901', '1')]
    detail = (f'unique seqs decoded: {unique} (expected [1, 2, 3])\n'
              f'duplicates: {dups} (echo copies)\n'
              f'gaps within 1,2,3: {consecutive_gaps} (expected none)\n'
              f'all gaps incl. the test rewind 900->1: {gaps}')
    return report.record('S1 sensor data upstream',
                         unique == ['1', '2', '3'] and not consecutive_gaps, detail)


def s2_control_and_ack(peer, stack, report):
    peer.slave_rx.clear()
    peer.master_rx.clear()
    before_slave = stack.log_text('slave_bridge')
    peer.send(peer.master_tx, 2, 0x12, control_command(0x01, 5, b'\xAA\xBB'))
    peer.spin(3.0)
    slave_log = stack.log_text('slave_bridge')[len(before_slave):]
    decoded = 'Decoded 0x12: flags=1, cmd_id=5, params_len=2' in slave_log
    replies = re.findall(r'Auto-replied ACK to.*function_code=0x12, seq=0', slave_log)
    master_acks = [f for f in peer.master_rx if f.function_code == 0x00]
    detail = (f'slave decoded 0x12: {decoded}\n'
              f'ACK replies sent: {len(replies)} (>=1 confirms the feature)\n'
              f'ACK frames back at master: {len(master_acks)}')
    core = decoded and len(replies) >= 1
    return report.record('S2 control command downstream + ACK', core, detail)


def s3_gaps(peer, stack, report):
    peer.master_rx.clear()
    peer.send(peer.slave_tx, 2, 0x10, sensor_data(0, 9, 3, 1.0))
    peer.spin(1.0)
    peer.master_rx.clear()
    before = stack.log_text('master_bridge')
    for seq in (10, 12, 14):
        peer.send(peer.slave_tx, 2, 0x10, sensor_data(0, seq, 3, 1.0))
    peer.spin(3.0)
    added = stack.log_text('master_bridge')[len(before):]
    gaps = re.findall(r'Gap detected: expected seq=(\d+), got seq=(\d+)', added)
    expected = [('11', '12'), ('13', '14')]
    detail = (f'gaps reported: {gaps}\n'
              f'gaps expected: {expected}')
    return report.record('S3 sequence gap detection', gaps == expected, detail)


def s4_duplicate(peer, stack, report):
    peer.send(peer.slave_tx, 2, 0x10, sensor_data(0, 19, 3, 5.0))
    peer.spin(1.0)
    peer.master_rx.clear()
    before = stack.log_text('master_bridge')
    peer.send(peer.slave_tx, 2, 0x10, sensor_data(0, 20, 3, 5.0))
    peer.send(peer.slave_tx, 2, 0x10, sensor_data(0, 20, 3, 5.0))
    peer.send(peer.slave_tx, 2, 0x10, sensor_data(0, 21, 3, 6.0))
    peer.spin(3.0)
    added = stack.log_text('master_bridge')[len(before):]
    warned = 'Duplicate seq=20 (station=2)' in added
    spurious_gaps = re.findall(r'Gap detected: expected seq=(\d+), got seq=(\d+)', added)
    detail = (f'duplicate seq=20 logged: {warned}\n'
              f'spurious gaps: {spurious_gaps} (expected none)')
    return report.record('S4 duplicate frame dropped', warned and not spurious_gaps, detail)


def s5_unknown_function(peer, stack, report):
    peer.slave_rx.clear()
    before = stack.log_text('slave_bridge')
    peer.send(peer.master_tx, 2, 0xFF, [0xDE, 0xAD])
    peer.spin(2.0)
    added = stack.log_text('slave_bridge')[len(before):]
    warned = bool(re.search(
        r'Unknown or unimplemented function_code=0xFF from station=\d+', added))
    return report.record('S5 unknown function code', warned, f'warned: {warned}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master-port', default='/dev/ttyUSB0')
    parser.add_argument('--slave-port', default='/dev/ttyUSB1')
    parser.add_argument('--slave-station', type=int, default=2)
    args = parser.parse_args()
    for port in (args.master_port, args.slave_port):
        if not os.path.exists(port):
            print(f'no such serial device: {port}', file=sys.stderr)
            return 2
    stack = Stack(args.master_port, args.slave_port, args.slave_station)
    report = Report()
    rclpy.init()
    peer = Peer()
    try:
        print(f'starting stack: master={args.master_port} '
              f'slave={args.slave_port} station={args.slave_station}\n')
        stack.start()
        if not peer.wait():
            print('discovery failed', file=sys.stderr)
            return 2
        if stack.died():
            print(f'process(es) died: {stack.died()}', file=sys.stderr)
            return 2
        s1_sensor_upstream(peer, stack, report)
        s2_control_and_ack(peer, stack, report)
        s3_gaps(peer, stack, report)
        s4_duplicate(peer, stack, report)
        s5_unknown_function(peer, stack, report)
        print('\n' + '=' * 62)
        for name, verdict, _ in report.rows:
            print(f'{verdict:>8}  {name}')
        print('=' * 62)
        print('logs:')
        for name, path in stack.logs.items():
            print(f'  {name}: {path}')
        return 0 if report.ok() else 1
    finally:
        stack.stop()
        peer.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
