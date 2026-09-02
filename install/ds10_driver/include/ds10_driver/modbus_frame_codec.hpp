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

#ifndef DS10_DRIVER__MODBUS_FRAME_CODEC_HPP_
#define DS10_DRIVER__MODBUS_FRAME_CODEC_HPP_

#include <cstdint>
#include <optional>
#include <vector>

namespace ds10_driver
{

/// One decoded Modbus RTU frame: station address, function code and the data
/// field between them and the CRC. Produced only for frames whose CRC-16/MODBUS
/// verified — a decoded frame is by definition CRC-valid (see design ticket 03).
struct DecodedFrame
{
  uint8_t station = 0;
  uint8_t function_code = 0;
  std::vector<uint8_t> data;
};

/// Pure-logic Modbus RTU framing for the DS10 transparent link. No serial I/O,
/// no ROS dependency — unit-testable in isolation (design test seam 1).
///
/// Encoding builds `[station][function][data][CRC16-LE]`. Decoding implements
/// the hybrid delimiter validated on real hardware (design tickets 01/02):
/// the DS10 wireless link coalesces/splits serial bursts, so frame boundaries
/// cannot be trusted from read boundaries or silence alone. `feed()` appends
/// raw bytes and extracts every complete frame it can by CRC trial: from each
/// candidate start it requires a legal station byte (1..247), then grows the
/// candidate length and accepts the first length whose CRC verifies. Bytes that
/// cannot begin a valid frame are slid past one at a time (resynchronisation);
/// a trailing partial frame is retained for the next `feed()`.
class ModbusFrameCodec
{
public:
  /// Modbus station ids are 1..247; 0 is broadcast and 248..255 are reserved.
  static constexpr uint8_t kMinStation = 1;
  static constexpr uint8_t kMaxStation = 247;

  /// Smallest structurally legal frame: station + function + CRC16 (empty data).
  static constexpr std::size_t kMinFrameLen = 4;

  /// Hard cap on a single frame on the wire. The DS10 reliable-broadcast reader
  /// truncates beyond ~4095B (design ticket 04), so both encode and the decoder
  /// buffer refuse to exceed this.
  static constexpr std::size_t kMaxFrameLen = 4095;

  explicit ModbusFrameCodec(std::size_t max_frame_len = kMaxFrameLen);

  /// CRC-16/MODBUS (poly 0xA001 reflected, init 0xFFFF). Returned low byte
  /// first, matching Modbus RTU on-wire order.
  static uint16_t crc16(const uint8_t * data, std::size_t len);

  /// Build a complete frame `[station][function_code][data][CRC-LE]`.
  /// Returns std::nullopt if the resulting frame would exceed max_frame_len
  /// (the caller must reject oversized Frames on the tx path).
  std::optional<std::vector<uint8_t>> encode(
    uint8_t station, uint8_t function_code, const std::vector<uint8_t> & data) const;

  /// Append raw bytes from the serial stream and extract every complete frame
  /// currently decodable. Frames are returned in order. Bytes discarded during
  /// resynchronisation are counted in `resync_dropped()`.
  std::vector<DecodedFrame> feed(const uint8_t * bytes, std::size_t len);

  /// Drop any buffered partial bytes (e.g. on burst-end timeout or reconnect),
  /// counting them as resync drops, and reset to a clean scan state.
  void flush_partial();

  /// Number of bytes discarded so far by resynchronisation / partial flush.
  /// Exposed for the diagnostics link-noise metric (design ticket 03).
  uint64_t resync_dropped() const {return resync_dropped_;}

  std::size_t buffered() const {return buffer_.size();}

private:
  std::size_t max_frame_len_;
  std::vector<uint8_t> buffer_;
  uint64_t resync_dropped_ = 0;
};

}  // namespace ds10_driver

#endif  // DS10_DRIVER__MODBUS_FRAME_CODEC_HPP_
