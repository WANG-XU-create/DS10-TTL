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

#include "ds10_protocol/codec.hpp"
#include "ds10_protocol/protocol_constants.hpp"

namespace ds10_protocol
{

std::vector<uint8_t> encode_control_command(const ControlCommand & cmd)
{
  std::vector<uint8_t> data;
  data.reserve(SIZEOF_FLAGS + SIZEOF_CMD_ID + cmd.params.size());

  data.push_back(cmd.flags);
  data.push_back(cmd.cmd_id);
  data.insert(data.end(), cmd.params.begin(), cmd.params.end());

  return data;
}

std::optional<ControlCommand> decode_control_command(const std::vector<uint8_t> & data)
{
  // Minimum size: flags(1B) + cmd_id(1B) = 2 bytes
  if (data.size() < SIZEOF_FLAGS + SIZEOF_CMD_ID) {
    return std::nullopt;
  }

  ControlCommand cmd;
  cmd.flags = data[0];
  cmd.cmd_id = data[1];

  // params = everything after flags and cmd_id
  if (data.size() > 2) {
    cmd.params.assign(data.begin() + 2, data.end());
  }

  return cmd;
}

}  // namespace ds10_protocol
