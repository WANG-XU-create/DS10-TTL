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

#include <cstring>  // for memcpy

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

std::vector<uint8_t> encode_sensor_data(const SensorData & sensor)
{
  std::vector<uint8_t> data(8);  // Fixed size: 1 + 2 + 1 + 4 = 8 bytes

  data[0] = sensor.flags;

  // seq: uint16_t little-endian
  data[1] = static_cast<uint8_t>(sensor.seq & 0xFF);
  data[2] = static_cast<uint8_t>((sensor.seq >> 8) & 0xFF);

  data[3] = sensor.sensor_id;

  // reading: float32 little-endian
  // Use memcpy to avoid type-punning undefined behavior
  uint32_t float_bits;
  std::memcpy(&float_bits, &sensor.reading, sizeof(float));
  data[4] = static_cast<uint8_t>(float_bits & 0xFF);
  data[5] = static_cast<uint8_t>((float_bits >> 8) & 0xFF);
  data[6] = static_cast<uint8_t>((float_bits >> 16) & 0xFF);
  data[7] = static_cast<uint8_t>((float_bits >> 24) & 0xFF);

  return data;
}

std::optional<SensorData> decode_sensor_data(const std::vector<uint8_t> & data)
{
  // Minimum size: flags(1B) + seq(2B) + sensor_id(1B) + reading(4B) = 8 bytes
  constexpr size_t SENSOR_DATA_SIZE = 8;
  if (data.size() < SENSOR_DATA_SIZE) {
    return std::nullopt;
  }

  SensorData sensor;
  sensor.flags = data[0];

  // seq: uint16_t little-endian
  sensor.seq = static_cast<uint16_t>(data[1]) | (static_cast<uint16_t>(data[2]) << 8);

  sensor.sensor_id = data[3];

  // reading: float32 little-endian
  uint32_t float_bits = static_cast<uint32_t>(data[4]) |
    (static_cast<uint32_t>(data[5]) << 8) |
    (static_cast<uint32_t>(data[6]) << 16) |
    (static_cast<uint32_t>(data[7]) << 24);
  std::memcpy(&sensor.reading, &float_bits, sizeof(float));

  return sensor;
}

}  // namespace ds10_protocol
