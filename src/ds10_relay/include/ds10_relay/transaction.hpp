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

#ifndef DS10_RELAY__TRANSACTION_HPP_
#define DS10_RELAY__TRANSACTION_HPP_

#include <cstdint>
#include <optional>
#include <vector>

namespace ds10_relay
{

/// Transaction header carried at the head of the Modbus data field.
///
/// Requests (master -> slave) carry a 4-byte header:
///     `[0xF1][0xF1][txn_hi][txn_lo][payload...]`
/// Replies (slave -> master) use a *different second marker byte* and add the
/// forwarding target the slave chose:
///     `[0xF1][0xF2][txn_hi][txn_lo][dst][payload...]`
///
/// The distinct reply marker is load-bearing, not cosmetic. Requests and
/// replies overlap in length, so length alone cannot tell them apart: a
/// 4-byte-header reply from a peer that predates slave-driven routing would
/// have its first payload byte read as `dst`, and since printable ASCII
/// (32..126) lies entirely inside the legal station range (1..247), a payload
/// like "Hello" would be forwarded to station 72. Silent misrouting is worse
/// than a drop, so the format is self-describing: `F1 F2` means "this frame
/// carries a dst", and an `F1 F1` frame arriving where a reply is expected is
/// rejected and counted rather than guessed at.
///
/// `dst` is the slave's decision, not the master's: the slave inspects its own
/// payload and names the station the reply should be relayed to, or 0 to ask
/// for no forwarding at all. The master only sanity-checks the value; it does
/// not override it. That is what makes routing content-driven — adding a new
/// destination needs no master-side reconfiguration.
///
/// Why a header inside `data` rather than a new wire field: `ds10_driver`
/// encodes only station id, function code and data, so `Frame.tx_seq` never
/// reaches the air. Request/reply pairing therefore needs an in-payload
/// sequence number. The 0xF1 lead byte and big-endian layout match the pyserial
/// tools under `DS10_Modbus/test/`, so C++ and Python nodes interoperate on the
/// wire. Widening the link frame instead would break those 11 raw-serial
/// scripts and re-introduce the stacked application frame that
/// `.scratch/ds10-modbus-driver/spec.md` deliberately rejected.
///
/// Pure logic: no ROS types, no I/O — unit-testable in isolation (test seam 1).
namespace transaction
{

/// Marker bytes announcing a request header.
constexpr uint8_t kMarker0 = 0xF1;
constexpr uint8_t kMarker1 = 0xF1;

/// Second marker byte announcing a reply header (one that carries `dst`).
constexpr uint8_t kReplyMarker1 = 0xF2;

/// Request header size: 2 marker bytes + 2 transaction-number bytes.
constexpr std::size_t kHeaderLen = 4;

/// Reply header size: markers + transaction number + destination byte.
constexpr std::size_t kReplyHeaderLen = kHeaderLen + 1;

/// `dst` value meaning "do not forward this reply anywhere".
constexpr uint8_t kNoForward = 0;

/// Modbus station id bounds. The driver's decoder only accepts a leading byte
/// in 1..247, so a destination outside this range could never be delivered.
constexpr uint8_t kMinStation = 1;
constexpr uint8_t kMaxStation = 247;

/// Largest `data` field the driver will accept. The DS10 single-frame ceiling
/// is 4095 B on the wire and the Modbus frame spends 2 B on station + function
/// code and 2 B on the CRC, leaving 4091 B for `data`.
constexpr std::size_t kMaxData = 4091;

/// Largest payload that still fits once the request header is prepended.
constexpr std::size_t kMaxPayload = kMaxData - kHeaderLen;

/// Largest payload that still fits once the reply header is prepended.
constexpr std::size_t kMaxReplyPayload = kMaxData - kReplyHeaderLen;

/// True when `data` carries a request header (`F1 F1` + transaction number).
/// A 3-byte truncated header is not a header.
bool has_header(const std::vector<uint8_t> & data);

/// True when `data` carries a reply header (`F1 F2` + transaction number +
/// dst). Deliberately false for a request: the markers differ.
bool has_reply_header(const std::vector<uint8_t> & data);

/// Transaction number from either a request or a reply header, or nullopt when
/// `data` carries neither.
std::optional<uint16_t> parse_txn(const std::vector<uint8_t> & data);

/// Forwarding target a slave asked for, or nullopt when `data` is not a reply.
/// Returns kNoForward when the slave declined forwarding; the value is returned
/// as sent, so callers must validate it against the station range.
std::optional<uint8_t> parse_dst(const std::vector<uint8_t> & data);

/// True when `dst` names a station a reply can actually be forwarded to.
/// kNoForward and out-of-range ids are both rejected.
bool is_forwardable(uint8_t dst);

/// Build a request: `[F1 F1][txn][payload]`. Returns nullopt when the result
/// would exceed kMaxData, so callers reject oversized payloads before the
/// driver does (the driver would otherwise count it as tx_rejected).
std::optional<std::vector<uint8_t>> build(
  uint16_t txn, const std::vector<uint8_t> & payload);

/// Build a reply: `[F1 F2][txn][dst][payload]`. Returns nullopt when the
/// result would exceed kMaxData.
std::optional<std::vector<uint8_t>> build_reply(
  uint16_t txn, uint8_t dst, const std::vector<uint8_t> & payload);

/// Payload with the request header removed. Data that is not a request is
/// returned unchanged, so this is safe to call on foreign frames.
std::vector<uint8_t> strip_header(const std::vector<uint8_t> & data);

/// Payload with the reply header (including `dst`) removed. Data that is not a
/// reply is returned unchanged.
std::vector<uint8_t> strip_reply_header(const std::vector<uint8_t> & data);

}  // namespace transaction

}  // namespace ds10_relay

#endif  // DS10_RELAY__TRANSACTION_HPP_
