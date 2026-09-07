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

#include "ds10_relay/transaction.hpp"

namespace ds10_relay
{
namespace transaction
{

bool has_header(const std::vector<uint8_t> & data)
{
  return data.size() >= kHeaderLen &&
         data[0] == kMarker0 &&
         data[1] == kMarker1;
}

bool has_reply_header(const std::vector<uint8_t> & data)
{
  // The second marker byte differs from a request's on purpose: length alone
  // cannot separate the two, and guessing would silently misroute.
  return data.size() >= kReplyHeaderLen &&
         data[0] == kMarker0 &&
         data[1] == kReplyMarker1;
}

std::optional<uint16_t> parse_txn(const std::vector<uint8_t> & data)
{
  if (!has_header(data) && !has_reply_header(data)) {
    return std::nullopt;
  }
  // Big-endian, matching the pyserial tools' bytes((seq >> 8, seq & 0xFF)).
  return static_cast<uint16_t>((data[2] << 8) | data[3]);
}

std::optional<uint8_t> parse_dst(const std::vector<uint8_t> & data)
{
  if (!has_reply_header(data)) {
    return std::nullopt;
  }
  return data[kHeaderLen];
}

bool is_forwardable(uint8_t dst)
{
  return dst >= kMinStation && dst <= kMaxStation;
}

std::optional<std::vector<uint8_t>> build(
  uint16_t txn, const std::vector<uint8_t> & payload)
{
  if (payload.size() > kMaxPayload) {
    return std::nullopt;
  }
  std::vector<uint8_t> out;
  out.reserve(kHeaderLen + payload.size());
  out.push_back(kMarker0);
  out.push_back(kMarker1);
  out.push_back(static_cast<uint8_t>((txn >> 8) & 0xFF));
  out.push_back(static_cast<uint8_t>(txn & 0xFF));
  out.insert(out.end(), payload.begin(), payload.end());
  return out;
}

std::optional<std::vector<uint8_t>> build_reply(
  uint16_t txn, uint8_t dst, const std::vector<uint8_t> & payload)
{
  if (payload.size() > kMaxReplyPayload) {
    return std::nullopt;
  }
  std::vector<uint8_t> out;
  out.reserve(kReplyHeaderLen + payload.size());
  out.push_back(kMarker0);
  out.push_back(kReplyMarker1);
  out.push_back(static_cast<uint8_t>((txn >> 8) & 0xFF));
  out.push_back(static_cast<uint8_t>(txn & 0xFF));
  out.push_back(dst);
  out.insert(out.end(), payload.begin(), payload.end());
  return out;
}

std::vector<uint8_t> strip_header(const std::vector<uint8_t> & data)
{
  if (!has_header(data)) {
    return data;
  }
  return std::vector<uint8_t>(data.begin() + kHeaderLen, data.end());
}

std::vector<uint8_t> strip_reply_header(const std::vector<uint8_t> & data)
{
  if (!has_reply_header(data)) {
    return data;
  }
  return std::vector<uint8_t>(data.begin() + kReplyHeaderLen, data.end());
}

}  // namespace transaction
}  // namespace ds10_relay
