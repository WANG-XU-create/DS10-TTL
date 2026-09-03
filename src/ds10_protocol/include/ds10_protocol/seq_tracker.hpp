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
/// Sequence numbers are uint16 and wrap, so ordering is decided modulo 2^16
/// rather than by comparing magnitudes: the unsigned difference wraps by
/// construction, which makes 65535 -> 0 an ordinary increment.
///
/// The question that decides whether a frame is dropped is narrow: *has this
/// sequence number already been delivered?* Only then is it a duplicate. A
/// frame that is merely far from the expectation has still never been seen,
/// so it is a gap -- resynchronising costs nothing, whereas withholding a
/// live frame would silently starve the application. See §帧去留清单 row 6,
/// which defines a duplicate as a sequence number already processed.
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
      newest_seen_ = seq;
      expected_ = static_cast<uint16_t>(seq + 1);
      return {SeqVerdict::kFirst, seq};
    }

    const uint16_t was_expecting = expected_;

    // Modular distance back from the newest sequence number already accepted.
    // Zero means this is that same frame again; anything within the trailing
    // window is older still. Both have been delivered once already.
    const uint16_t behind_newest = static_cast<uint16_t>(newest_seen_ - seq);
    if (behind_newest < kStaleWindow) {
      // Expectation untouched: the stream is still waiting for the frame
      // after the newest one actually seen.
      return {SeqVerdict::kDuplicate, was_expecting};
    }

    const bool in_order = (seq == expected_);
    newest_seen_ = seq;
    expected_ = static_cast<uint16_t>(seq + 1);
    return {in_order ? SeqVerdict::kInOrder : SeqVerdict::kGap, was_expecting};
  }

private:
  /// How far back a sequence number may be and still count as already seen.
  ///
  /// This window is the only thing standing between a frame and being
  /// silently dropped, so it is deliberately narrow. Duplicates on this link
  /// come from retransmission and reordering, which are bounded by a handful
  /// of frames; a sequence number hundreds behind is far more likely to be a
  /// counter reset or a stream restart, and dropping those would starve the
  /// application with no way to tell.
  ///
  /// Widening it is not free: the window is measured backwards modulo 2^16,
  /// so every value it claims is one a large forward jump can no longer be
  /// distinguished from. Half the space would make a jump of 40000 ahead
  /// indistinguishable from a stale frame -- and dropping a never-seen frame
  /// violates §帧去留清单 row 6, which defines a duplicate as a sequence
  /// number *already processed*. Erring narrow costs at worst a redundant
  /// delivery; erring wide loses data.
  static constexpr uint16_t kStaleWindow = 64;

  uint16_t expected_ = 0;
  uint16_t newest_seen_ = 0;
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
