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
r"""
Launch the DS10 relay in responder role (slave side).

Answers requests on the driver's rx topic, choosing the forwarding target from
the payload via the route_map table. This is the only place forwarding routes
are configured: the master reads the target out of each reply and never
overrides it, so a new destination needs no master-side change.

  ros2 launch ds10_relay ds10_responder.launch.py route_map:="temp:2,humid:3"

  # Chinese keywords work too (matching is on UTF-8 bytes)
  ros2 launch ds10_relay ds10_responder.launch.py route_map:="温度:2,湿度:3"

  # Another slave's topics
  ros2 launch ds10_relay ds10_responder.launch.py \
      tx_topic:=/slave3/tx rx_topic:=/slave3/rx
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    route_map = LaunchConfiguration('route_map')
    default_dst = LaunchConfiguration('default_dst')
    tx_topic = LaunchConfiguration('tx_topic')
    rx_topic = LaunchConfiguration('rx_topic')

    return LaunchDescription([
        DeclareLaunchArgument('route_map', default_value='temp:2,humid:3',
                              description='"keyword:station,..." picking the '
                                          'forward target from the payload; '
                                          'first match wins'),
        DeclareLaunchArgument('default_dst', default_value='0',
                              description='Target when no keyword matches; '
                                          '0 means reply but do not forward'),
        DeclareLaunchArgument('tx_topic', default_value='/slave1/tx',
                              description='Driver tx topic on this slave'),
        DeclareLaunchArgument('rx_topic', default_value='/slave1/rx',
                              description='Driver rx topic on this slave'),
        Node(
            package='ds10_relay',
            executable='relay_node',
            name='ds10_responder',
            output='screen',
            parameters=[{
                'role': 'responder',
                'route_map': route_map,
                'default_dst': default_dst,
                'tx_topic': tx_topic,
                'rx_topic': rx_topic,
            }],
        ),
    ])
