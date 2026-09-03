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

/// @file
/// @brief Validate the C++ codec against the shared wire-format vectors.
///
/// The Python reference codec checks itself against the same
/// protocol_test_vectors.json. That shared file is the whole point: two
/// implementations written from the same prose disagree exactly where the
/// prose is ambiguous, and pinning both to bytes derived by hand from the
/// spec turns such a disagreement into a failing test on one side or the
/// other. Tests private to each language could never catch it.

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include "ds10_protocol/codec.hpp"
#include "nlohmann/json.hpp"

namespace
{

/// Path to the vector file, passed in by CMake so the test does not have to
/// guess where the build tree sits relative to the source.
const char * vectors_path()
{
  const char * from_env = std::getenv("DS10_PROTOCOL_TEST_VECTORS");
  return from_env != nullptr ? from_env : "protocol_test_vectors.json";
}

// The helpers below throw rather than EXPECT_ on bad input. EXPECT_ does not
// return, so a helper that used it would carry on and hand back a garbage
// value -- an unopened file yields a null json whose .at() then throws
// something unrelated, and an unrecognised reading name would silently become
// NaN, which the NaN branch of the decode test would accept. Throwing puts
// the diagnosis in the failure message where it belongs.

nlohmann::json load_vectors()
{
  std::ifstream file(vectors_path());
  if (!file.is_open()) {
    throw std::runtime_error(std::string("cannot open vector file: ") + vectors_path());
  }
  nlohmann::json doc;
  file >> doc;
  return doc.at("vectors");
}

/// "0105AABB" -> {0x01, 0x05, 0xAA, 0xBB}.
std::vector<uint8_t> from_hex(const std::string & hex)
{
  if (hex.size() % 2 != 0) {
    throw std::runtime_error("hex string has an odd length: " + hex);
  }
  std::vector<uint8_t> bytes;
  bytes.reserve(hex.size() / 2);
  for (size_t i = 0; i + 1 < hex.size(); i += 2) {
    bytes.push_back(static_cast<uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16)));
  }
  return bytes;
}

std::string to_hex(const std::vector<uint8_t> & bytes)
{
  static const char * kDigits = "0123456789ABCDEF";
  std::string hex;
  hex.reserve(bytes.size() * 2);
  for (const uint8_t byte : bytes) {
    hex.push_back(kDigits[byte >> 4]);
    hex.push_back(kDigits[byte & 0x0F]);
  }
  return hex;
}

/// Resolve a vector's `reading`, which is a number or one of the strings
/// "inf" / "-inf" / "nan" -- JSON has no literal for those three.
float reading_of(const nlohmann::json & value)
{
  if (!value.is_string()) {
    return value.get<float>();
  }
  const std::string name = value.get<std::string>();
  if (name == "inf") {
    return std::numeric_limits<float>::infinity();
  }
  if (name == "-inf") {
    return -std::numeric_limits<float>::infinity();
  }
  if (name == "nan") {
    return std::numeric_limits<float>::quiet_NaN();
  }
  throw std::runtime_error("unknown special reading: " + name);
}

}  // namespace

TEST(ProtocolVectors, FileIsPresentAndCoversBothTypes) {
  // A vector file that failed to load would make every other test in here
  // pass vacuously, having iterated over nothing.
  const auto vectors = load_vectors();
  ASSERT_FALSE(vectors.empty()) << "no vectors loaded from " << vectors_path();

  size_t control = 0;
  size_t sensor = 0;
  for (const auto & vector : vectors) {
    const std::string type = vector.at("type");
    if (type == "0x12") {
      ++control;
    } else if (type == "0x10") {
      ++sensor;
    } else {
      ADD_FAILURE() << "vector of unknown type: " << type;
    }
  }

  EXPECT_GE(control, 4u) << "too few 0x12 vectors to be meaningful";
  EXPECT_GE(sensor, 4u) << "too few 0x10 vectors to be meaningful";
}

TEST(ProtocolVectors, EncodingMatchesTheSpecifiedBytes) {
  for (const auto & vector : load_vectors()) {
    const std::string name = vector.at("name");
    const auto & input = vector.at("input");
    const std::string expected = vector.at("expected_bytes");
    const std::string type = vector.at("type");

    std::vector<uint8_t> encoded;
    if (type == "0x12") {
      ds10_protocol::ControlCommand cmd;
      cmd.flags = input.at("flags").get<uint8_t>();
      cmd.cmd_id = input.at("cmd_id").get<uint8_t>();
      cmd.params = from_hex(input.at("params").get<std::string>());
      encoded = ds10_protocol::encode_control_command(cmd);
    } else {
      ds10_protocol::SensorData sensor;
      sensor.flags = input.at("flags").get<uint8_t>();
      sensor.seq = input.at("seq").get<uint16_t>();
      sensor.sensor_id = input.at("sensor_id").get<uint8_t>();
      sensor.reading = reading_of(input.at("reading"));
      encoded = ds10_protocol::encode_sensor_data(sensor);
    }

    EXPECT_EQ(to_hex(encoded), expected) << "vector: " << name;
  }
}

TEST(ProtocolVectors, DecodingRecoversTheOriginalFields) {
  for (const auto & vector : load_vectors()) {
    const std::string name = vector.at("name");
    const auto & input = vector.at("input");
    const auto bytes = from_hex(vector.at("expected_bytes").get<std::string>());

    // `continue` rather than ASSERT_ on the has_value checks: ASSERT_ returns
    // from the whole TEST, so one undecodable vector would hide every vector
    // after it. Skipping to the next keeps the run reporting all of them,
    // which is the reason to iterate here in the first place.
    if (vector.at("type") == "0x12") {
      const auto decoded = ds10_protocol::decode_control_command(bytes);
      EXPECT_TRUE(decoded.has_value()) << "vector: " << name;
      if (!decoded) {
        continue;
      }
      EXPECT_EQ(decoded->flags, input.at("flags").get<uint8_t>()) << name;
      EXPECT_EQ(decoded->cmd_id, input.at("cmd_id").get<uint8_t>()) << name;
      EXPECT_EQ(decoded->params, from_hex(input.at("params").get<std::string>())) << name;
    } else {
      const auto decoded = ds10_protocol::decode_sensor_data(bytes);
      EXPECT_TRUE(decoded.has_value()) << "vector: " << name;
      if (!decoded) {
        continue;
      }
      EXPECT_EQ(decoded->flags, input.at("flags").get<uint8_t>()) << name;
      EXPECT_EQ(decoded->seq, input.at("seq").get<uint16_t>()) << name;
      EXPECT_EQ(decoded->sensor_id, input.at("sensor_id").get<uint8_t>()) << name;

      const float expected_reading = reading_of(input.at("reading"));
      if (std::isnan(expected_reading)) {
        EXPECT_TRUE(std::isnan(decoded->reading)) << name;
      } else {
        // Exact equality, not a tolerance: these bytes must reproduce the
        // value bit for bit, and a tolerance would hide a mangled mantissa.
        EXPECT_EQ(decoded->reading, expected_reading) << name;
      }
    }
  }
}
