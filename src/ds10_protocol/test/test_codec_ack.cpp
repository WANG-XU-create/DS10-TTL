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

// Round-trip test: encode then decode should recover original values
TEST(CodecAckTest, RoundTrip)
{
  ds10_protocol::AckMessage ack;
  ack.acked_seq = 42;
  ack.acked_function_code = ds10_protocol::FUNC_SENSOR_DATA;

  auto encoded = ds10_protocol::encode_ack(ack);
  auto decoded = ds10_protocol::decode_ack(encoded);

  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->acked_seq, ack.acked_seq);
  EXPECT_EQ(decoded->acked_function_code, ack.acked_function_code);
}

// Test acked_seq boundary: 0 (also the convention for messages without a seq)
TEST(CodecAckTest, AckedSeqZero)
{
  ds10_protocol::AckMessage ack;
  ack.acked_seq = 0;
  ack.acked_function_code = ds10_protocol::FUNC_CONTROL_CMD;

  auto encoded = ds10_protocol::encode_ack(ack);
  auto decoded = ds10_protocol::decode_ack(encoded);

  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->acked_seq, 0);
  EXPECT_EQ(decoded->acked_function_code, ds10_protocol::FUNC_CONTROL_CMD);
}

// Test acked_seq boundary: 65535 (max uint16_t)
TEST(CodecAckTest, AckedSeqMax)
{
  ds10_protocol::AckMessage ack;
  ack.acked_seq = 65535;
  ack.acked_function_code = ds10_protocol::FUNC_SENSOR_DATA;

  auto encoded = ds10_protocol::encode_ack(ack);
  auto decoded = ds10_protocol::decode_ack(encoded);

  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->acked_seq, 65535);
  EXPECT_EQ(decoded->acked_function_code, ds10_protocol::FUNC_SENSOR_DATA);
}

// Test common function codes being acknowledged
TEST(CodecAckTest, CommonFunctionCodes)
{
  // 0x10 sensor data
  {
    ds10_protocol::AckMessage ack{100, ds10_protocol::FUNC_SENSOR_DATA};
    auto decoded = ds10_protocol::decode_ack(ds10_protocol::encode_ack(ack));
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->acked_function_code, ds10_protocol::FUNC_SENSOR_DATA);
  }

  // 0x11 log message
  {
    ds10_protocol::AckMessage ack{200, ds10_protocol::FUNC_LOG};
    auto decoded = ds10_protocol::decode_ack(ds10_protocol::encode_ack(ack));
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->acked_function_code, ds10_protocol::FUNC_LOG);
  }

  // 0x12 control command
  {
    ds10_protocol::AckMessage ack{300, ds10_protocol::FUNC_CONTROL_CMD};
    auto decoded = ds10_protocol::decode_ack(ds10_protocol::encode_ack(ack));
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->acked_function_code, ds10_protocol::FUNC_CONTROL_CMD);
  }
}

// Test wire format: 3 bytes, acked_seq little-endian, no leading flags byte
TEST(CodecAckTest, LittleEndianByteOrder)
{
  ds10_protocol::AckMessage ack;
  ack.acked_seq = 0x1234;
  ack.acked_function_code = ds10_protocol::FUNC_SENSOR_DATA;

  auto encoded = ds10_protocol::encode_ack(ack);

  ASSERT_EQ(encoded.size(), 3u);
  EXPECT_EQ(encoded[0], 0x34);  // acked_seq low byte
  EXPECT_EQ(encoded[1], 0x12);  // acked_seq high byte
  EXPECT_EQ(encoded[2], ds10_protocol::FUNC_SENSOR_DATA);
}

// Test decode error: data size < 3
TEST(CodecAckTest, DecodeErrorTooShort)
{
  // Empty data
  {
    std::vector<uint8_t> data;
    auto decoded = ds10_protocol::decode_ack(data);
    EXPECT_FALSE(decoded.has_value());
  }

  // 1 byte
  {
    std::vector<uint8_t> data = {0x00};
    auto decoded = ds10_protocol::decode_ack(data);
    EXPECT_FALSE(decoded.has_value());
  }

  // 2 bytes
  {
    std::vector<uint8_t> data = {0x00, 0x00};
    auto decoded = ds10_protocol::decode_ack(data);
    EXPECT_FALSE(decoded.has_value());
  }
}

// Test decode tolerates trailing bytes beyond the 3-byte payload
TEST(CodecAckTest, DecodeIgnoresTrailingBytes)
{
  // [0x34, 0x12, 0x10] + two extra bytes
  std::vector<uint8_t> data = {0x34, 0x12, ds10_protocol::FUNC_SENSOR_DATA, 0xFF, 0xEE};

  auto decoded = ds10_protocol::decode_ack(data);

  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->acked_seq, 0x1234);
  EXPECT_EQ(decoded->acked_function_code, ds10_protocol::FUNC_SENSOR_DATA);
}
