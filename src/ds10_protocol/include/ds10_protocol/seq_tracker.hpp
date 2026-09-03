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

#ifndef DS10_PROTOCOL__SEQ_TRACKER_HPP_
#define DS10_PROTOCOL__SEQ_TRACKER_HPP_

#include <cstdint>
#include <map>
#include <utility>

namespace ds10_protocol
{

/// What a newly-arrived sequence number means for its stream.
enum class SeqVerdict
{
  kFirst,      ///< First frame on this stream; nothing to compare against.
  kInOrder,    ///< Exactly the expected sequence number.
  kGap,        ///< Ahead of expectation: frames were lost on the link.
  kDuplicate,  ///< Already seen, or arriving late. Dropped per §帧去留清单.
};

/// The outcome of classifying a sequence number, plus the value that was
/// expected at the time. Reporting a gap is only actionable if the log says
/// what was missed, so the expectation travels with the verdict.
struct SeqClassification
{
  SeqVerdict verdict;
  uint16_t expected;  ///< Meaningless when verdict is kFirst.
};

/// Tracks the expected sequence number of one message stream.
///
/// Sequence numbers are uint16 and wrap, so "ahead" and "behind" are decided
/// modulo 2^16 rather than by comparing magnitudes: the unsigned difference
/// `seq - expected` wraps by construction, and a difference in the lower half
/// of the space means ahead, the upper half means behind. That makes
/// 65535 -> 0 an ordinary increment while still recognising a genuinely old
/// sequence number as a duplicate.
class SeqTracker
{
public:
  /// Classify `seq` and advance the expectation to match what arrived.
  ///
  /// Gaps resynchronise on the received value rather than insisting on the
  /// lost one, so a single lost frame produces one warning, not a permanent
  /// offset. Duplicates leave the expectation untouched.
  SeqClassification classify(uint16_t seq)
  {
    if (!initialised_) {
      initialised_ = true;
      const uint16_t was_expecting = seq;
      expected_ = static_cast<uint16_t>(seq + 1);
      return {SeqVerdict::kFirst, was_expecting};
    }

    const uint16_t was_expecting = expected_;

    // Unsigned wraparound makes this the modular distance from expectation.
    const uint16_t ahead_by = static_cast<uint16_t>(seq - expected_);

    if (ahead_by == 0) {
      expected_ = static_cast<uint16_t>(seq + 1);
      return {SeqVerdict::kInOrder, was_expecting};
    }

    if (ahead_by < kBackwardsThreshold) {
      expected_ = static_cast<uint16_t>(seq + 1);
      return {SeqVerdict::kGap, was_expecting};
    }

    // Upper half of the space: behind the expectation, so a repeat or a
    // straggler. Leave `expected_` alone -- the stream is still waiting for
    // the frame that follows the newest one actually seen.
    return {SeqVerdict::kDuplicate, was_expecting};
  }

private:
  /// Distances at or beyond half the uint16 space read as backwards.
  static constexpr uint16_t kBackwardsThreshold = 32768;

  uint16_t expected_ = 0;
  bool initialised_ = false;
};

/// A `SeqTracker` per (station_id, function_code) stream.
///
/// One slave's dropped sensor frame must not look like a gap on another
/// slave's stream, nor on a different message type from the same slave.
class SeqTrackerTable
{
public:
  SeqClassification classify(uint8_t station_id, uint8_t function_code, uint16_t seq)
  {
    return trackers_[{station_id, function_code}].classify(seq);
  }

private:
  std::map<std::pair<uint8_t, uint8_t>, SeqTracker> trackers_;
};

}  // namespace ds10_protocol

#endif  // DS10_PROTOCOL__SEQ_TRACKER_HPP_
