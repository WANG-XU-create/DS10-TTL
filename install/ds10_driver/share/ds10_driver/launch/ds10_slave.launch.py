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
Launch a DS10 driver in slave role.

A slave stamps every tx Frame with its own station_id and only surfaces rx
Frames addressed to that station. station_id is required. Example:

  ros2 launch ds10_driver ds10_slave.launch.py port:=/dev/ttyUSB1 station_id:=1
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    port = LaunchConfiguration('port')
    baud = LaunchConfiguration('baud')
    station_id = LaunchConfiguration('station_id')

    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='/dev/ttyUSB1',
                              description='DS10 slave serial device'),
        DeclareLaunchArgument('baud', default_value='115200',
                              description='Serial baud rate (8N1)'),
        DeclareLaunchArgument('station_id', default_value='1',
                              description='This slave Modbus station id (1..247)'),
        Node(
            package='ds10_driver',
            executable='ds10_node',
            name='ds10_slave',
            output='screen',
            parameters=[{
                'port': port,
                'baud': baud,
                'role': 'slave',
                'station_id': station_id,
            }],
        ),
    ])
