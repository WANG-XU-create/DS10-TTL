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
#include <stdexcept>
#include <string>
#include <vector>

#include "ds10_relay/relay_node.hpp"
#include "ds10_relay/transaction.hpp"

namespace tx = ds10_relay::transaction;

namespace
{

std::vector<uint8_t> bytes_of(const std::string & s)
{
  return std::vector<uint8_t>(s.begin(), s.end());
}

}  // namespace

// The header lands exactly where the pyserial tools expect it:
// F1 F1 then the transaction number big-endian, then the payload.
TEST(Transaction, BuildByteLayout)
{
  auto out = tx::build(0x0102, bytes_of("hi"));
  ASSERT_TRUE(out.has_value());
  const std::vector<uint8_t> expected = {0xF1, 0xF1, 0x01, 0x02, 'h', 'i'};
  EXPECT_EQ(*out, expected);
}

// build -> parse_txn round-trips across the whole 16-bit range, including the
// boundaries where a sloppy shift or a signed type would break.
TEST(Transaction, TxnRoundTrip)
{
  for (uint32_t txn : {0u, 1u, 0x00FFu, 0x0100u, 0x7FFFu, 0x8000u, 0xFFFEu, 0xFFFFu}) {
    auto out = tx::build(static_cast<uint16_t>(txn), bytes_of("x"));
    ASSERT_TRUE(out.has_value()) << "txn=" << txn;
    auto got = tx::parse_txn(*out);
    ASSERT_TRUE(got.has_value()) << "txn=" << txn;
    EXPECT_EQ(*got, static_cast<uint16_t>(txn)) << "txn=" << txn;
  }
}

// An empty payload still produces a well-formed, parsable header.
TEST(Transaction, EmptyPayloadIsValid)
{
  auto out = tx::build(42, {});
  ASSERT_TRUE(out.has_value());
  EXPECT_EQ(out->size(), tx::kHeaderLen);
  EXPECT_TRUE(tx::has_header(*out));
  EXPECT_EQ(*tx::parse_txn(*out), 42u);
  EXPECT_TRUE(tx::strip_header(*out).empty());
}

// has_header rejects everything that is not a complete marker + txn.
TEST(Transaction, HasHeaderRejectsMalformed)
{
  EXPECT_FALSE(tx::has_header({}));                          // empty
  EXPECT_FALSE(tx::has_header({0xF1}));                      // 1 byte
  EXPECT_FALSE(tx::has_header({0xF1, 0xF1}));                // marker only
  EXPECT_FALSE(tx::has_header({0xF1, 0xF1, 0x00}));          // truncated txn
  EXPECT_FALSE(tx::has_header({0xF1, 0xF2, 0x00, 0x01}));    // wrong 2nd marker
  EXPECT_FALSE(tx::has_header({0x01, 0xF1, 0x00, 0x01}));    // wrong 1st marker
  EXPECT_TRUE(tx::has_header({0xF1, 0xF1, 0x00, 0x01}));     // exactly a header
}

// parse_txn on headerless data reports absence rather than inventing a number.
TEST(Transaction, ParseTxnWithoutHeader)
{
  EXPECT_FALSE(tx::parse_txn(bytes_of("plain text")).has_value());
  EXPECT_FALSE(tx::parse_txn({}).has_value());
  EXPECT_FALSE(tx::parse_txn({0xF1, 0xF1, 0x00}).has_value());
}

// strip_header removes a real header and leaves foreign data untouched, which
// is what makes it safe to call on frames from other senders.
TEST(Transaction, StripHeader)
{
  auto framed = tx::build(7, bytes_of("payload"));
  ASSERT_TRUE(framed.has_value());
  EXPECT_EQ(tx::strip_header(*framed), bytes_of("payload"));

  const auto foreign = bytes_of("no header here");
  EXPECT_EQ(tx::strip_header(foreign), foreign);

  const std::vector<uint8_t> truncated = {0xF1, 0xF1, 0x00};
  EXPECT_EQ(tx::strip_header(truncated), truncated);
}

// A payload at the cap fits and fills the data field exactly; one byte more is
// refused, so the relay rejects it before the driver counts a tx_rejected.
TEST(Transaction, PayloadCapBoundary)
{
  const std::vector<uint8_t> at_cap(tx::kMaxPayload, 0x5A);
  auto ok = tx::build(1, at_cap);
  ASSERT_TRUE(ok.has_value());
  EXPECT_EQ(ok->size(), tx::kMaxData);

  const std::vector<uint8_t> over_cap(tx::kMaxPayload + 1, 0x5A);
  EXPECT_FALSE(tx::build(1, over_cap).has_value());
}

