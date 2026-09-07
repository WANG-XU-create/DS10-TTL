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

#include <memory>

#include "ds10_relay/relay_node.hpp"
#include "rclcpp/rclcpp.hpp"

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  try {
    auto node = std::make_shared<ds10_relay::RelayNode>(rclcpp::NodeOptions());
    // MultiThreadedExecutor: the timeout timer must be able to fire while an rx
    // callback is in flight, otherwise a stalled callback would defer the
    // timeout and stretch every transaction.
    rclcpp::executors::MultiThreadedExecutor executor;
    executor.add_node(node);
    executor.spin();
  } catch (const std::exception & e) {
    RCLCPP_FATAL(rclcpp::get_logger("ds10_relay"), "Startup failed: %s", e.what());
    rclcpp::shutdown();
    return 1;
  }

  rclcpp::shutdown();
  return 0;
}
