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
    ds10_protocol::ControlCommand cmd;
    cmd.flags = 0x00;
    cmd.cmd_id = 0x42;
    cmd.params = {};

    auto encoded = ds10_protocol::encode_control_command(cmd);
    auto decoded = ds10_protocol::decode_control_command(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, cmd.flags);
    EXPECT_EQ(decoded->cmd_id, cmd.cmd_id);
    EXPECT_EQ(decoded->params, cmd.params);
  }

  // Test with non-empty params
  {
    ds10_protocol::ControlCommand cmd;
    cmd.flags = ds10_protocol::FLAGS_REQUEST_ACK;
    cmd.cmd_id = 0x10;
    cmd.params = {0x01, 0x02, 0x03, 0xFF};

    auto encoded = ds10_protocol::encode_control_command(cmd);
    auto decoded = ds10_protocol::decode_control_command(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, cmd.flags);
    EXPECT_EQ(decoded->cmd_id, cmd.cmd_id);
    EXPECT_EQ(decoded->params, cmd.params);
  }
}

// Test minimum size: data.size = 2 (flags + cmd_id, empty params)
TEST(CodecControlCommandTest, MinimumSize)
{
  ds10_protocol::ControlCommand cmd;
  cmd.flags = 0x00;
  cmd.cmd_id = 0x55;
  cmd.params = {};  // empty

  auto encoded = ds10_protocol::encode_control_command(cmd);

  EXPECT_EQ(encoded.size(), 2);
  EXPECT_EQ(encoded[0], cmd.flags);
  EXPECT_EQ(encoded[1], cmd.cmd_id);

  auto decoded = ds10_protocol::decode_control_command(encoded);
  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->params.size(), 0);
}

// Test maximum size: params up to MAX_CONTROL_PARAMS_SIZE (4089B)
// Frame = [station 1B][function_code 1B][data ...][CRC 2B]
// MAX_FRAME_SIZE = 4095B, MAX_DATA_SIZE = 4091B
// For 0x12: data = [flags 1B][cmd_id 1B][params ...]
// MAX_CONTROL_PARAMS_SIZE = 4089B
TEST(CodecControlCommandTest, MaximumSize)
{
  ds10_protocol::ControlCommand cmd;
  cmd.flags = 0x01;
  cmd.cmd_id = 0xAA;
  cmd.params.resize(ds10_protocol::MAX_CONTROL_PARAMS_SIZE, 0x5A);  // Fill with pattern

  auto encoded = ds10_protocol::encode_control_command(cmd);

  EXPECT_EQ(encoded.size(), 2 + ds10_protocol::MAX_CONTROL_PARAMS_SIZE);

  auto decoded = ds10_protocol::decode_control_command(encoded);
  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->flags, cmd.flags);
  EXPECT_EQ(decoded->cmd_id, cmd.cmd_id);
  EXPECT_EQ(decoded->params.size(), ds10_protocol::MAX_CONTROL_PARAMS_SIZE);
  EXPECT_EQ(decoded->params, cmd.params);
}

// Test flags combinations: bit0=0/1, bit1-7=0 (reserved bits)
TEST(CodecControlCommandTest, FlagsVariations)
{
  ds10_protocol::ControlCommand cmd;
  cmd.cmd_id = 0x33;
  cmd.params = {0xAB, 0xCD};

  // bit0 = 0, bit1-7 = 0 (no ACK request, reserved bits zero)
  {
    cmd.flags = 0x00;
    auto encoded = ds10_protocol::encode_control_command(cmd);
    auto decoded = ds10_protocol::decode_control_command(encoded);
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, 0x00);
    EXPECT_EQ(decoded->flags & ds10_protocol::FLAGS_REQUEST_ACK, 0);
  }

  // bit0 = 1, bit1-7 = 0 (request ACK, reserved bits zero)
  {
    cmd.flags = ds10_protocol::FLAGS_REQUEST_ACK;  // 0x01
    auto encoded = ds10_protocol::encode_control_command(cmd);
    auto decoded = ds10_protocol::decode_control_command(encoded);
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, ds10_protocol::FLAGS_REQUEST_ACK);
    EXPECT_NE(decoded->flags & ds10_protocol::FLAGS_REQUEST_ACK, 0);
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

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