// Wire compatibility with the Python relay: these are the exact bytes observed
// on /slave1/rx during the hardware-side test (f1 f1 00 01 + "Hello中文"
// UTF-8). If the C++ layout ever diverges from the pyserial tools, this fails.
TEST(Transaction, DecodesPythonCapturedFrame)
{
  const std::vector<uint8_t> captured = {
    0xF1, 0xF1, 0x00, 0x01,                          // marker + txn=1
    'H', 'e', 'l', 'l', 'o',                         // "Hello"
    0xE4, 0xB8, 0xAD, 0xE6, 0x96, 0x87               // "中文" in UTF-8
  };
  ASSERT_TRUE(tx::has_header(captured));
  EXPECT_EQ(*tx::parse_txn(captured), 1u);

  const auto payload = tx::strip_header(captured);
  EXPECT_EQ(payload.size(), 11u);   // 5 ASCII + 6 UTF-8 continuation bytes
  EXPECT_EQ(payload, bytes_of("Hello\xE4\xB8\xAD\xE6\x96\x87"));

  // And the same bytes come back out of build(), proving encode/decode agree
  // with the captured wire format rather than merely with each other.
  auto rebuilt = tx::build(1, payload);
  ASSERT_TRUE(rebuilt.has_value());
  EXPECT_EQ(*rebuilt, captured);
}

// A payload whose first bytes happen to look like a marker is still stripped
// only once — strip_header must not recurse into user data.
TEST(Transaction, PayloadContainingMarkerStrippedOnce)
{
  const std::vector<uint8_t> payload = {0xF1, 0xF1, 0x09, 0x09, 'z'};
  auto framed = tx::build(3, payload);
  ASSERT_TRUE(framed.has_value());
  EXPECT_EQ(*tx::parse_txn(*framed), 3u);
  EXPECT_EQ(tx::strip_header(*framed), payload);
}

// ---- reply header: the slave-chosen forwarding target ----

// The dst byte sits immediately after the transaction number, and the reply
// uses its own second marker byte so the format is self-describing.
TEST(Transaction, BuildReplyByteLayout)
{
  auto out = tx::build_reply(0x0102, 7, bytes_of("hi"));
  ASSERT_TRUE(out.has_value());
  const std::vector<uint8_t> expected = {0xF1, 0xF2, 0x01, 0x02, 0x07, 'h', 'i'};
  EXPECT_EQ(*out, expected);
}

// A reply round-trips txn, dst and payload independently of each other.
TEST(Transaction, ReplyRoundTrip)
{
  for (uint32_t dst : {0u, 1u, 2u, 100u, 247u}) {
    auto out = tx::build_reply(0xBEEF, static_cast<uint8_t>(dst), bytes_of("data"));
    ASSERT_TRUE(out.has_value()) << "dst=" << dst;
    EXPECT_EQ(*tx::parse_txn(*out), 0xBEEFu) << "dst=" << dst;
    ASSERT_TRUE(tx::parse_dst(*out).has_value()) << "dst=" << dst;
    EXPECT_EQ(*tx::parse_dst(*out), static_cast<uint8_t>(dst)) << "dst=" << dst;
    EXPECT_EQ(tx::strip_reply_header(*out), bytes_of("data")) << "dst=" << dst;
  }
}

// THE misrouting guard. A request-format frame must never yield a dst, however
// long it is. Length alone cannot separate requests from replies, and printable
// ASCII (32..126) lies wholly inside the legal station range (1..247), so
// reading data[4] of an `F1 F1` frame would forward "Hello" to station 72 —
// silent misdelivery. The distinct reply marker is what prevents that.
TEST(Transaction, RequestFormatNeverYieldsDst)
{
  // Empty payload: too short to hold a dst at all.
  auto bare = tx::build(1, {});
  ASSERT_TRUE(bare.has_value());
  EXPECT_FALSE(tx::parse_dst(*bare).has_value());

  // Long enough to *contain* a fifth byte, and that byte is a legal station
  // number. Only the marker check saves us here.
  auto texty = tx::build(1, bytes_of("Hello"));
  ASSERT_TRUE(texty.has_value());
  ASSERT_GT(texty->size(), tx::kReplyHeaderLen);
  EXPECT_EQ((*texty)[tx::kHeaderLen], 'H');          // 72, a legal station id
  EXPECT_TRUE(tx::is_forwardable('H'));              // ... and forwardable
  EXPECT_FALSE(tx::parse_dst(*texty).has_value());   // yet refused: not a reply
  EXPECT_FALSE(tx::has_reply_header(*texty));

  // Nor is the payload eaten by the reply-stripping path.
  EXPECT_EQ(tx::strip_reply_header(*texty), *texty);
}

