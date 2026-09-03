// Copyright 2026 wangxu
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "ds10_protocol/protocol_bridge_node.hpp"

#include <string>

namespace ds10_protocol
{

namespace
{
// Matches the depth ds10_driver uses on its own tx/rx topics.
constexpr int kQueueDepth = 10;
}  // namespace

ProtocolBridgeNode::ProtocolBridgeNode(const rclcpp::NodeOptions & options)
: rclcpp::Node("protocol_bridge", options)
{
  driver_rx_topic_ = declare_parameter<std::string>("driver_rx_topic", "/ds10_driver/rx");
  driver_tx_topic_ = declare_parameter<std::string>("driver_tx_topic", "/ds10_driver/tx");
  protocol_rx_topic_ = declare_parameter<std::string>("protocol_rx_topic", "/protocol/rx");
  protocol_tx_topic_ = declare_parameter<std::string>("protocol_tx_topic", "/protocol/tx");

  // Publishers first: creating them before the subscriptions means a Frame
  // arriving on the very first callback already has somewhere to go.
  protocol_rx_pub_ = create_publisher<ds10_interfaces::msg::Frame>(
    protocol_rx_topic_, rclcpp::QoS(kQueueDepth));
  driver_tx_pub_ = create_publisher<ds10_interfaces::msg::Frame>(
    driver_tx_topic_, rclcpp::QoS(kQueueDepth));

  driver_rx_sub_ = create_subscription<ds10_interfaces::msg::Frame>(
    driver_rx_topic_, rclcpp::QoS(kQueueDepth),
    [this](const ds10_interfaces::msg::Frame::SharedPtr msg) {on_driver_rx(msg);});
  protocol_tx_sub_ = create_subscription<ds10_interfaces::msg::Frame>(
    protocol_tx_topic_, rclcpp::QoS(kQueueDepth),
    [this](const ds10_interfaces::msg::Frame::SharedPtr msg) {on_protocol_tx(msg);});

  RCLCPP_INFO(
    get_logger(), "Protocol bridge up: %s -> %s (device to app), %s -> %s (app to device)",
    driver_rx_topic_.c_str(), protocol_rx_topic_.c_str(),
    protocol_tx_topic_.c_str(), driver_tx_topic_.c_str());
}

void ProtocolBridgeNode::on_driver_rx(const ds10_interfaces::msg::Frame::SharedPtr msg)
{
  // Transparent for now; ticket 06 decodes Frame.data here.
  protocol_rx_pub_->publish(*msg);
}

void ProtocolBridgeNode::on_protocol_tx(const ds10_interfaces::msg::Frame::SharedPtr msg)
{
  driver_tx_pub_->publish(*msg);
}

}  // namespace ds10_protocol
