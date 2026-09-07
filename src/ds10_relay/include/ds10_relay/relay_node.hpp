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

#ifndef DS10_RELAY__RELAY_NODE_HPP_
#define DS10_RELAY__RELAY_NODE_HPP_

#include <atomic>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

#include "ds10_interfaces/msg/frame.hpp"
#include "ds10_relay/transaction.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

namespace ds10_relay
{

/// Three-hop request/reply relay riding on top of `ds10_driver` topics.
///
/// One executable covers both ends via the `role` parameter, mirroring how
/// `ds10_driver` uses `role=master|slave`:
///
/// - `relay` (master side): publishes a request to slave 1, waits for the reply
///   whose transaction number matches, then forwards that reply to **whichever
///   station the slave named** in the reply's `dst` byte. Retries on timeout.
/// - `responder` (slave side): answers a request, choosing the forwarding
///   target from its payload via a configured keyword -> station table.
///
/// Routing is therefore slave-driven: the master holds no destination of its
/// own and only sanity-checks that `dst` is a legal, non-self station. Adding a
/// destination means editing the responder's table, not the master's config.
///
/// The relay is deliberately single-transaction: one request is outstanding at
/// a time, so a single pending transaction number suffices and no table is
/// needed. Timeouts run on a one-shot timer rather than blocking the callback,
/// because under MultiThreadedExecutor a blocking wait would pin an executor
/// thread for the whole timeout.
class RelayNode : public rclcpp::Node
{
public:
  explicit RelayNode(const rclcpp::NodeOptions & options);

  /// One keyword -> station rule from the `route_map` parameter.
  struct Route
  {
    std::string keyword;
    uint8_t station;
  };

  /// Parse a `route_map` parameter ("keyword:station,keyword:station,...")
  /// into rules. Throws std::invalid_argument on a malformed entry or an
  /// out-of-range station, so a typo fails at startup rather than silently
  /// routing nowhere. Public, static and pure: this is the routing contract
  /// the responder is configured with, so it is unit-tested directly.
  static std::vector<Route> parse_route_map(const std::string & spec);

  /// Station the given routing table selects for `payload`, or
  /// `default_dst` when no keyword matches. First match wins, so earlier
  /// entries take precedence. Pure, so it is unit-tested directly.
  static uint8_t route_lookup(
    const std::vector<Route> & routes,
    const std::vector<uint8_t> & payload,
    uint8_t default_dst);

private:
  enum class Role { kRelay, kResponder };

  /// Frames arriving from the driver's rx topic.
  void on_rx(const ds10_interfaces::msg::Frame::SharedPtr msg);

  /// Answer a request, naming the forwarding target chosen from the payload
  /// (responder role).
  void respond(const ds10_interfaces::msg::Frame & msg);

  /// Station the routing table selects for this payload, or kNoForward when
  /// nothing matches and no default is configured.
  uint8_t route_for(const std::vector<uint8_t> & payload) const;

  /// Reply path: validate against the pending transaction, then forward to the
  /// station the slave named (relay role).
  void handle_reply(const ds10_interfaces::msg::Frame & msg);

  /// External trigger: start a transaction carrying this text as the payload.
  void on_trigger(const std_msgs::msg::String::SharedPtr msg);

  /// Publish a request to slave 1 and arm the timeout. Caller holds no lock.
  void start_transaction(const std::vector<uint8_t> & payload);

  /// Re-send the current payload, or give up once retries are exhausted.
  void on_timeout();

  /// Forward a reply's payload to the station the slave asked for.
  void forward(
    uint8_t dst, const std::vector<uint8_t> & payload, uint8_t function_code);

  /// Publish the running counters on ~/stats.
  void publish_stats();

  // Parameters, resolved in the constructor and immutable afterwards.
  Role role_ = Role::kRelay;
  uint8_t slave1_id_ = 1;
  uint8_t function_code_ = 0x10;
  // 1500 ms covers the worst round trip measured on real radios (764 ms at a
  // 1004 B payload) with roughly 2x headroom. RTT scales steeply with size:
  // ~30 ms at 30 B, ~250 ms at 504 B, ~600 ms at 1004 B.
  std::chrono::milliseconds timeout_{1500};
  int max_retries_ = 2;

  // Responder-side routing table and its fallback, both from parameters.
  std::vector<Route> routes_;
  uint8_t default_dst_ = transaction::kNoForward;

  rclcpp::Subscription<ds10_interfaces::msg::Frame>::SharedPtr rx_sub_;
  rclcpp::Publisher<ds10_interfaces::msg::Frame>::SharedPtr tx_pub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr trigger_sub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr stats_pub_;
  rclcpp::TimerBase::SharedPtr timeout_timer_;
  rclcpp::TimerBase::SharedPtr auto_timer_;
  rclcpp::TimerBase::SharedPtr stats_timer_;

  // Transaction state. Guarded by mutex_: on_rx, the timeout timer and the
  // trigger callback all run concurrently under MultiThreadedExecutor.
  std::mutex mutex_;
  bool busy_ = false;              ///< a transaction is outstanding
  uint16_t txn_ = 0;               ///< last allocated transaction number
  uint16_t pending_txn_ = 0;       ///< transaction we are waiting on
  int attempt_ = 0;                ///< attempts spent on the current payload
  std::vector<uint8_t> payload_;   ///< current payload, kept for retries
  rclcpp::Time started_;           ///< when the current attempt went out

  // Counters. Reported on ~/stats; dropped frames are counted rather than
  // logged at INFO, because duplicate and late replies are normal on a radio
  // link and logging each one drowns out real failures.
  std::atomic<uint64_t> sent_{0};
  std::atomic<uint64_t> ok_{0};
  std::atomic<uint64_t> failed_{0};
  std::atomic<uint64_t> retried_{0};
  std::atomic<uint64_t> timeouts_{0};
  std::atomic<uint64_t> ignored_{0};
  std::atomic<uint64_t> forwarded_{0};
  std::atomic<uint64_t> no_forward_{0};   ///< replies the slave asked us to keep
  std::atomic<uint64_t> bad_dst_{0};      ///< replies naming an illegal station
  std::atomic<uint64_t> answered_{0};
  std::atomic<uint64_t> oversized_{0};
};

}  // namespace ds10_relay

#endif  // DS10_RELAY__RELAY_NODE_HPP_
