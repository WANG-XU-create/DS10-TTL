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
#include "ds10_protocol/codec.hpp"
#include "ds10_protocol/protocol_constants.hpp"

// Test round-trip: encode then decode should produce same values
TEST(CodecControlCommandTest, RoundTrip)
{
  // Test with empty params
  {
    uint8_t flags = 0x00;
    uint8_t cmd_id = 0x42;
    std::vector<uint8_t> params;

    auto encoded = ds10_protocol::encode_control_command(flags, cmd_id, params);
    auto decoded = ds10_protocol::decode_control_command(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, flags);
    EXPECT_EQ(decoded->cmd_id, cmd_id);
    EXPECT_EQ(decoded->params, params);
  }

  // Test with non-empty params
  {
    uint8_t flags = ds10_protocol::FLAGS_REQUEST_ACK;
    uint8_t cmd_id = 0x10;
    std::vector<uint8_t> params = {0x01, 0x02, 0x03, 0xFF};

    auto encoded = ds10_protocol::encode_control_command(flags, cmd_id, params);
    auto decoded = ds10_protocol::decode_control_command(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, flags);
    EXPECT_EQ(decoded->cmd_id, cmd_id);
    EXPECT_EQ(decoded->params, params);
  }
}

// Test minimum size: data.size = 2 (flags + cmd_id, empty params)
TEST(CodecControlCommandTest, MinimumSize)
{
  uint8_t flags = 0x00;
  uint8_t cmd_id = 0x55;
  std::vector<uint8_t> params;  // empty

  auto encoded = ds10_protocol::encode_control_command(flags, cmd_id, params);

  EXPECT_EQ(encoded.size(), 2);
  EXPECT_EQ(encoded[0], flags);
  EXPECT_EQ(encoded[1], cmd_id);

  auto decoded = ds10_protocol::decode_control_command(encoded);
  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->params.size(), 0);
}

// Test maximum size: params ~4078B (approaching frame limit 4095B)
// Frame = [station 1B][function_code 1B][data ...][CRC 2B]
// data max = 4095 - 1 - 1 - 2 = 4091B
// For 0x12: data = [flags 1B][cmd_id 1B][params ...]
// params max = 4091 - 2 = 4089B
TEST(CodecControlCommandTest, MaximumSize)
{
  uint8_t flags = 0x01;
  uint8_t cmd_id = 0xAA;
  std::vector<uint8_t> params(4089, 0x5A);  // Fill with pattern

  auto encoded = ds10_protocol::encode_control_command(flags, cmd_id, params);

  EXPECT_EQ(encoded.size(), 2 + 4089);

  auto decoded = ds10_protocol::decode_control_command(encoded);
  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->flags, flags);
  EXPECT_EQ(decoded->cmd_id, cmd_id);
  EXPECT_EQ(decoded->params.size(), 4089);
  EXPECT_EQ(decoded->params, params);
}

// Test all flags combinations
TEST(CodecControlCommandTest, FlagsVariations)
{
  uint8_t cmd_id = 0x33;
  std::vector<uint8_t> params = {0xAB, 0xCD};

  // bit0 = 0 (no ACK request)
  {
    uint8_t flags = 0x00;
    auto encoded = ds10_protocol::encode_control_command(flags, cmd_id, params);
    auto decoded = ds10_protocol::decode_control_command(encoded);
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, 0x00);
    EXPECT_EQ(decoded->flags & ds10_protocol::FLAGS_REQUEST_ACK, 0);
  }

  // bit0 = 1 (request ACK)
  {
    uint8_t flags = ds10_protocol::FLAGS_REQUEST_ACK;
    auto encoded = ds10_protocol::encode_control_command(flags, cmd_id, params);
    auto decoded = ds10_protocol::decode_control_command(encoded);
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, ds10_protocol::FLAGS_REQUEST_ACK);
    EXPECT_NE(decoded->flags & ds10_protocol::FLAGS_REQUEST_ACK, 0);
  }

  // bit1-7 should be preserved (though reserved, codec doesn't validate)
  {
    uint8_t flags = 0xFE;  // all bits except bit0
    auto encoded = ds10_protocol::encode_control_command(flags, cmd_id, params);
    auto decoded = ds10_protocol::decode_control_command(encoded);
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, 0xFE);
  }
}

// Test decode error: data too short
TEST(CodecControlCommandTest, DecodeErrorTooShort)
{
  // Size 0
  {
    std::vector<uint8_t> data;
    auto decoded = ds10_protocol::decode_control_command(data);
    EXPECT_FALSE(decoded.has_value());
  }

  // Size 1 (only flags, missing cmd_id)
  {
    std::vector<uint8_t> data = {0x00};
    auto decoded = ds10_protocol::decode_control_command(data);
    EXPECT_FALSE(decoded.has_value());
  }
}

// Test decode success: exactly minimum size
TEST(CodecControlCommandTest, DecodeMinimumValid)
{
  std::vector<uint8_t> data = {0x01, 0x42};  // flags=0x01, cmd_id=0x42, no params

  auto decoded = ds10_protocol::decode_control_command(data);
  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->flags, 0x01);
  EXPECT_EQ(decoded->cmd_id, 0x42);
  EXPECT_EQ(decoded->params.size(), 0);
}

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
