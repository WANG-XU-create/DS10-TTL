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

#include "ds10_driver/modbus_frame_codec.hpp"

#include <algorithm>

namespace ds10_driver
{

ModbusFrameCodec::ModbusFrameCodec(std::size_t max_frame_len)
: max_frame_len_(std::max<std::size_t>(max_frame_len, kMinFrameLen))
{
}

uint16_t ModbusFrameCodec::crc16(const uint8_t * data, std::size_t len)
{
  uint16_t crc = 0xFFFF;
  for (std::size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit) {
      if (crc & 1u) {
        crc = static_cast<uint16_t>((crc >> 1) ^ 0xA001u);
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

std::optional<std::vector<uint8_t>> ModbusFrameCodec::encode(
  uint8_t station, uint8_t function_code, const std::vector<uint8_t> & data) const
{
  const std::size_t frame_len = 2 + data.size() + 2;  // station+fc + data + CRC
  if (frame_len > max_frame_len_) {
    return std::nullopt;
  }
  std::vector<uint8_t> frame;
  frame.reserve(frame_len);
  frame.push_back(station);
  frame.push_back(function_code);
  frame.insert(frame.end(), data.begin(), data.end());
  const uint16_t crc = crc16(frame.data(), frame.size());
  frame.push_back(static_cast<uint8_t>(crc & 0xFF));         // low byte first
  frame.push_back(static_cast<uint8_t>((crc >> 8) & 0xFF));
  return frame;
}

std::vector<DecodedFrame> ModbusFrameCodec::feed(const uint8_t * bytes, std::size_t len)
{
  buffer_.insert(buffer_.end(), bytes, bytes + len);

  std::vector<DecodedFrame> frames;
  std::size_t pos = 0;
  const std::size_t n = buffer_.size();

  while (pos < n) {
    const uint8_t station = buffer_[pos];
    // Resynchronise: a legal frame can only start on a station byte 1..247.
    if (station < kMinStation || station > kMaxStation) {
      ++pos;
      ++resync_dropped_;
      continue;
    }
    // CRC trial: grow the candidate length, accept the first CRC match.
    const std::size_t max_try = std::min(n - pos, max_frame_len_);
    bool matched = false;
    for (std::size_t flen = kMinFrameLen; flen <= max_try; ++flen) {
      const uint8_t * f = buffer_.data() + pos;
      const uint16_t crc = crc16(f, flen - 2);
      const uint16_t on_wire =
        static_cast<uint16_t>(f[flen - 2] | (f[flen - 1] << 8));
      if (crc == on_wire) {
        DecodedFrame df;
        df.station = f[0];
        df.function_code = f[1];
        df.data.assign(f + 2, f + (flen - 2));
        frames.push_back(std::move(df));
        pos += flen;
        matched = true;
        break;
      }
    }
    if (matched) {
      continue;
    }
    // No frame starts at pos yet. If the untried remainder is shorter than the
    // cap it may be a partial frame — keep it. Otherwise this start is noise:
    // slide one byte and resynchronise.
    if (n - pos < max_frame_len_) {
      break;
    }
    ++pos;
    ++resync_dropped_;
  }

  buffer_.erase(buffer_.begin(), buffer_.begin() + pos);
  return frames;
}

void ModbusFrameCodec::flush_partial()
{
  resync_dropped_ += buffer_.size();
  buffer_.clear();
}

}  // namespace ds10_driver
