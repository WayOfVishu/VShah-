"""
Extract each participant's item loadout at a fixed snapshot minute.

# TODO (Phase 3 -- see docs/TODO.md #FEAT-1)
#
# Important fact that will save you a dead end: the Match-V5 *match detail*
# endpoint (get_match) only gives you FINAL item slots (end of game). To know
# what a participant had purchased at, say, the 10-minute mark, you need the
# separate *timeline* endpoint (get_match_timeline), which returns a list of
# per-minute "frames", each containing an "events" list. The events you want
# have type "ITEM_PURCHASED" (also watch for "ITEM_SOLD" / "ITEM_UNDO" if you
# want to be fully correct about what's still owned, vs. just what was ever
# bought).
#
# That fact is domain knowledge about Riot's API shape, not the solution --
# the actual parsing logic is yours to design:
#   - How do you go from a stream of purchase/sell/undo events up to minute
#     10 to a final set of "currently owned item IDs" at that timestamp?
#   - The item_snapshots table models 6 item slots + a trinket slot
#     (item_slot 0-6). Do you need to track *which slot* an item sits in, or
#     does "the set of items owned" suffice for your features? (Re-read
#     project-charter.md Section 3 scope -- item builds, not slot layout --
#     before over-building this. The networks read items as a set anyway.)
#   - What should happen for a participant who, at minute 10, hasn't
#     completed a "full" build yet? (They won't have -- that's expected. Don't
#     pad or infer missing items.)
#   - (v3) Components and consumables. A Doran's Blade, a Health Potion and
#     a half-built component all show up as ITEM_PURCHASED. Keep everything,
#     or filter to items that are still in the inventory and not consumed?
#     Whatever you decide here is what the recommender (#REC-1) will be able
#     to recommend, so decide it with that in mind.
#   - (v3) "At minute 10" must mean the same moment here and in frames.py
#     (#FEAT-4) -- otherwise the items and the gold in one row describe two
#     different points in the game.
"""


def extract_item_snapshot(match_timeline: dict, participant_id: int, snapshot_minute: int) -> list[int]:
    """Return the list of item_ids owned by `participant_id` at `snapshot_minute`.

    `participant_id` here is Riot's small per-match integer 1-10 (as used in
    timeline frame events, and stored as participants.riot_participant_num),
    not this project's participant_id string (f"{match_id}_{puuid}") used
    elsewhere -- keep that distinction straight when you call this from
    build_feature_table.py.
    """
    raise NotImplementedError("extract_item_snapshot() is not implemented yet -- see docs/TODO.md #FEAT-1")
