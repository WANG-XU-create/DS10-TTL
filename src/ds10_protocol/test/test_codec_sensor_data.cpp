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
#include <cmath>
#include <limits>
#include "ds10_protocol/codec.hpp"
#include "ds10_protocol/protocol_constants.hpp"

// Test round-trip: encode then decode should produce same values
TEST(CodecSensorDataTest, RoundTrip)
{
  ds10_protocol::SensorData sensor;
  sensor.flags = 0x00;
  sensor.seq = 1234;
  sensor.sensor_id = 0x05;
  sensor.reading = 23.456f;

  auto encoded = ds10_protocol::encode_sensor_data(sensor);
  auto decoded = ds10_protocol::decode_sensor_data(encoded);

  ASSERT_TRUE(decoded.has_value());
  EXPECT_EQ(decoded->flags, sensor.flags);
  EXPECT_EQ(decoded->seq, sensor.seq);
  EXPECT_EQ(decoded->sensor_id, sensor.sensor_id);
  EXPECT_FLOAT_EQ(decoded->reading, sensor.reading);
}

// Test seq boundary values
TEST(CodecSensorDataTest, SeqBoundaries)
{
  // seq = 0 (minimum)
  {
    ds10_protocol::SensorData sensor{0x00, 0, 0x01, 1.0f};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->seq, 0);
  }

  // seq = 65535 (maximum uint16_t)
  {
    ds10_protocol::SensorData sensor{0x00, 65535, 0x01, 1.0f};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->seq, 65535);
  }

  // seq wraparound: verify little-endian encoding
  // seq=0x1234 should encode as [0x34, 0x12]
  {
    ds10_protocol::SensorData sensor{0x00, 0x1234, 0x01, 1.0f};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);

    ASSERT_EQ(encoded.size(), 8u);
    EXPECT_EQ(encoded[1], 0x34);  // low byte
    EXPECT_EQ(encoded[2], 0x12);  // high byte

    auto decoded = ds10_protocol::decode_sensor_data(encoded);
    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->seq, 0x1234);
  }
}

// Test float special values
TEST(CodecSensorDataTest, FloatSpecialValues)
{
  // 0.0
  {
    ds10_protocol::SensorData sensor{0x00, 0, 0x01, 0.0f};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_FLOAT_EQ(decoded->reading, 0.0f);
  }

  // -0.0
  {
    ds10_protocol::SensorData sensor{0x00, 0, 0x01, -0.0f};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    // Note: -0.0f == 0.0f in IEEE 754, but bit pattern differs
    // We verify serialization doesn't crash
  }

  // Positive infinity
  {
    ds10_protocol::SensorData sensor{0x00, 0, 0x01, std::numeric_limits<float>::infinity()};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_TRUE(std::isinf(decoded->reading));
    EXPECT_GT(decoded->reading, 0);
  }

  // Negative infinity
  {
    ds10_protocol::SensorData sensor{0x00, 0, 0x01, -std::numeric_limits<float>::infinity()};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_TRUE(std::isinf(decoded->reading));
    EXPECT_LT(decoded->reading, 0);
  }

  // NaN
  {
    ds10_protocol::SensorData sensor{0x00, 0, 0x01, std::numeric_limits<float>::quiet_NaN()};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_TRUE(std::isnan(decoded->reading));
  }
}

// Test flags combinations
TEST(CodecSensorDataTest, FlagsVariations)
{
  // flags = 0x00 (no ACK request, typical for sensors)
  {
    ds10_protocol::SensorData sensor{0x00, 100, 0x01, 25.0f};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, 0x00);
  }

  // flags = 0x01 (error flag set)
  {
    ds10_protocol::SensorData sensor{0x01, 100, 0x01, 25.0f};
    auto encoded = ds10_protocol::encode_sensor_data(sensor);
    auto decoded = ds10_protocol::decode_sensor_data(encoded);

    ASSERT_TRUE(decoded.has_value());
    EXPECT_EQ(decoded->flags, 0x01);
  }
}

// Test error conditions
TEST(CodecSensorDataTest, DecodeErrors)
{
  // data.size() < 8 should return nullopt
  {
    std::vector<uint8_t> too_short = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06};  // 7 bytes
    auto decoded = ds10_protocol::decode_sensor_data(too_short);
    EXPECT_FALSE(decoded.has_value());
  }

  // Empty data
  {
    std::vector<uint8_t> empty;
    auto decoded = ds10_protocol::decode_sensor_data(empty);
    EXPECT_FALSE(decoded.has_value());
  }

  // Exactly 8 bytes should succeed
  {
    std::vector<uint8_t> valid_size = {0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00, 0x00};
    auto decoded = ds10_protocol::decode_sensor_data(valid_size);
    ASSERT_TRUE(decoded.has_value());
  }

  // More than 8 bytes should succeed (extra bytes ignored)
  {
    std::vector<uint8_t> extra = {0x00, 0x01, 0x00, 0x05, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF};
    auto decoded = ds10_protocol::decode_sensor_data(extra);
    ASSERT_TRUE(decoded.has_value());
  }
}

// Test encoded size
TEST(CodecSensorDataTest, EncodedSize)
{
  ds10_protocol::SensorData sensor{0x00, 100, 0x01, 42.0f};
  auto encoded = ds10_protocol::encode_sensor_data(sensor);

  // Should always be exactly 8 bytes: flags(1) + seq(2) + sensor_id(1) + reading(4)
  EXPECT_EQ(encoded.size(), 8u);
}
