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
Launch a DS10 driver in master role.

The master routes tx Frames to the target slave by station_id and tags every
rx Frame with its source slave station. Override the serial port on the command
line, e.g.:

  ros2 launch ds10_driver ds10_master.launch.py port:=/dev/ttyUSB0
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    port = LaunchConfiguration('port')
    baud = LaunchConfiguration('baud')

    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB0',
                              description='DS10 master serial device'),
        DeclareLaunchArgument('baud', default_value='115200',
                              description='Serial baud rate (8N1)'),
        Node(
            package='ds10_driver',
            executable='ds10_node',
            name='ds10_master',
            output='screen',
            parameters=[{
                'port': port,
                'baud': baud,
                'role': 'master',
            }],
        ),
    ])
