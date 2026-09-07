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
Launch the DS10 relay in relay role (master side).

Sends a request to slave 1, matches the reply by transaction number, then
forwards it to whichever station the slave named in the reply's dst byte. The
master holds no destination of its own: see the responder launch file for where
routing is configured. Requires a ds10_driver master node already publishing
/master/rx and subscribing /master/tx, plus a responder on slave 1.

  ros2 launch ds10_relay ds10_relay.launch.py
  ros2 launch ds10_relay ds10_relay.launch.py timeout_ms:=2000 slave1_id:=3

Trigger a transaction from another terminal:

  ros2 topic pub --once /ds10_relay/trigger std_msgs/String "{data: 'temp=25'}"
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    slave1_id = LaunchConfiguration('slave1_id')
    timeout_ms = LaunchConfiguration('timeout_ms')
    max_retries = LaunchConfiguration('max_retries')
    auto_interval_ms = LaunchConfiguration('auto_interval_ms')
    tx_topic = LaunchConfiguration('tx_topic')
    rx_topic = LaunchConfiguration('rx_topic')

    return LaunchDescription([
        DeclareLaunchArgument('slave1_id', default_value='1',
                              description='Station queried for a reply (1..247)'),
        DeclareLaunchArgument('timeout_ms', default_value='1500',
                              description='Reply timeout per attempt (measured: '
                                          '764 ms worst case at 1004 B payload)'),
        DeclareLaunchArgument('max_retries', default_value='2',
                              description='Retries after a timeout (0 disables)'),
        DeclareLaunchArgument('auto_interval_ms', default_value='0',
                              description='>0 self-triggers every N ms (soak runs)'),
        DeclareLaunchArgument('tx_topic', default_value='/master/tx',
                              description='Driver tx topic on the master side'),
        DeclareLaunchArgument('rx_topic', default_value='/master/rx',
                              description='Driver rx topic on the master side'),
        Node(
            package='ds10_relay',
            executable='relay_node',
            name='ds10_relay',
            output='screen',
            parameters=[{
                'role': 'relay',
                'slave1_id': slave1_id,
                'timeout_ms': timeout_ms,
                'max_retries': max_retries,
                'auto_interval_ms': auto_interval_ms,
                'tx_topic': tx_topic,
                'rx_topic': rx_topic,
            }],
        ),
    ])
