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

#include "ds10_relay/relay_node.hpp"

#include <algorithm>
#include <cinttypes>
#include <chrono>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ds10_relay
{

using namespace std::chrono_literals;

namespace
{
/// Modbus station ids are 1..247; 0 is broadcast and 248..255 are reserved.
/// The driver's decoder only accepts a leading byte in this range, so a frame
/// addressed outside it is written to the port but can never be decoded —
/// silently black-holed. Reject such a configuration at startup instead.
uint8_t checked_station(int value, const std::string & name)
{
  if (value < transaction::kMinStation || value > transaction::kMaxStation) {
    throw std::invalid_argument(
            name + " must be in 1..247 (Modbus station id), got: " + std::to_string(value));
  }
  return static_cast<uint8_t>(value);
}

/// Render a payload for logs: printable ASCII as-is, anything else escaped.
/// Keeps a binary payload from spraying control characters at the terminal.
std::string preview(const std::vector<uint8_t> & payload, std::size_t limit = 48)
{
  std::string out;
  const std::size_t n = std::min(payload.size(), limit);
  for (std::size_t i = 0; i < n; ++i) {
    const uint8_t c = payload[i];
    if (c >= 0x20 && c < 0x7F) {
      out.push_back(static_cast<char>(c));
    } else if (c >= 0x80) {
      out.push_back(static_cast<char>(c));   // pass UTF-8 multibyte through
    } else {
      out += '.';
    }
  }
  if (payload.size() > n) {
    out += "...";
  }
  return out;
}
}  // namespace

RelayNode::RelayNode(const rclcpp::NodeOptions & options)
: rclcpp::Node("ds10_relay", options)
{
  const std::string role = declare_parameter<std::string>("role", "relay");
  const int slave1 = declare_parameter<int>("slave1_id", 1);
  const int function_code = declare_parameter<int>("function_code", 0x10);
  const int timeout_ms = declare_parameter<int>("timeout_ms", 1500);
  max_retries_ = declare_parameter<int>("max_retries", 2);
  const int auto_interval_ms = declare_parameter<int>("auto_interval_ms", 0);
  const int stats_interval_ms = declare_parameter<int>("stats_interval_ms", 5000);
  const std::string tx_topic = declare_parameter<std::string>("tx_topic", "/master/tx");
  const std::string rx_topic = declare_parameter<std::string>("rx_topic", "/master/rx");
  const std::string trigger_topic =
    declare_parameter<std::string>("trigger_topic", "~/trigger");
  const std::string auto_payload =
    declare_parameter<std::string>("auto_payload", "ds10_relay auto probe");
  // Responder-side routing: "keyword:station,keyword:station,...". The slave
  // owns this decision, so the master never needs to know the destinations.
  const std::string route_map = declare_parameter<std::string>("route_map", "");
  const int default_dst = declare_parameter<int>("default_dst", 0);

  if (role == "relay") {
    role_ = Role::kRelay;
  } else if (role == "responder") {
    role_ = Role::kResponder;
  } else {
    throw std::invalid_argument("role must be 'relay' or 'responder', got: " + role);
  }

  if (timeout_ms <= 0) {
    throw std::invalid_argument(
            "timeout_ms must be positive, got: " + std::to_string(timeout_ms));
  }
  timeout_ = std::chrono::milliseconds(timeout_ms);

  if (max_retries_ < 0) {
    throw std::invalid_argument(
            "max_retries must be >= 0, got: " + std::to_string(max_retries_));
  }
  if (function_code < 0 || function_code > 0xFF) {
    throw std::invalid_argument(
            "function_code must be in 0..255, got: " + std::to_string(function_code));
  }
  function_code_ = static_cast<uint8_t>(function_code);

  if (role_ == Role::kRelay) {
    // The relay only needs to know who to ask; where the answer goes is the
    // slave's call, carried in the reply.
    slave1_id_ = checked_station(slave1, "slave1_id");
  } else {
    // 0 is the legal "do not forward" default; any other value must address a
    // real station.
    if (default_dst != transaction::kNoForward) {
      default_dst_ = checked_station(default_dst, "default_dst");
    }
    routes_ = parse_route_map(route_map);
  }

  tx_pub_ = create_publisher<ds10_interfaces::msg::Frame>(tx_topic, rclcpp::QoS(10));
  rx_sub_ = create_subscription<ds10_interfaces::msg::Frame>(
    rx_topic, rclcpp::QoS(10),
    std::bind(&RelayNode::on_rx, this, std::placeholders::_1));

  if (role_ == Role::kRelay) {
    trigger_sub_ = create_subscription<std_msgs::msg::String>(
      trigger_topic, rclcpp::QoS(10),
      std::bind(&RelayNode::on_trigger, this, std::placeholders::_1));

    if (auto_interval_ms > 0) {
      const std::vector<uint8_t> payload(auto_payload.begin(), auto_payload.end());
      auto_timer_ = create_wall_timer(
        std::chrono::milliseconds(auto_interval_ms),
        [this, payload]() {
          // Skip the tick when a transaction is still in flight rather than
          // queueing up work the single-transaction design cannot honour.
          {
            std::lock_guard<std::mutex> lock(mutex_);
            if (busy_) {
              return;
            }
          }
          start_transaction(payload);
        });
    }
  }

  stats_pub_ = create_publisher<std_msgs::msg::String>("~/stats", rclcpp::QoS(10));
  if (stats_interval_ms > 0) {
    stats_timer_ = create_wall_timer(
      std::chrono::milliseconds(stats_interval_ms),
      std::bind(&RelayNode::publish_stats, this));
  }

  if (role_ == Role::kRelay) {
    RCLCPP_INFO(
      get_logger(),
      "relay: ask slave%u via %s, forward per the reply's dst byte "
      "| timeout=%dms retries=%d fc=0x%02X%s",
      slave1_id_, tx_topic.c_str(), timeout_ms, max_retries_, function_code_,
      auto_interval_ms > 0 ? " (auto)" : "");
    RCLCPP_INFO(
      get_logger(), "trigger a transaction:  ros2 topic pub --once %s "
      "std_msgs/String \"{data: 'hello'}\"",
      trigger_sub_->get_topic_name());
  } else {
    RCLCPP_INFO(
      get_logger(), "responder: answering %s on %s", rx_topic.c_str(), tx_topic.c_str());
    if (routes_.empty()) {
      RCLCPP_WARN(
        get_logger(),
        "route_map is empty: every reply will use default_dst=%u%s. Set e.g. "
        "route_map:=\"temp:2,humid:3\" so the payload picks the target.",
        default_dst_,
        default_dst_ == transaction::kNoForward ? " (no forwarding)" : "");
    } else {
      std::ostringstream os;
      for (std::size_t i = 0; i < routes_.size(); ++i) {
        os << (i ? ", " : "") << routes_[i].keyword << "->slave"
           << static_cast<int>(routes_[i].station);
      }
      RCLCPP_INFO(
        get_logger(), "route_map: %s | default_dst=%u%s",
        os.str().c_str(), default_dst_,
        default_dst_ == transaction::kNoForward ? " (no forwarding)" : "");
    }
  }
}

std::vector<RelayNode::Route> RelayNode::parse_route_map(const std::string & spec)
{
  std::vector<Route> routes;
  std::size_t pos = 0;
  while (pos < spec.size()) {
    std::size_t comma = spec.find(',', pos);
    if (comma == std::string::npos) {
      comma = spec.size();
    }
    std::string entry = spec.substr(pos, comma - pos);
    pos = comma + 1;

    // Trim surrounding whitespace so "temp:2, humid:3" works.
    const auto first = entry.find_first_not_of(" \t");
    if (first == std::string::npos) {
      continue;                       // empty entry, e.g. a trailing comma
    }
    const auto last = entry.find_last_not_of(" \t");
    entry = entry.substr(first, last - first + 1);

    const auto colon = entry.rfind(':');
    if (colon == std::string::npos || colon == 0 || colon + 1 == entry.size()) {
      throw std::invalid_argument(
              "route_map entry must be 'keyword:station', got: '" + entry + "'");
    }
    const std::string keyword = entry.substr(0, colon);
    const std::string station_text = entry.substr(colon + 1);

    int station = 0;
    try {
      std::size_t consumed = 0;
      station = std::stoi(station_text, &consumed);
      if (consumed != station_text.size()) {
        throw std::invalid_argument("trailing characters");
      }
    } catch (const std::exception &) {
      throw std::invalid_argument(
              "route_map station must be an integer, got: '" + station_text +
              "' in entry '" + entry + "'");
    }
    routes.push_back({keyword, checked_station(station, "route_map station")});
  }
  return routes;
}

uint8_t RelayNode::route_lookup(
  const std::vector<Route> & routes,
  const std::vector<uint8_t> & payload,
  uint8_t default_dst)
{
  const std::string text(payload.begin(), payload.end());
  for (const auto & route : routes) {
    if (text.find(route.keyword) != std::string::npos) {
      return route.station;          // first match wins
    }
  }
  return default_dst;
}

void RelayNode::on_rx(const ds10_interfaces::msg::Frame::SharedPtr msg)
{
  if (role_ == Role::kResponder) {
    respond(*msg);
  } else {
    handle_reply(*msg);
  }
}

uint8_t RelayNode::route_for(const std::vector<uint8_t> & payload) const
{
  return route_lookup(routes_, payload, default_dst_);
}

void RelayNode::respond(const ds10_interfaces::msg::Frame & msg)
{
  // The request carries a 4-byte header; the payload after it is what the
  // routing table inspects.
  const auto txn = transaction::parse_txn(msg.data);
  if (!txn) {
    ++ignored_;
    RCLCPP_DEBUG(get_logger(), "request has no transaction header, dropped");
    return;
  }
  const auto payload = transaction::strip_header(msg.data);

  // This is the whole point of the design: the slave, not the master, decides
  // where its answer goes. kNoForward means "answer me, but keep it".
  const uint8_t dst = route_for(payload);

  auto framed = transaction::build_reply(*txn, dst, payload);
  if (!framed) {
    ++oversized_;
    RCLCPP_WARN(
      get_logger(), "reply payload %zu B exceeds cap %zu B, not answering",
      payload.size(), transaction::kMaxReplyPayload);
    return;
  }

  ds10_interfaces::msg::Frame out;
  // station_id is overwritten by the driver with this slave's own station.
  out.function_code = msg.function_code;
  out.data = std::move(*framed);
  tx_pub_->publish(out);
  ++answered_;

  if (dst == transaction::kNoForward) {
    RCLCPP_INFO(
      get_logger(), "answered txn=%u %zu B, dst=0 (no forwarding) [%s]",
      *txn, payload.size(), preview(payload).c_str());
  } else {
    RCLCPP_INFO(
      get_logger(), "answered txn=%u %zu B, dst=slave%u [%s]",
      *txn, payload.size(), dst, preview(payload).c_str());
  }
}

void RelayNode::handle_reply(const ds10_interfaces::msg::Frame & msg)
{
  // Every rejection below is a normal event on a radio link — a duplicate
  // reply, one that arrived after we gave up, or traffic from another slave.
  // They are counted and logged at DEBUG only; at INFO a single retransmitting
  // peer would flood the console and bury real failures.
  if (msg.station_id != slave1_id_) {
    ++ignored_;
    RCLCPP_DEBUG(
      get_logger(), "ignoring frame from station %u (awaiting %u)",
      msg.station_id, slave1_id_);
    return;
  }

  const auto got = transaction::parse_txn(msg.data);
  if (!got) {
    ++ignored_;
    RCLCPP_DEBUG(get_logger(), "reply has no transaction header, dropped");
    return;
  }

  std::vector<uint8_t> reply;
  double rtt_ms = 0.0;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!busy_) {
      ++ignored_;
      RCLCPP_DEBUG(get_logger(), "reply txn=%u while idle, dropped", *got);
      return;
    }
    if (*got != pending_txn_) {
      ++ignored_;
      RCLCPP_DEBUG(
        get_logger(), "reply txn=%u does not match pending %u, dropped",
        *got, pending_txn_);
      return;
    }
    rtt_ms = (now() - started_).seconds() * 1000.0;
    reply = msg.data;
    // Clear pending state before forwarding so a duplicate arriving mid-forward
    // is dropped by the !busy_ check above instead of forwarding twice.
    busy_ = false;
  }
  if (timeout_timer_) {
    timeout_timer_->cancel();
  }

  // The slave names its target in the reply header. A reply that predates this
  // protocol (4-byte header, no dst) is not silently treated as dst=0: it is
  // counted so a version mismatch is visible rather than looking like a slave
  // that simply declined forwarding.
  //
  // It counts as failed, not ok: a reply arrived, but the transaction did not
  // do what was asked of it. Booking it as ok would inflate the success rate
  // and bury a real version mismatch inside the healthy bucket.
  const auto dst = transaction::parse_dst(reply);
  if (!dst) {
    ++bad_dst_;
    ++failed_;
    RCLCPP_WARN(
      get_logger(),
      "reply txn=%u (%zu B, rtt %.1f ms) carries no dst byte — peer likely "
      "predates slave-driven routing; not forwarding",
      *got, reply.size(), rtt_ms);
    return;
  }

  const auto payload = transaction::strip_reply_header(reply);

  if (*dst == transaction::kNoForward) {
    ++no_forward_;
    ++ok_;
    RCLCPP_INFO(
      get_logger(),
      "reply from slave%u txn=%u %zu B, rtt %.1f ms, dst=0 (slave asked for "
      "no forwarding) [%s]",
      slave1_id_, *got, payload.size(), rtt_ms, preview(payload).c_str());
    return;
  }

  // Any legal station is honoured: routing authority belongs to the slave, so
  // the master keeps no allow-list. Self-addressing is the one exception —
  // forwarding back to the responder would make its own answer look like a
  // fresh reply and the relay would chase its tail.
  if (!transaction::is_forwardable(*dst)) {
    ++bad_dst_;
    ++failed_;
    RCLCPP_WARN(
      get_logger(),
      "reply txn=%u names dst=%u, outside the Modbus station range 1..247 — "
      "not forwarding", *got, *dst);
    return;
  }
  if (*dst == slave1_id_) {
    ++bad_dst_;
    ++failed_;
    RCLCPP_WARN(
      get_logger(),
      "reply txn=%u names dst=%u, its own station — refusing to forward a "
      "reply back to its sender", *got, *dst);
    return;
  }

  RCLCPP_INFO(
    get_logger(), "reply from slave%u txn=%u %zu B, rtt %.1f ms, dst=slave%u [%s]",
    slave1_id_, *got, payload.size(), rtt_ms, *dst, preview(payload).c_str());

  forward(*dst, payload, msg.function_code);
  ++ok_;
}

