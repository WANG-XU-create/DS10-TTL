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
#include "ds10_protocol/protocol_constants.hpp"

// Test function code ranges
TEST(ProtocolConstantsTest, FunctionCodeRanges)
{
  // Protocol control messages (0x00-0x0F)
  EXPECT_EQ(ds10_protocol::FUNC_ACK, 0x00);
  EXPECT_EQ(ds10_protocol::FUNC_NACK, 0x01);
  EXPECT_EQ(ds10_protocol::FUNC_HEARTBEAT, 0x02);
  EXPECT_EQ(ds10_protocol::FUNC_TIME_SYNC, 0x03);
  EXPECT_EQ(ds10_protocol::FUNC_VERSION_NEGO, 0x0F);
  EXPECT_LE(ds10_protocol::FUNC_VERSION_NEGO, 0x0F);  // Last control message in range

  // Application data messages (0x10-0x7F)
  EXPECT_EQ(ds10_protocol::FUNC_SENSOR_DATA, 0x10);
  EXPECT_EQ(ds10_protocol::FUNC_LOG, 0x11);
  EXPECT_EQ(ds10_protocol::FUNC_CONTROL_CMD, 0x12);
  EXPECT_GE(ds10_protocol::FUNC_SENSOR_DATA, 0x10);
  EXPECT_LE(ds10_protocol::FUNC_CONTROL_CMD, 0x7F);

  // Extended features (0x80-0xFF)
  EXPECT_EQ(ds10_protocol::FUNC_FRAGMENTED, 0x80);
  EXPECT_GE(ds10_protocol::FUNC_FRAGMENTED, 0x80);
}

// Test flags bit masks
TEST(ProtocolConstantsTest, FlagsBitMasks)
{
  // Bit 0: REQUEST_ACK
  EXPECT_EQ(ds10_protocol::FLAGS_REQUEST_ACK, 0x01);
  EXPECT_EQ(ds10_protocol::FLAGS_REQUEST_ACK, 1 << 0);

  // Bit 1: FRAGMENTED
  EXPECT_EQ(ds10_protocol::FLAGS_FRAGMENTED, 0x02);
  EXPECT_EQ(ds10_protocol::FLAGS_FRAGMENTED, 1 << 1);

  // Bits 2-7: RESERVED
  EXPECT_EQ(ds10_protocol::FLAGS_RESERVED_MASK, 0xFC);
  EXPECT_EQ(ds10_protocol::FLAGS_RESERVED_MASK, 0xFF & ~0x03);  // All bits except 0-1

  // Flags should be mutually exclusive
  EXPECT_EQ(ds10_protocol::FLAGS_REQUEST_ACK & ds10_protocol::FLAGS_FRAGMENTED, 0);
  EXPECT_EQ(ds10_protocol::FLAGS_REQUEST_ACK & ds10_protocol::FLAGS_RESERVED_MASK, 0);
  EXPECT_EQ(ds10_protocol::FLAGS_FRAGMENTED & ds10_protocol::FLAGS_RESERVED_MASK, 0);
}

// Test field size constants
TEST(ProtocolConstantsTest, FieldSizes)
{
  EXPECT_EQ(ds10_protocol::SIZEOF_FLAGS, 1);
  EXPECT_EQ(ds10_protocol::SIZEOF_SEQ, 2);
  EXPECT_EQ(ds10_protocol::SIZEOF_SENSOR_ID, 1);
  EXPECT_EQ(ds10_protocol::SIZEOF_READING, 4);
  EXPECT_EQ(ds10_protocol::SIZEOF_CMD_ID, 1);
  EXPECT_EQ(ds10_protocol::SIZEOF_LOG_LEVEL, 1);

  // Verify sizes match expected types
  EXPECT_EQ(ds10_protocol::SIZEOF_FLAGS, sizeof(uint8_t));
  EXPECT_EQ(ds10_protocol::SIZEOF_SEQ, sizeof(uint16_t));
  EXPECT_EQ(ds10_protocol::SIZEOF_READING, sizeof(float));
}

// Test minimum frame sizes for each function code
TEST(ProtocolConstantsTest, MinimumFrameSizes)
{
  // 0x00 ACK: [acked_seq: u16][acked_function_code: u8] = 3 bytes
  constexpr size_t ACK_MIN_SIZE = ds10_protocol::SIZEOF_SEQ + 1;
  EXPECT_EQ(ACK_MIN_SIZE, 3);

  // 0x10 Sensor Data: [flags][seq][sensor_id][reading] = 8 bytes
  constexpr size_t SENSOR_MIN_SIZE = ds10_protocol::SIZEOF_FLAGS + ds10_protocol::SIZEOF_SEQ +
    ds10_protocol::SIZEOF_SENSOR_ID + ds10_protocol::SIZEOF_READING;
  EXPECT_EQ(SENSOR_MIN_SIZE, 8);

  // 0x12 Control Command: [flags][cmd_id][params...] >= 2 bytes
  constexpr size_t CONTROL_MIN_SIZE = ds10_protocol::SIZEOF_FLAGS + ds10_protocol::SIZEOF_CMD_ID;
  EXPECT_EQ(CONTROL_MIN_SIZE, 2);

  // 0x11 Log: [flags][seq][log_level][text...] >= 4 bytes (empty text)
  constexpr size_t LOG_MIN_SIZE = ds10_protocol::SIZEOF_FLAGS + ds10_protocol::SIZEOF_SEQ +
    ds10_protocol::SIZEOF_LOG_LEVEL;
  EXPECT_EQ(LOG_MIN_SIZE, 4);
}

int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
