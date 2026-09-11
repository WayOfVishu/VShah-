"""
Unit tests for leagueml/features/.

# TODO (see docs/TODO.md #FEAT-1, #FEAT-2, #FEAT-4)
#
# For test_extract_item_snapshot: don't hit the real Riot API in a unit
# test. Build a small hand-written fake timeline dict (a couple of frames,
# each with a made-up ITEM_PURCHASED event) as a pytest fixture, so the test
# is fast, deterministic, and doesn't need network/API-key access at all.
#
# The #FEAT-2 tests can use real-shaped input today: synthetic.to_participant_rows()
# produces exactly the columns build_feature_table() will.
"""

import pytest

from leagueml.features.item_timing import extract_item_snapshot


@pytest.fixture
def fake_timeline():
    # TODO: build a minimal fake timeline dict here -- a couple of frames,
    # each with an "events" list containing ITEM_PURCHASED (and maybe
    # ITEM_SOLD) events for a single participantId, spanning past the
    # snapshot minute you'll test against.
    raise NotImplementedError("TODO: see docs/TODO.md #FEAT-1")


@pytest.mark.skip(reason="TODO: implement the fake_timeline fixture and extract_item_snapshot first")
def test_extract_item_snapshot_returns_items_owned_before_cutoff(fake_timeline):
    result = extract_item_snapshot(fake_timeline, participant_id=1, snapshot_minute=10)
    # TODO: assert result matches exactly what your fake timeline implies was
    # owned at minute 10 (accounting for any ITEM_SOLD events you included).


@pytest.mark.skip(reason="TODO: implement extract_item_snapshot first")
def test_extract_item_snapshot_ignores_purchases_after_cutoff(fake_timeline):
    # TODO: assert an item purchased at, say, minute 12 does NOT show up in
    # a snapshot taken at minute 10.
    pass


@pytest.mark.skip(reason="build_vocabularies / encode_ids are not implemented yet -- see #FEAT-2")
def test_a_champion_unseen_in_training_encodes_as_unk():
    # TODO: #FEAT-2 design question 1. Build vocabularies from some synthetic
    # participant rows, then encode a row whose champion is not in them, and
    # assert it gets UNK_ID rather than raising a KeyError. This is the path a
    # new champion release takes in production, and it is the one nobody
    # tests until it breaks.
    pytest.fail("write me")


@pytest.mark.skip(reason="encode_ids is not implemented yet -- see #FEAT-2")
def test_encode_ids_pads_items_to_six_with_pad_id():
    # TODO: rows owning 0, 1 and 6 items all come back as (6,) arrays, padded
    # with PAD_ID -- and PAD_ID never collides with a real item's id.
    pytest.fail("write me")


@pytest.mark.skip(reason="extract_participant_frames is not implemented yet -- see #FEAT-4")
def test_frames_stop_where_the_game_stops():
    # TODO: #FEAT-4 design question 2. A fake timeline with 6 frames and
    # max_minute=15 yields 6 minutes of rows, not 15 -- no invented frames.
    pytest.fail("write me")
