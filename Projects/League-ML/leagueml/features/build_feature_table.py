"""
Turn the normalised SQLite tables into one flat, participant-centric table.

# TODO (Phase 3 -- see docs/TODO.md #FEAT-3)
#
# This is the piece that turns "data sitting in normalized tables" into
# "one row per participant, ready for encode.py". Your SQL is strong -- this
# is mostly that skill applied through pandas.read_sql_query() instead of a
# bare cursor.
#
# (v3) Two steps now, not one:
#
#   1. Materialise. item_snapshots and participant_frames are empty after
#      ingestion -- #ING-4 stores raw timeline JSON and the match/participant
#      rows, nothing more. Walk the timelines in data/raw/, run
#      extract_item_snapshot() (#FEAT-1) and extract_participant_frames()
#      (#FEAT-4) over each, map Riot's 1-10 numbers to participant_id via
#      participants.riot_participant_num, and insert. Idempotent, please:
#      running it twice must not double anything (the tables' primary keys
#      plus insert_rows' INSERT OR REPLACE get you most of the way).
#
#   2. Join, into exactly the columns in PARTICIPANT_COLUMNS below:
#        participants
#          JOIN matches                      (patch filter, game_start_ts)
#          self-JOIN participants            (enemy_laner: same match, same
#                                             role, other team_id)
#          JOIN participants again           (allies / enemies as lists --
#                                             GROUP_CONCAT in SQL, or groupby
#                                             in pandas; your call)
#          LEFT JOIN item_snapshots          (at the snapshot minute -> items)
#          JOIN participant_frames           (team gold at the snapshot minute,
#                                             summed per team -> gold_diff)
#
# (v3) The draft's table had no enemy column at all -- only champion, role,
# items, win -- while its predict CLI took --enemy. A model cannot condition on
# a feature it was never shown. enemy_laner, allies and enemies fix that, and
# they are what the embedding and attention models (#DL-2, #DL-5) are for.
#
# Think about:
#   - Should the join happen in SQL (one query, let SQLite do the work) or by
#     pulling tables separately and joining in pandas? Either is defensible --
#     pick one and know why.
#   - What do you do with a participant who has zero item_snapshot rows at
#     the target minute (e.g. very short/remake game)? Drop the row, or is
#     that itself informative? Where do you decide and document that?
#   - A missing role. Riot's team position can come back empty for some games.
#     enemy_laner is undefined for such a row -- drop it, or give "UNKNOWN" a
#     place in the vocabulary (#FEAT-2)?
#   - Rows are participants, so every match contributes ten of them, and
#     they are not independent: teammates share a label and opponents have the
#     opposite one. That is not a problem for this function, but it is why
#     meta_match_id is here and why evaluate.py splits on it. #EVAL-2 measures
#     what ignoring it would cost.
"""

import pandas as pd

from leagueml.config import SNAPSHOT_MINUTE
from leagueml.storage.db import get_connection

# The contract between features and models: one row per participant, from that
# participant's point of view. synthetic.to_participant_rows() produces exactly
# these columns, which is what lets encode.py (#FEAT-2) and every network be
# built and tested before this function works. Columns prefixed meta_ are
# bookkeeping and must never reach a model -- same rule as Stocks' META_PREFIX.
PARTICIPANT_COLUMNS = {
    "meta_match_id": "the match this row belongs to -- evaluate.py splits on it",
    "meta_participant_id": "f'{match_id}_{puuid}' (project-charter.md Section 12)",
    "meta_game_start_ts": "epoch millis -- for the chronological split",
    "champion": "the focal participant's champion, by name",
    "role": "TOP / JUNGLE / MIDDLE / BOTTOM / UTILITY",
    "enemy_laner": "the other team's champion in the same role",
    "allies": "list of the four teammates' champion names",
    "enemies": "list of the five opponents' champion names",
    "items": "list of item ids owned at the snapshot minute, 0-6 long, unpadded",
    "gold_diff_at_snapshot": "focal team's total gold minus the other team's, at the snapshot minute",
    "win": "1 if the focal participant's team won",
}


def build_feature_table(snapshot_minute: int = SNAPSHOT_MINUTE) -> pd.DataFrame:
    """Return the flat, joined (but not yet numerically encoded) participant
    table -- one row per participant, columns exactly PARTICIPANT_COLUMNS."""
    raise NotImplementedError("build_feature_table() is not implemented yet -- see docs/TODO.md #FEAT-3")
