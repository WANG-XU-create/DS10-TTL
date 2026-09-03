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
#include "ds10_protocol/seq_tracker.hpp"

// The first sequence number seen on a stream establishes the baseline; there
// is nothing to compare it against, so it is never a gap or a duplicate.
TEST(SeqTrackerTest, FirstFrameInitialises)
{
  ds10_protocol::SeqTracker tracker;

  EXPECT_EQ(tracker.classify(100).verdict, ds10_protocol::SeqVerdict::kFirst);
}

TEST(SeqTrackerTest, ConsecutiveFramesAreInOrder)
{
  ds10_protocol::SeqTracker tracker;

  tracker.classify(10);
  EXPECT_EQ(tracker.classify(11).verdict, ds10_protocol::SeqVerdict::kInOrder);
  EXPECT_EQ(tracker.classify(12).verdict, ds10_protocol::SeqVerdict::kInOrder);
  EXPECT_EQ(tracker.classify(13).verdict, ds10_protocol::SeqVerdict::kInOrder);
}

TEST(SeqTrackerTest, SkippedSequenceIsAGap)
{
  ds10_protocol::SeqTracker tracker;

  tracker.classify(1);
  const auto gap = tracker.classify(3);
  EXPECT_EQ(gap.verdict, ds10_protocol::SeqVerdict::kGap);
  // The log needs to name what was missed, not just what arrived.
  EXPECT_EQ(gap.expected, 2);
  // After a gap the tracker resynchronises on what actually arrived, so the
  // next consecutive frame is in order rather than a second gap.
  EXPECT_EQ(tracker.classify(4).verdict, ds10_protocol::SeqVerdict::kInOrder);
}

TEST(SeqTrackerTest, RepeatedSequenceIsADuplicate)
{
  ds10_protocol::SeqTracker tracker;

  tracker.classify(5);
  EXPECT_EQ(tracker.classify(5).verdict, ds10_protocol::SeqVerdict::kDuplicate);
}

// A duplicate must not move the baseline: the stream is still expecting the
// frame that follows the one already seen.
TEST(SeqTrackerTest, DuplicateDoesNotAdvanceExpectation)
{
  ds10_protocol::SeqTracker tracker;

  tracker.classify(5);
  tracker.classify(5);
  EXPECT_EQ(tracker.classify(6).verdict, ds10_protocol::SeqVerdict::kInOrder);
}

TEST(SeqTrackerTest, WrapAroundIsInOrderNotAGap)
{
  ds10_protocol::SeqTracker tracker;

  tracker.classify(65534);
  EXPECT_EQ(tracker.classify(65535).verdict, ds10_protocol::SeqVerdict::kInOrder);
  EXPECT_EQ(tracker.classify(0).verdict, ds10_protocol::SeqVerdict::kInOrder);
  EXPECT_EQ(tracker.classify(1).verdict, ds10_protocol::SeqVerdict::kInOrder);
}

// A gap that straddles the wrap point is still a gap.
TEST(SeqTrackerTest, GapAcrossWrapPoint)
{
  ds10_protocol::SeqTracker tracker;

  tracker.classify(65534);
  EXPECT_EQ(tracker.classify(2).verdict, ds10_protocol::SeqVerdict::kGap);
  EXPECT_EQ(tracker.classify(3).verdict, ds10_protocol::SeqVerdict::kInOrder);
}

// Half the uint16 space is the boundary between "a large forward gap" and
// "an old frame arriving late". Anything at or beyond it reads as backwards.
TEST(SeqTrackerTest, LargeForwardJumpIsAGap)
{
  ds10_protocol::SeqTracker tracker;

  tracker.classify(0);
  // 32767 ahead: still within the forward half, so a gap.
  EXPECT_EQ(tracker.classify(32767).verdict, ds10_protocol::SeqVerdict::kGap);
}

TEST(SeqTrackerTest, FarBackwardSequenceIsADuplicate)
{
  ds10_protocol::SeqTracker tracker;

  tracker.classify(1000);
  // 900 is well behind the expectation and nowhere near a wrap: a late or
  // replayed frame, which we treat as a duplicate and drop.
  EXPECT_EQ(tracker.classify(900).verdict, ds10_protocol::SeqVerdict::kDuplicate);
}

TEST(SeqTrackerTest, TrackersAreIndependentPerStream)
{
  ds10_protocol::SeqTrackerTable table;

  // Two stations on the same function code must not share an expectation.
  EXPECT_EQ(table.classify(2, 0x10, 1).verdict, ds10_protocol::SeqVerdict::kFirst);
  EXPECT_EQ(table.classify(3, 0x10, 1).verdict, ds10_protocol::SeqVerdict::kFirst);

  EXPECT_EQ(table.classify(2, 0x10, 3).verdict, ds10_protocol::SeqVerdict::kGap);
  EXPECT_EQ(table.classify(3, 0x10, 2).verdict, ds10_protocol::SeqVerdict::kInOrder);
}

TEST(SeqTrackerTest, SameStationDifferentFunctionCodesAreIndependent)
{
  ds10_protocol::SeqTrackerTable table;

  EXPECT_EQ(table.classify(2, 0x10, 1).verdict, ds10_protocol::SeqVerdict::kFirst);
  EXPECT_EQ(table.classify(2, 0x11, 1).verdict, ds10_protocol::SeqVerdict::kFirst);

  EXPECT_EQ(table.classify(2, 0x10, 2).verdict, ds10_protocol::SeqVerdict::kInOrder);
  EXPECT_EQ(table.classify(2, 0x11, 2).verdict, ds10_protocol::SeqVerdict::kInOrder);
}
