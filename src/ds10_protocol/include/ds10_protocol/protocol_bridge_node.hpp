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

#ifndef DS10_PROTOCOL__PROTOCOL_BRIDGE_NODE_HPP_
#define DS10_PROTOCOL__PROTOCOL_BRIDGE_NODE_HPP_

#include <optional>
#include <string>
#include <variant>

#include "ds10_interfaces/msg/frame.hpp"
#include "ds10_protocol/codec.hpp"
#include "ds10_protocol/seq_tracker.hpp"
#include "rclcpp/rclcpp.hpp"

namespace ds10_protocol
{

/// A `Frame.data` payload decoded according to its function code.
///
/// Holds whichever message type the function code selected. Callers switch on
/// the alternative rather than re-reading `function_code`, so a decoded frame
/// cannot be misinterpreted as the wrong type.
using DecodedPayload = std::variant<ControlCommand, SensorData>;

/// Application-protocol bridge sitting between ds10_driver and business nodes.
///
/// Frames are forwarded in both directions unchanged, with one exception:
/// duplicate sequence numbers on a sensor stream are dropped, because handing
/// the same reading to an application twice is actively wrong rather than
/// merely uninformative. Everything else -- malformed payloads, unknown
/// function codes, detected gaps -- is logged and still forwarded, so
/// applications that parse `data` themselves keep working.
/// application_protocol_v1.md §帧去留清单 is the authoritative table.
///
///   driver_rx_topic  --> [bridge] --> protocol_rx_topic   (device to app)
///   protocol_tx_topic --> [bridge] --> driver_tx_topic    (app to device)
class ProtocolBridgeNode : public rclcpp::Node
{
public:
  explicit ProtocolBridgeNode(const rclcpp::NodeOptions & options);

private:
  void on_driver_rx(const ds10_interfaces::msg::Frame::SharedPtr msg);
  void on_protocol_tx(const ds10_interfaces::msg::Frame::SharedPtr msg);

  /// Decode `msg.data` according to its function code.
  ///
  /// Returns nullopt both for function codes this version has no decoder for
  /// and for payloads a decoder rejected; the two cases are distinguished in
  /// the log, at WARN and ERROR respectively.
  std::optional<DecodedPayload> decode_frame(const ds10_interfaces::msg::Frame & msg);

  /// Log an already-decoded payload at INFO.
  void log_payload(const ds10_interfaces::msg::Frame & msg, const DecodedPayload & payload);

  /// Run sequence tracking for payloads that carry a sequence number.
  ///
  /// @return false when the frame is a duplicate and must not be forwarded.
  ///         Payloads without a sequence number always return true.
  bool track_sequence(
    const ds10_interfaces::msg::Frame & msg, const DecodedPayload & payload);

  // Topic names (resolved in the constructor, immutable afterwards).
  std::string driver_rx_topic_;
  std::string driver_tx_topic_;
  std::string protocol_rx_topic_;
  std::string protocol_tx_topic_;

  rclcpp::Subscription<ds10_interfaces::msg::Frame>::SharedPtr driver_rx_sub_;
  rclcpp::Subscription<ds10_interfaces::msg::Frame>::SharedPtr protocol_tx_sub_;
  rclcpp::Publisher<ds10_interfaces::msg::Frame>::SharedPtr protocol_rx_pub_;
  rclcpp::Publisher<ds10_interfaces::msg::Frame>::SharedPtr driver_tx_pub_;

  /// Expected sequence number per (station_id, function_code) stream.
  ///
  /// Entries are never evicted. The key space is bounded by the deployment --
  /// at most 15 slaves times a handful of numbered message types -- so the
  /// table stays tiny over an arbitrarily long run. It would only need
  /// eviction if station ids became transient.
  SeqTrackerTable seq_trackers_;
};

}  // namespace ds10_protocol

#endif  // DS10_PROTOCOL__PROTOCOL_BRIDGE_NODE_HPP_
