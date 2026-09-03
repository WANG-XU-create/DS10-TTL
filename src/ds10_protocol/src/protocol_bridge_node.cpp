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

#include <optional>
#include <string>
#include <utility>
#include <variant>

#include "ds10_protocol/codec.hpp"
#include "ds10_protocol/protocol_constants.hpp"

namespace ds10_protocol
{

namespace
{
// Matches the depth ds10_driver uses on its own tx/rx topics.
constexpr int kQueueDepth = 10;

// Smallest payload each decoder accepts, reported when one rejects a frame.
constexpr size_t kMinControlCommandSize = SIZEOF_FLAGS + SIZEOF_CMD_ID;
constexpr size_t kMinSensorDataSize =
  SIZEOF_FLAGS + SIZEOF_SEQ + SIZEOF_SENSOR_ID + SIZEOF_READING;
}  // namespace

ProtocolBridgeNode::ProtocolBridgeNode(const rclcpp::NodeOptions & options)
: rclcpp::Node("protocol_bridge", options)
{
  // Defaults follow the spec. Note the driver owns *private* topics, so its
  // node name decides the real names (a driver launched as `ds10_master`
  // publishes /ds10_master/rx). protocol_bridge.launch.py derives these from a
  // `driver_name` argument; set the parameters directly when launching by hand.
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
  const auto payload = decode_frame(*msg);
  if (payload) {
    log_payload(*msg, *payload);
  }

  // Forward regardless of what decoding found: subscribers that parse `data`
  // themselves must keep receiving every frame the driver delivered.
  // See application_protocol_v1.md §错误处理.
  protocol_rx_pub_->publish(*msg);
}

std::optional<DecodedPayload> ProtocolBridgeNode::decode_frame(
  const ds10_interfaces::msg::Frame & msg)
{
  switch (msg.function_code) {
    case FUNC_CONTROL_CMD: {
        auto cmd = decode_control_command(msg.data);
        if (!cmd) {
          RCLCPP_ERROR(
            get_logger(),
            "Failed to decode function_code=0x%02X: data size=%zu (expected >=%zu)",
            msg.function_code, msg.data.size(), kMinControlCommandSize);
          return std::nullopt;
        }
        return DecodedPayload{std::move(*cmd)};
      }

    case FUNC_SENSOR_DATA: {
        auto sensor = decode_sensor_data(msg.data);
        if (!sensor) {
          RCLCPP_ERROR(
            get_logger(),
            "Failed to decode function_code=0x%02X: data size=%zu (expected >=%zu)",
            msg.function_code, msg.data.size(), kMinSensorDataSize);
          return std::nullopt;
        }
        return DecodedPayload{std::move(*sensor)};
      }

    default:
      // Includes codes this version has no decoder for (0x00 ACK, 0x11 log,
      // 0x80 fragment) as well as genuinely unknown ones.
      RCLCPP_WARN(
        get_logger(), "Unknown or unimplemented function_code=0x%02X from station=%u",
        msg.function_code, msg.station_id);
      return std::nullopt;
  }
}

void ProtocolBridgeNode::log_payload(
  const ds10_interfaces::msg::Frame & msg, const DecodedPayload & payload)
{
  if (const auto * cmd = std::get_if<ControlCommand>(&payload)) {
    RCLCPP_INFO(
      get_logger(), "Decoded 0x%02X: flags=%u, cmd_id=%u, params_len=%zu",
      msg.function_code, cmd->flags, cmd->cmd_id, cmd->params.size());
  } else if (const auto * sensor = std::get_if<SensorData>(&payload)) {
    RCLCPP_INFO(
      get_logger(), "Decoded 0x%02X: flags=%u, seq=%u, sensor_id=%u, reading=%f",
      msg.function_code, sensor->flags, sensor->seq, sensor->sensor_id, sensor->reading);
  }
}

void ProtocolBridgeNode::on_protocol_tx(const ds10_interfaces::msg::Frame::SharedPtr msg)
{
  driver_tx_pub_->publish(*msg);
}

}  // namespace ds10_protocol