// Requests and replies are mutually exclusive: neither predicate accepts the
// other's frames, so a mixed-version peer is detected rather than guessed at.
TEST(Transaction, RequestAndReplyAreDisjoint)
{
  auto request = tx::build(5, bytes_of("payload"));
  auto reply = tx::build_reply(5, 2, bytes_of("payload"));
  ASSERT_TRUE(request.has_value() && reply.has_value());

  EXPECT_TRUE(tx::has_header(*request));
  EXPECT_FALSE(tx::has_reply_header(*request));

  EXPECT_TRUE(tx::has_reply_header(*reply));
  EXPECT_FALSE(tx::has_header(*reply));

  // Both still expose the transaction number: pairing works across both forms.
  EXPECT_EQ(*tx::parse_txn(*request), 5u);
  EXPECT_EQ(*tx::parse_txn(*reply), 5u);
}

// dst=0 is the explicit "answer me but do not forward" signal, and is
// distinguishable from a station id.
TEST(Transaction, NoForwardIsNotForwardable)
{
  EXPECT_EQ(tx::kNoForward, 0u);
  EXPECT_FALSE(tx::is_forwardable(tx::kNoForward));
}

// Only real Modbus station ids are forwardable: the driver's decoder rejects a
// leading byte outside 1..247, so anything else could never be delivered.
TEST(Transaction, IsForwardableStationRange)
{
  EXPECT_FALSE(tx::is_forwardable(0));
  EXPECT_TRUE(tx::is_forwardable(1));
  EXPECT_TRUE(tx::is_forwardable(2));
  EXPECT_TRUE(tx::is_forwardable(247));
  EXPECT_FALSE(tx::is_forwardable(248));
  EXPECT_FALSE(tx::is_forwardable(255));
}

// A reply needs the full 5-byte header; a truncated one is not a reply.
TEST(Transaction, HasReplyHeaderNeedsDstByte)
{
  const std::vector<uint8_t> four = {0xF1, 0xF2, 0x00, 0x01};
  EXPECT_FALSE(tx::has_reply_header(four));          // marker right, too short

  const std::vector<uint8_t> five = {0xF1, 0xF2, 0x00, 0x01, 0x02};
  EXPECT_TRUE(tx::has_reply_header(five));
  EXPECT_TRUE(tx::strip_reply_header(five).empty());

  const std::vector<uint8_t> bad_marker = {0xF1, 0xF3, 0x00, 0x01, 0x02};
  EXPECT_FALSE(tx::has_reply_header(bad_marker));
  // Not a reply, so returned untouched rather than losing 5 bytes.
  EXPECT_EQ(tx::strip_reply_header(bad_marker), bad_marker);
}

// The reply cap is one byte tighter than the request cap, since dst costs a
// byte. Both must land exactly on kMaxData.
TEST(Transaction, ReplyPayloadCapBoundary)
{
  EXPECT_EQ(tx::kMaxReplyPayload, tx::kMaxPayload - 1);

  const std::vector<uint8_t> at_cap(tx::kMaxReplyPayload, 0x5A);
  auto ok = tx::build_reply(1, 2, at_cap);
  ASSERT_TRUE(ok.has_value());
  EXPECT_EQ(ok->size(), tx::kMaxData);

  const std::vector<uint8_t> over_cap(tx::kMaxReplyPayload + 1, 0x5A);
  EXPECT_FALSE(tx::build_reply(1, 2, over_cap).has_value());
}

// ---- route_map: the responder's content -> station decision ----

using ds10_relay::RelayNode;

TEST(RouteMap, ParsesEntries)
{
  auto routes = RelayNode::parse_route_map("temp:2,humid:3,alarm:4");
  ASSERT_EQ(routes.size(), 3u);
  EXPECT_EQ(routes[0].keyword, "temp");
  EXPECT_EQ(routes[0].station, 2);
  EXPECT_EQ(routes[2].keyword, "alarm");
  EXPECT_EQ(routes[2].station, 4);
}