void RelayNode::forward(
  uint8_t dst, const std::vector<uint8_t> & payload, uint8_t function_code)
{
  // Forward the business payload with the reply header stripped: the
  // transaction number and dst were master<->slave1 bookkeeping and mean
  // nothing to the destination.
  if (payload.size() > transaction::kMaxData) {
    ++oversized_;
    RCLCPP_WARN(
      get_logger(),
      "not forwarding %zu B: exceeds single-frame data cap %zu B",
      payload.size(), transaction::kMaxData);
    return;
  }

  ds10_interfaces::msg::Frame out;
  out.station_id = dst;
  out.function_code = function_code;
  out.data = payload;
  tx_pub_->publish(out);
  ++forwarded_;

  RCLCPP_INFO(get_logger(), "forwarded %zu B to slave%u", payload.size(), dst);
}

void RelayNode::on_trigger(const std_msgs::msg::String::SharedPtr msg)
{
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (busy_) {
      RCLCPP_WARN(
        get_logger(), "busy with txn=%u, ignoring trigger", pending_txn_);
      return;
    }
  }
  start_transaction(std::vector<uint8_t>(msg->data.begin(), msg->data.end()));
}

void RelayNode::start_transaction(const std::vector<uint8_t> & payload)
{
  if (payload.size() > transaction::kMaxPayload) {
    ++oversized_;
    RCLCPP_WARN(
      get_logger(), "payload %zu B exceeds cap %zu B (frame 4095 B minus "
      "Modbus header/CRC and the 4 B transaction header)",
      payload.size(), transaction::kMaxPayload);
    return;
  }

  {
    std::lock_guard<std::mutex> lock(mutex_);
    busy_ = true;
    payload_ = payload;
    attempt_ = 0;
    txn_ = static_cast<uint16_t>(txn_ + 1);
    pending_txn_ = txn_;
  }
  // Send the first attempt through the retry path so request emission and
  // timer arming live in exactly one place.
  on_timeout();
}

