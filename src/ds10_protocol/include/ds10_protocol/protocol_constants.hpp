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

#ifndef DS10_PROTOCOL__PROTOCOL_CONSTANTS_HPP_
#define DS10_PROTOCOL__PROTOCOL_CONSTANTS_HPP_

#include <cstdint>

/// @brief DS10 Application Protocol constants and registry
/// @details Defines function codes, flags bits, and field sizes for the
///          DS10 application-layer protocol built on top of ds10_driver's
///          Modbus RTU frame transport.
///          Specification: application_protocol_v1.md
namespace ds10_protocol
{

// ============================================================================
// Function Code Registry (8-bit, 0x00-0xFF)
// ============================================================================

/// @defgroup protocol_control Protocol Control Messages (0x00-0x0F)
/// @{

/// Function code 0x00: ACK (Acknowledgment)
/// data = [acked_seq: u16][acked_function_code: u8]
/// See application_protocol_v1.md §功能码 0x00
constexpr uint8_t FUNC_ACK = 0x00;

/// Function code 0x01: NACK (Negative Acknowledgment) - Reserved for v2
constexpr uint8_t FUNC_NACK = 0x01;

/// Function code 0x02: Heartbeat - Reserved for v2
constexpr uint8_t FUNC_HEARTBEAT = 0x02;

/// Function code 0x03: Time Sync - Reserved for v2
constexpr uint8_t FUNC_TIME_SYNC = 0x03;

/// Function code 0x0F: Protocol Version Negotiation - Reserved for v2
constexpr uint8_t FUNC_VERSION_NEGO = 0x0F;

/// @}

/// @defgroup application_data Application Data Messages (0x10-0x7F)
/// @{

/// Function code 0x10: Sensor Data Report
/// data = [flags: u8][seq: u16][sensor_id: u8][reading: 4B float, little-endian]
/// See application_protocol_v1.md §功能码 0x10
constexpr uint8_t FUNC_SENSOR_DATA = 0x10;

/// Function code 0x11: Log Message
/// data = [flags: u8][seq: u16][log_level: u8][text: UTF-8 string]
/// See application_protocol_v1.md §功能码 0x11
constexpr uint8_t FUNC_LOG = 0x11;

/// Function code 0x12: Control Command
/// data = [flags: u8][cmd_id: u8][params: variable length]
/// See application_protocol_v1.md §功能码 0x12
constexpr uint8_t FUNC_CONTROL_CMD = 0x12;

/// @}

/// @defgroup extended_features Extended Features (0x80-0xFF)
/// @{

/// Function code 0x80: Fragmented Frame - Reserved for v2
/// data = [fragment_id: u16][total_fragments: u8][current_fragment: u8][payload]
constexpr uint8_t FUNC_FRAGMENTED = 0x80;

/// @}

// ============================================================================
// Flags Field Bit Masks (1 byte, uint8)
// ============================================================================

/// Bit 0: Request ACK
/// If set (=1), receiver must send 0x00 ACK frame in response
/// See application_protocol_v1.md §公共字段定义 - flags
constexpr uint8_t FLAGS_REQUEST_ACK = 0x01;

/// Bit 1: Fragmented (reserved for v2)
/// Must be 0 in v1; receiver ignores this bit
constexpr uint8_t FLAGS_FRAGMENTED = 0x02;

/// Bits 2-7: Reserved
/// Must be 0 when sending; receiver ignores these bits
constexpr uint8_t FLAGS_RESERVED_MASK = 0xFC;

// ============================================================================
// Field Size Constants (bytes)
// ============================================================================

/// Size of flags field (1 byte, uint8)
constexpr size_t SIZEOF_FLAGS = 1;

/// Size of sequence number field (2 bytes, uint16 little-endian)
constexpr size_t SIZEOF_SEQ = 2;

/// Size of sensor_id field in 0x10 Sensor Data (1 byte)
constexpr size_t SIZEOF_SENSOR_ID = 1;

/// Size of reading field in 0x10 Sensor Data (4 bytes, float32 little-endian)
constexpr size_t SIZEOF_READING = 4;

/// Size of cmd_id field in 0x12 Control Command (1 byte)
constexpr size_t SIZEOF_CMD_ID = 1;

/// Size of log_level field in 0x11 Log Message (1 byte)
constexpr size_t SIZEOF_LOG_LEVEL = 1;

// ============================================================================
// Frame Size Limits (bytes)
// ============================================================================

/// Maximum DS10 frame size (Modbus RTU constraint)
/// Frame structure: [station 1B][function_code 1B][data ...][CRC 2B]
/// Total frame <= 4095B
constexpr size_t MAX_FRAME_SIZE = 4095;

/// Maximum data field size in a DS10 frame
/// data_max = MAX_FRAME_SIZE - station - function_code - CRC
/// data_max = 4095 - 1 - 1 - 2 = 4091B
constexpr size_t MAX_DATA_SIZE = MAX_FRAME_SIZE - 1 - 1 - 2;

/// Maximum params size for 0x12 Control Command
/// For 0x12: data = [flags 1B][cmd_id 1B][params ...]
/// params_max = MAX_DATA_SIZE - flags - cmd_id = 4091 - 2 = 4089B
constexpr size_t MAX_CONTROL_PARAMS_SIZE = MAX_DATA_SIZE - SIZEOF_FLAGS - SIZEOF_CMD_ID;

}  // namespace ds10_protocol

#endif  // DS10_PROTOCOL__PROTOCOL_CONSTANTS_HPP_