// Whitespace around entries is tolerated so a YAML config can breathe.
TEST(RouteMap, ToleratesWhitespaceAndTrailingComma)
{
  auto routes = RelayNode::parse_route_map(" temp:2,  humid:3 ,");
  ASSERT_EQ(routes.size(), 2u);
  EXPECT_EQ(routes[0].keyword, "temp");
  EXPECT_EQ(routes[1].keyword, "humid");
  EXPECT_EQ(routes[1].station, 3);
}

TEST(RouteMap, EmptySpecYieldsNoRoutes)
{
  EXPECT_TRUE(RelayNode::parse_route_map("").empty());
  EXPECT_TRUE(RelayNode::parse_route_map("   ").empty());
}

// A malformed or out-of-range entry must fail loudly at startup. Silently
// dropping it would leave the responder routing nothing while looking healthy.
TEST(RouteMap, RejectsMalformedEntries)
{
  EXPECT_THROW(RelayNode::parse_route_map("temp"), std::invalid_argument);
  EXPECT_THROW(RelayNode::parse_route_map("temp:"), std::invalid_argument);
  EXPECT_THROW(RelayNode::parse_route_map(":2"), std::invalid_argument);
  EXPECT_THROW(RelayNode::parse_route_map("temp:abc"), std::invalid_argument);
  EXPECT_THROW(RelayNode::parse_route_map("temp:2x"), std::invalid_argument);
  EXPECT_THROW(RelayNode::parse_route_map("temp:0"), std::invalid_argument);
  EXPECT_THROW(RelayNode::parse_route_map("temp:248"), std::invalid_argument);
  EXPECT_THROW(RelayNode::parse_route_map("temp:-1"), std::invalid_argument);
}

// A keyword may contain a colon; only the last one separates the station.
TEST(RouteMap, KeywordMayContainColon)
{
  auto routes = RelayNode::parse_route_map("sensor:temp:5");
  ASSERT_EQ(routes.size(), 1u);
  EXPECT_EQ(routes[0].keyword, "sensor:temp");
  EXPECT_EQ(routes[0].station, 5);
}

TEST(RouteMap, LookupMatchesSubstring)
{
  const auto routes = RelayNode::parse_route_map("temp:2,humid:3");
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("temp=25.3"), 0), 2);
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("humid=60"), 0), 3);
  // Keyword anywhere in the payload, not just at the start.
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("sensor humid ok"), 0), 3);
}

// No match falls back to default_dst, which is how "answer but do not forward"
// stays the safe default.
TEST(RouteMap, LookupFallsBackToDefault)
{
  const auto routes = RelayNode::parse_route_map("temp:2");
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("unrelated"), 0), 0);
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("unrelated"), 9), 9);
  // An empty table always falls back.
  EXPECT_EQ(RelayNode::route_lookup({}, bytes_of("temp=1"), 7), 7);
}

// First match wins, so ordering in the parameter is meaningful and documented.
TEST(RouteMap, FirstMatchWins)
{
  const auto routes = RelayNode::parse_route_map("temp:2,temperature:3");
  // "temperature" contains "temp", so the earlier entry claims it.
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("temperature=20"), 0), 2);

  const auto reversed = RelayNode::parse_route_map("temperature:3,temp:2");
  EXPECT_EQ(RelayNode::route_lookup(reversed, bytes_of("temperature=20"), 0), 3);
  EXPECT_EQ(RelayNode::route_lookup(reversed, bytes_of("temp=20"), 0), 2);
}

// Routing keys off UTF-8 bytes, so Chinese keywords work without extra care.
TEST(RouteMap, LookupHandlesUtf8Keywords)
{
  const auto routes = RelayNode::parse_route_map("温度:2,湿度:3");
  ASSERT_EQ(routes.size(), 2u);
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("温度=25.3"), 0), 2);
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("湿度=60"), 0), 3);
  EXPECT_EQ(RelayNode::route_lookup(routes, bytes_of("气压=1013"), 0), 0);
}

// A binary payload must not crash the lookup or match by accident.
TEST(RouteMap, LookupOnBinaryPayload)
{
  const auto routes = RelayNode::parse_route_map("temp:2");
  const std::vector<uint8_t> binary = {0x00, 0x01, 0xFF, 0x00, 0x7F};
  EXPECT_EQ(RelayNode::route_lookup(routes, binary, 0), 0);
  EXPECT_EQ(RelayNode::route_lookup(routes, {}, 0), 0);
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
