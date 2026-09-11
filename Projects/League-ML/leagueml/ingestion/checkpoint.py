"""
Ingestion checkpointing -- makes a multi-session pull resumable.

# TODO (Phase 1 -- see docs/TODO.md #ING-3)
#
# project-charter.md Section 13 flags this explicitly: your personal key's rate
# limit means pulling even 2,000-5,000 matches happens over *multiple
# sessions*, not one run. Functional Requirement (Section 8):
#   "Ingestion must checkpoint progress (resumable if interrupted)"
#
# The `ingestion_checkpoints` table already exists in db/schema.sql with
# columns (match_id, status, updated_at) where status is one of
# 'pending' / 'done' / 'failed'. Use leagueml/storage/db.py's insert_row() /
# fetch_all() helpers -- don't hand-write new SQL connection logic here.
#
# Questions to work through:
#   - When exactly do you mark a match_id 'pending' vs 'done'? (Before or
#     after you've actually written its rows to matches/participants and its
#     raw JSON to data/raw/? What happens if the process dies in between?)
#   - On startup, how do you find the set of match_ids that still need work --
#     is "not in the checkpoint table at all" different from "marked
#     'failed'"? Should a resumed run retry failures automatically, or only
#     fresh ones?
#   - A 'failed' match: retry forever, retry N times, or skip permanently?
#     Where would you record that decision so a re-run doesn't repeat it?
"""


def mark_pending(match_id: str) -> None:
    """Record that we're about to attempt this match."""
    raise NotImplementedError("mark_pending() is not implemented yet -- see docs/TODO.md #ING-3")


def mark_done(match_id: str) -> None:
    """Record that this match's data was successfully stored."""
    raise NotImplementedError("see docs/TODO.md #ING-3")


def mark_failed(match_id: str) -> None:
    """Record that this match failed and won't be retried automatically."""
    raise NotImplementedError("see docs/TODO.md #ING-3")


def get_pending_match_ids(candidate_ids: list[str]) -> list[str]:
    """Given a list of match_ids you'd like to fetch, return the subset that
    still need work (i.e. filter out ones already marked 'done')."""
    raise NotImplementedError("see docs/TODO.md #ING-3")
