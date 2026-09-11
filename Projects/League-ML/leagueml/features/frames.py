"""
Per-minute participant frames from the Match-V5 timeline.

# TODO (Phase 3 -- see docs/TODO.md #FEAT-4) -- new in v3
#
# The timeline you already save to data/raw/ carries, besides the events
# #FEAT-1 reads, a snapshot of every participant roughly once a minute: a
# list of frames, each with a timestamp and a mapping from participant number
# to that participant's state -- gold, experience, level, minions and jungle
# camps killed, and more. Open one real timeline JSON and read the actual key
# names before writing anything; don't trust this docstring over the data.
#
# Two consumers, which is why this is its own module:
#   - gold_diff_at_snapshot in the participant table (#FEAT-3) -- the
#     variable the recommender has to hold fixed, because players who are
#     ahead buy more items (#REC-1's confounding trap).
#   - the sequence model (#DL-7) -- a (minutes x features) matrix per match.
#
# Design questions:
#   1. Frames are about sixty seconds apart but not exactly, and the first one
#      is at t=0. Which frame is "minute 10" -- timestamp // 60000, or the
#      nearest? Whatever you pick, #FEAT-1 must use the same rule, or one row's
#      items and gold describe two different moments.
#   2. Games shorter than max_minute (remakes, very early surrenders). Return
#      the frames that exist. Padding and masking are the sequence model's
#      decision (#DL-7), and inventing frames here would hide that a game ended.
#   3. The participant keys in a frame are the 1-10 numbers, as strings.
#      participants.riot_participant_num is the same number -- that is the join.
#   4. Totals or differences? Store raw per-participant totals here (the
#      participant_frames table does) and compute team differences later. A
#      difference computed here cannot be un-computed if you change your mind.
"""

from leagueml.config import FRAME_MINUTES


def extract_participant_frames(match_timeline: dict, max_minute: int = FRAME_MINUTES) -> list[dict]:
    """Return one dict per (participant, minute) up to `max_minute`, with keys
    matching the participant_frames table minus participant_id:

        {"riot_participant_num": 3, "minute": 10, "total_gold": 3850,
         "xp": 4120, "level": 8, "minions_killed": 71, "jungle_minions_killed": 0}

    The caller (#FEAT-3's materialise step) maps riot_participant_num to this
    project's participant_id string before inserting.
    """
    raise NotImplementedError("extract_participant_frames() is not implemented yet -- see docs/TODO.md #FEAT-4")
