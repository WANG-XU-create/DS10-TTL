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

#include "ds10_driver/ds10_node.hpp"

#include <chrono>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ds10_driver
{

using namespace std::chrono_literals;

Ds10Node::Ds10Node(const rclcpp::NodeOptions & options)
: rclcpp::Node("ds10_node", options),
  codec_(ModbusFrameCodec::kMaxFrameLen)
{
  port_ = declare_parameter<std::string>("port", "/dev/ttyUSB0");
  baud_ = declare_parameter<int>("baud", 115200);
  const std::string role = declare_parameter<std::string>("role", "master");
  const int station = declare_parameter<int>("station_id", 0);
  frame_timeout_ms_ = declare_parameter<int>("frame_timeout_ms", 20);
  const int max_frame = declare_parameter<int>(
    "max_frame_bytes", static_cast<int>(ModbusFrameCodec::kMaxFrameLen));
  const std::string tx_topic = declare_parameter<std::string>("tx_topic", "~/tx");
  const std::string rx_topic = declare_parameter<std::string>("rx_topic", "~/rx");

  if (role == "master") {
    role_ = Role::kMaster;
  } else if (role == "slave") {
    role_ = Role::kSlave;
  } else {
    throw std::invalid_argument("role must be 'master' or 'slave', got: " + role);
  }

  if (role_ == Role::kSlave) {
    if (station < ModbusFrameCodec::kMinStation || station > ModbusFrameCodec::kMaxStation) {
      throw std::invalid_argument(
              "slave role requires station_id in 1..247, got: " + std::to_string(station));
    }
    station_id_ = static_cast<uint8_t>(station);
  }

  if (max_frame < static_cast<int>(ModbusFrameCodec::kMinFrameLen) ||
    max_frame > static_cast<int>(ModbusFrameCodec::kMaxFrameLen))
  {
    throw std::invalid_argument(
            "max_frame_bytes must be in 4..4095, got: " + std::to_string(max_frame));
  }
  max_frame_len_ = static_cast<std::size_t>(max_frame);
  codec_ = ModbusFrameCodec(max_frame_len_);

  rx_pub_ = create_publisher<ds10_interfaces::msg::Frame>(rx_topic, rclcpp::QoS(10));
  tx_sub_ = create_subscription<ds10_interfaces::msg::Frame>(
    tx_topic, rclcpp::QoS(10),
    std::bind(&Ds10Node::on_tx, this, std::placeholders::_1));

  diag_ = std::make_shared<diagnostic_updater::Updater>(this);
  diag_->setHardwareID(port_);
  diag_->add("ds10_link", this, &Ds10Node::diagnostics);

  RCLCPP_INFO(
    get_logger(),
    "DS10 node: port=%s baud=%d role=%s station_id=%d frame_timeout=%dms max_frame=%zu",
    port_.c_str(), baud_, role.c_str(), station_id_, frame_timeout_ms_, max_frame_len_);

  running_ = true;
  reader_thread_ = std::thread(&Ds10Node::reader_loop, this);
}

Ds10Node::~Ds10Node()
{
  running_ = false;
  if (reader_thread_.joinable()) {
    reader_thread_.join();
  }
  std::lock_guard<std::mutex> lock(serial_mutex_);
  serial_.close();
}

// on_tx / reader_loop / publish_frame / diagnostics defined in the next chunk.
// DS10_NODE_IMPL_PLACEHOLDER

void Ds10Node::on_tx(const ds10_interfaces::msg::Frame::SharedPtr msg)
{
  // Slave uses its configured station; master honours the target in the message.
  const uint8_t station = (role_ == Role::kSlave) ? station_id_ : msg->station_id;

  auto frame = codec_.encode(station, msg->function_code, msg->data);
  if (!frame.has_value()) {
    ++tx_rejected_;
    RCLCPP_WARN(
      get_logger(),
      "tx rejected: data %zu B exceeds single-frame cap (max_frame_bytes=%zu)",
      msg->data.size(), max_frame_len_);
    return;
  }

  std::lock_guard<std::mutex> lock(serial_mutex_);
  if (!connected_ || !serial_.write(frame->data(), frame->size())) {
    RCLCPP_WARN_THROTTLE(
      get_logger(), *get_clock(), 2000,
      "tx dropped: link down (%s)", serial_.last_error().c_str());
    return;
  }
  ++tx_frames_;
}

void Ds10Node::reader_loop()
{
  using clock = std::chrono::steady_clock;
  std::vector<uint8_t> chunk;
  auto last_rx = clock::now();
  bool have_pending = false;

  while (running_) {
    if (!connected_) {
      std::lock_guard<std::mutex> lock(serial_mutex_);
      if (serial_.open(port_, baud_)) {
        connected_ = true;
        codec_.flush_partial();
        have_pending = false;
        RCLCPP_INFO(get_logger(), "serial connected: %s", port_.c_str());
      } else {
        RCLCPP_WARN_THROTTLE(
          get_logger(), *get_clock(), 3000,
          "serial connect failed: %s", serial_.last_error().c_str());
      }
      if (!connected_) {
        std::this_thread::sleep_for(500ms);
        continue;
      }
    }

    chunk.clear();
    ReadStatus status;
    {
      std::lock_guard<std::mutex> lock(serial_mutex_);
      status = serial_.read(chunk);
    }
    if (status == ReadStatus::kDisconnected) {
      RCLCPP_WARN(get_logger(), "serial disconnected: %s", serial_.last_error().c_str());
      std::lock_guard<std::mutex> lock(serial_mutex_);
      serial_.close();
      connected_ = false;
      continue;
    }

    if (!chunk.empty()) {
      auto frames = codec_.feed(chunk.data(), chunk.size());
      for (const auto & f : frames) {
        publish_frame(f);
      }
      last_rx = clock::now();
      have_pending = codec_.buffered() > 0;
    } else {
      // Burst-end: after frame_timeout_ms of silence, drop any un-pairable
      // trailing bytes and resynchronise (hybrid delimiter coarse split).
      if (have_pending && codec_.buffered() > 0) {
        const auto idle = std::chrono::duration_cast<std::chrono::milliseconds>(
          clock::now() - last_rx).count();
        if (idle >= frame_timeout_ms_) {
          codec_.flush_partial();
          have_pending = false;
        }
      }
      std::this_thread::sleep_for(2ms);
    }
  }
}

void Ds10Node::publish_frame(const DecodedFrame & frame)
{
  // Slave-side filter: only surface frames addressed to this station. Master
  // accepts every source station (that is how it tells slaves apart).
  if (role_ == Role::kSlave && frame.station != station_id_) {
    ++rx_filtered_;
    return;
  }

  ds10_interfaces::msg::Frame msg;
  msg.header.stamp = now();
  msg.header.frame_id = port_;
  // Master RX: source slave station. Slave RX: 0 means "from master".
  msg.station_id = (role_ == Role::kMaster) ? frame.station : 0;
  msg.function_code = frame.function_code;
  msg.data = frame.data;
  msg.rx_seq = ++rx_seq_;
  rx_pub_->publish(msg);
  ++rx_frames_;
}

void Ds10Node::diagnostics(diagnostic_updater::DiagnosticStatusWrapper & stat)
{
  if (connected_) {
    stat.summary(diagnostic_msgs::msg::DiagnosticStatus::OK, "connected");
  } else {
    stat.summary(diagnostic_msgs::msg::DiagnosticStatus::ERROR, "disconnected");
  }
  stat.add("port", port_);
  stat.add("role", role_ == Role::kMaster ? "master" : "slave");
  stat.add("rx_frames", static_cast<int>(rx_frames_.load()));
  stat.add("rx_filtered", static_cast<int>(rx_filtered_.load()));
  stat.add("tx_frames", static_cast<int>(tx_frames_.load()));
  stat.add("tx_rejected", static_cast<int>(tx_rejected_.load()));
  // Link noise floor: bytes discarded during resynchronisation (ticket 03).
  stat.add("resync_dropped_bytes", static_cast<int>(codec_.resync_dropped()));
}

}  // namespace ds10_driver
