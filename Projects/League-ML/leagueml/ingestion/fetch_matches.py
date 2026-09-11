"""
Top-level ingestion orchestrator: seed accounts -> match IDs -> raw match +
timeline JSON on disk -> structured rows in SQLite.

# TODO (Phase 1 -- see docs/TODO.md #ING-4)
#
# This is the module `py run.py ingest` actually calls. It's intentionally left
# to you because "wire the pieces together in the right order, handling
# partial failure" is most of what real ETL engineering is -- riot_client.py,
# rate_limiter.py, and checkpoint.py give you the building blocks.
#
# A rough shape to build toward (not a line-by-line spec):
#
#   1. Get a pool of seed puuids straight from league entries
#      (get_league_entries(), or get_entries_by_division() for tiers below
#      Challenger -- v3: no Summoner-V4 hop any more, see riot_client.py).
#      Note: an all-Challenger seed pool skews your dataset toward one skill
#      tier -- worth a paragraph in your README either way (#LML-2).
#   2. For each seed puuid, call get_match_ids_by_puuid() to collect
#      candidate match_ids. De-duplicate across seeds (the same match shows
#      up for every one of its 10 participants' puuids).
#   3. Filter candidates through checkpoint.get_pending_match_ids() so a
#      resumed run doesn't re-fetch matches it already has.
#   4. For each remaining match_id: mark_pending -> fetch match + timeline ->
#      save both raw JSONs to data/raw/ -> parse+insert matches/participants
#      rows via leagueml/storage/db.py -> mark_done (or mark_failed on error,
#      and keep going rather than aborting the whole run).
#   5. Stop once you've hit max_matches (default config.TARGET_MATCH_COUNT_MAX),
#      or you run out of candidates, or you decide to stop for the session
#      (this can -- and per Section 13 should -- run across multiple invocations).
#
# (v3) Three things the schema now needs from step 4 that the draft did not:
#   - matches.game_version (raw info.gameVersion) and matches.patch (its
#     major.minor). Compare patch against config.TARGET_PATCH -- and note that
#     is "16.18", not "26.18"; config.py explains the two numbering schemes.
#     Decide what a match from the wrong patch does: skip, or store and filter?
#   - participants.riot_participant_num, Riot's 1-10 number for each
#     participant (info.participants[].participantId). The timeline is keyed by
#     it, so #FEAT-1 and #FEAT-4 cannot join back to a participant without it.
#   - Remakes. Some games end in the first few minutes and say nothing about
#     who was better. Look for how a match detail marks them (duration, and
#     participant-level early-surrender flags) and decide whether they are
#     ingested at all.
#
# Also worth deciding deliberately: what counts as "raw" here? Saving the
# untouched API response JSON to data/raw/ (in addition to inserting parsed
# rows into SQLite) means you can re-run feature engineering later without
# re-hitting the API if you change your mind about what to extract. In v3
# this stops being optional: the timeline JSON is the only source of the
# per-minute frames (#FEAT-4), and they are materialised from disk later.
"""


def run(max_matches: int | None = None) -> None:
    """Entry point called by `py run.py ingest`."""
    raise NotImplementedError("fetch_matches.run() is not implemented yet -- see docs/TODO.md #ING-4")


if __name__ == "__main__":
    run()
