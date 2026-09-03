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

#ifndef DS10_PROTOCOL__CODEC_HPP_
#define DS10_PROTOCOL__CODEC_HPP_

#include <cstdint>
#include <optional>
#include <vector>

namespace ds10_protocol
{

/// @brief Decoded control command message (function code 0x12)
struct ControlCommand
{
  uint8_t flags;                   ///< Flags byte (bit0=REQUEST_ACK, bit1-7=reserved)
  uint8_t cmd_id;                  ///< Command identifier
  std::vector<uint8_t> params;     ///< Command parameters (variable length, may be empty)
};

/// @brief Encode a control command message (function code 0x12)
/// @param cmd ControlCommand structure containing flags, cmd_id, and params
/// @return Encoded data = [flags 1B][cmd_id 1B][params...]
std::vector<uint8_t> encode_control_command(const ControlCommand & cmd);

/// @brief Decode a control command message (function code 0x12)
/// @param data Encoded data, expected: [flags 1B][cmd_id 1B][params...]
/// @return Decoded ControlCommand, or nullopt if data.size() < 2
std::optional<ControlCommand> decode_control_command(const std::vector<uint8_t> & data);

}  // namespace ds10_protocol

#endif  // DS10_PROTOCOL__CODEC_HPP_
