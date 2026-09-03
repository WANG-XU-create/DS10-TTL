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
Launch the application-protocol bridge.

Defaults assume a driver node publishing on /ds10_driver/rx and subscribing on
/ds10_driver/tx. Point the bridge at a differently-named driver instance by
overriding the topic arguments, for example:

  ros2 launch ds10_protocol protocol_bridge.launch.py driver_rx_topic:=/ds10_master/rx
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    driver_rx_topic = LaunchConfiguration('driver_rx_topic')
    driver_tx_topic = LaunchConfiguration('driver_tx_topic')
    protocol_rx_topic = LaunchConfiguration('protocol_rx_topic')
    protocol_tx_topic = LaunchConfiguration('protocol_tx_topic')

    return LaunchDescription([
        DeclareLaunchArgument('driver_rx_topic', default_value='/ds10_driver/rx',
                              description='Driver topic the bridge reads device frames from'),
        DeclareLaunchArgument('driver_tx_topic', default_value='/ds10_driver/tx',
                              description='Driver topic the bridge writes device frames to'),
        DeclareLaunchArgument('protocol_rx_topic', default_value='/protocol/rx',
                              description='Topic the bridge publishes frames to applications on'),
        DeclareLaunchArgument('protocol_tx_topic', default_value='/protocol/tx',
                              description='Topic the bridge accepts frames from applications on'),
        Node(
            package='ds10_protocol',
            executable='protocol_bridge',
            name='protocol_bridge',
            output='screen',
            parameters=[{
                'driver_rx_topic': driver_rx_topic,
                'driver_tx_topic': driver_tx_topic,
                'protocol_rx_topic': protocol_rx_topic,
                'protocol_tx_topic': protocol_tx_topic,
            }],
        ),
    ])
