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

#include <gtest/gtest.h>

#include <cstdint>
#include <vector>

#include "ds10_driver/modbus_frame_codec.hpp"

using ds10_driver::DecodedFrame;
using ds10_driver::ModbusFrameCodec;

namespace
{

std::vector<DecodedFrame> feed_vec(ModbusFrameCodec & codec, const std::vector<uint8_t> & bytes)
{
  return codec.feed(bytes.data(), bytes.size());
}

}  // namespace

// CRC-16/MODBUS reference vector: "01 03 00 00 00 02" -> C4 0B (low, high).
TEST(ModbusFrameCodec, Crc16KnownVector)
{
  const std::vector<uint8_t> body = {0x01, 0x03, 0x00, 0x00, 0x00, 0x02};
  const uint16_t crc = ModbusFrameCodec::crc16(body.data(), body.size());
  EXPECT_EQ(crc & 0xFF, 0xC4);
  EXPECT_EQ((crc >> 8) & 0xFF, 0x0B);
}

// A round-tripped frame decodes back to the same fields.
TEST(ModbusFrameCodec, EncodeDecodeRoundTrip)
{
  ModbusFrameCodec codec;
  const std::vector<uint8_t> data = {0xDE, 0xAD, 0xBE, 0xEF};
  auto frame = codec.encode(7, 0x10, data);
  ASSERT_TRUE(frame.has_value());

  auto out = feed_vec(codec, *frame);
  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].station, 7);
  EXPECT_EQ(out[0].function_code, 0x10);
  EXPECT_EQ(out[0].data, data);
  EXPECT_EQ(codec.resync_dropped(), 0u);
}

// A CRC-corrupted segment produces no frame; bytes are eventually consumed.
TEST(ModbusFrameCodec, CrcFailureProducesNoFrame)
{
  ModbusFrameCodec codec;
  auto frame = codec.encode(1, 0x03, {0x11, 0x22, 0x33, 0x44});
  ASSERT_TRUE(frame.has_value());
  frame->back() ^= 0xFF;  // corrupt CRC high byte

  auto out = feed_vec(codec, *frame);
  EXPECT_TRUE(out.empty());
}

// A partial frame is retained, then completed on the next feed.
TEST(ModbusFrameCodec, PartialFrameRetainedThenCompleted)
{
  ModbusFrameCodec codec;
  auto frame = codec.encode(3, 0x10, {1, 2, 3, 4, 5, 6, 7, 8});
  ASSERT_TRUE(frame.has_value());

  const std::size_t half = frame->size() / 2;
  std::vector<uint8_t> first(frame->begin(), frame->begin() + half);
  std::vector<uint8_t> rest(frame->begin() + half, frame->end());

  EXPECT_TRUE(feed_vec(codec, first).empty());
  EXPECT_GT(codec.buffered(), 0u);
  auto out = feed_vec(codec, rest);
  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].station, 3);
}

// Two frames glued into one burst are both extracted.
TEST(ModbusFrameCodec, CoalescedFramesSplit)
{
  ModbusFrameCodec codec;
  auto a = codec.encode(1, 0x03, {0xAA, 0xBB});
  auto b = codec.encode(2, 0x10, {0xCC, 0xDD, 0xEE});
  ASSERT_TRUE(a.has_value() && b.has_value());

  std::vector<uint8_t> glued = *a;
  glued.insert(glued.end(), b->begin(), b->end());

  auto out = feed_vec(codec, glued);
  ASSERT_EQ(out.size(), 2u);
  EXPECT_EQ(out[0].station, 1);
  EXPECT_EQ(out[1].station, 2);
}

// A noise prefix (illegal station bytes) is slid past, then the frame decodes.
TEST(ModbusFrameCodec, NoisePrefixResync)
{
  ModbusFrameCodec codec;
  auto frame = codec.encode(5, 0x03, {0x01, 0x02});
  ASSERT_TRUE(frame.has_value());

  std::vector<uint8_t> stream = {0x00, 0xFF, 0xFE};  // 0/248-255 style illegals
  stream.insert(stream.end(), frame->begin(), frame->end());

  auto out = feed_vec(codec, stream);
  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].station, 5);
  EXPECT_GE(codec.resync_dropped(), 3u);  // the three illegal prefix bytes
}

// An empty data field (minimum frame) is accepted.
TEST(ModbusFrameCodec, EmptyDataFrameAccepted)
{
  ModbusFrameCodec codec;
  auto frame = codec.encode(9, 0x05, {});
  ASSERT_TRUE(frame.has_value());
  ASSERT_EQ(frame->size(), ModbusFrameCodec::kMinFrameLen);

  auto out = feed_vec(codec, *frame);
  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].station, 9);
  EXPECT_TRUE(out[0].data.empty());
}

// A frame near the single-frame cap round-trips.
TEST(ModbusFrameCodec, LargeFrameNearCap)
{
  ModbusFrameCodec codec;
  std::vector<uint8_t> data(ModbusFrameCodec::kMaxFrameLen - 4, 0x5A);  // +2 fc +2 crc
  auto frame = codec.encode(1, 0x10, data);
  ASSERT_TRUE(frame.has_value());
  EXPECT_EQ(frame->size(), ModbusFrameCodec::kMaxFrameLen);

  auto out = feed_vec(codec, *frame);
  ASSERT_EQ(out.size(), 1u);
  EXPECT_EQ(out[0].data.size(), data.size());
}

// Encoding refuses payloads that would exceed the single-frame cap.
TEST(ModbusFrameCodec, EncodeRejectsOversized)
{
  ModbusFrameCodec codec;
  std::vector<uint8_t> data(ModbusFrameCodec::kMaxFrameLen, 0x00);  // guaranteed over
  auto frame = codec.encode(1, 0x10, data);
  EXPECT_FALSE(frame.has_value());
}

// flush_partial drops buffered bytes and counts them.
TEST(ModbusFrameCodec, FlushPartialCountsDrops)
{
  ModbusFrameCodec codec;
  auto frame = codec.encode(1, 0x03, {1, 2, 3, 4});
  ASSERT_TRUE(frame.has_value());
  std::vector<uint8_t> partial(frame->begin(), frame->begin() + 3);
  feed_vec(codec, partial);
  EXPECT_EQ(codec.buffered(), 3u);
  codec.flush_partial();
  EXPECT_EQ(codec.buffered(), 0u);
  EXPECT_GE(codec.resync_dropped(), 3u);
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