void RelayNode::on_timeout()
{
  std::vector<uint8_t> payload;
  uint16_t txn = 0;
  int attempt = 0;

  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!busy_) {
      return;  // reply landed between the timer firing and this lock
    }
    if (attempt_ > 0) {
      ++timeouts_;
      RCLCPP_WARN(
        get_logger(), "txn=%u timed out after %" PRId64 " ms (attempt %d/%d)",
        pending_txn_, static_cast<int64_t>(timeout_.count()),
        attempt_, max_retries_ + 1);
    }
    if (attempt_ > max_retries_) {
      ++failed_;
      RCLCPP_ERROR(
        get_logger(),
        "txn=%u gave up after %d attempts — is a responder running on slave%u? "
        "(check DS10 pairing/channel, and the driver's /diagnostics)",
        pending_txn_, attempt_, slave1_id_);
      busy_ = false;
      payload_.clear();
      return;
    }
    if (attempt_ > 0) {
      ++retried_;
    }
    ++attempt_;
    attempt = attempt_;
    txn = pending_txn_;
    payload = payload_;
    started_ = now();
  }

  auto framed = transaction::build(txn, payload);
  if (!framed) {
    // start_transaction already bounds the payload, so this is unreachable
    // unless the caps change inconsistently.
    ++oversized_;
    RCLCPP_ERROR(get_logger(), "txn=%u payload no longer fits, aborting", txn);
    std::lock_guard<std::mutex> lock(mutex_);
    busy_ = false;
    return;
  }

  ds10_interfaces::msg::Frame out;
  out.station_id = slave1_id_;
  out.function_code = function_code_;
  out.data = std::move(*framed);
  out.tx_seq = txn;   // local bookkeeping only: the driver does not put this on the wire
  const std::size_t sent_bytes = out.data.size();
  tx_pub_->publish(out);
  ++sent_;

  RCLCPP_INFO(
    get_logger(), "request to slave%u txn=%u %zu B (attempt %d/%d)",
    slave1_id_, txn, sent_bytes, attempt, max_retries_ + 1);

  // One-shot: re-arm per attempt. A repeating timer would keep firing after
  // the transaction completed.
  timeout_timer_ = create_wall_timer(
    timeout_, [this]() {
      if (timeout_timer_) {
        timeout_timer_->cancel();
      }
      on_timeout();
    });
}

void RelayNode::publish_stats()
{
  std::ostringstream os;
  if (role_ == Role::kResponder) {
    os << "answered=" << answered_.load()
       << " oversized=" << oversized_.load()
       << " ignored=" << ignored_.load();
  } else {
    os << "sent=" << sent_.load()
       << " ok=" << ok_.load()
       << " failed=" << failed_.load()
       << " retried=" << retried_.load()
       << " timeouts=" << timeouts_.load()
       << " forwarded=" << forwarded_.load()
      // A reply the slave deliberately kept (dst=0) and one naming an unusable
      // station are different outcomes, so they get different counters.
       << " no_forward=" << no_forward_.load()
       << " bad_dst=" << bad_dst_.load()
       << " oversized=" << oversized_.load()
      // Never silent: a large ignored count is the fingerprint of duplicate
      // responders, radio retransmission, or too tight a timeout.
       << " ignored=" << ignored_.load();
  }
  std_msgs::msg::String msg;
  msg.data = os.str();
  stats_pub_->publish(msg);
}

}  // namespace ds10_relay
