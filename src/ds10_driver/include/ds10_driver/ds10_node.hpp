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

#ifndef DS10_DRIVER__DS10_NODE_HPP_
#define DS10_DRIVER__DS10_NODE_HPP_

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include "ds10_driver/modbus_frame_codec.hpp"
#include "ds10_driver/serial_port.hpp"
#include "ds10_interfaces/msg/frame.hpp"
#include "diagnostic_updater/diagnostic_updater.hpp"
#include "rclcpp/rclcpp.hpp"

namespace ds10_driver
{

/// DS10 transparent-link driver node. Opens one serial port and bridges it to
/// two topics: subscribing `~/tx` (application -> Modbus frame -> serial) and
/// publishing `~/rx` (serial -> decoded frame -> application). A dedicated
/// reader thread owns the blocking read + hybrid delimiter; the tx callback
/// writes under a mutex shared with the reader. Reconnects automatically on
/// link loss. Behaves as master or slave per the `role` parameter.
class Ds10Node : public rclcpp::Node
{
public:
  explicit Ds10Node(const rclcpp::NodeOptions & options);
  ~Ds10Node() override;

private:
  enum class Role { kMaster, kSlave };

  void on_tx(const ds10_interfaces::msg::Frame::SharedPtr msg);
  void reader_loop();
  void publish_frame(const DecodedFrame & frame);

  // Diagnostics: link state + noise floor + per-direction counters.
  void diagnostics(diagnostic_updater::DiagnosticStatusWrapper & stat);

  // Parameters (resolved in the constructor, immutable afterwards).
  std::string port_;
  int baud_ = 115200;
  Role role_ = Role::kMaster;
  uint8_t station_id_ = 0;
  int frame_timeout_ms_ = 20;
  std::size_t max_frame_len_ = ModbusFrameCodec::kMaxFrameLen;

  ModbusFrameCodec codec_;
  SerialPort serial_;
  std::mutex serial_mutex_;   // guards concurrent write vs the port fd

  rclcpp::Subscription<ds10_interfaces::msg::Frame>::SharedPtr tx_sub_;
  rclcpp::Publisher<ds10_interfaces::msg::Frame>::SharedPtr rx_pub_;
  std::shared_ptr<diagnostic_updater::Updater> diag_;

  std::thread reader_thread_;
  std::atomic<bool> running_{false};
  std::atomic<bool> connected_{false};

  // Counters (single reader thread writes rx/resync; tx callback writes tx).
  std::atomic<uint64_t> rx_frames_{0};
  std::atomic<uint64_t> rx_filtered_{0};
  std::atomic<uint64_t> tx_frames_{0};
  std::atomic<uint64_t> tx_rejected_{0};
  std::atomic<uint32_t> rx_seq_{0};
};

}  // namespace ds10_driver

#endif  // DS10_DRIVER__DS10_NODE_HPP_
