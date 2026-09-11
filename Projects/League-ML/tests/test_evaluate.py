"""The evaluation harness is what makes every other number here believable, so
it is tested rather than trusted."""

import numpy as np

from leagueml.evaluate import (
    chronological_split,
    classification_report,
    compare,
    match_grouped_split,
    naive_row_split,
)


def _participant_ids(n_matches: int = 60) -> np.ndarray:
    return np.repeat([f"M{i:03d}" for i in range(n_matches)], 10)


def test_grouped_split_never_puts_one_match_on_both_sides():
    ids = _participant_ids()
    s = match_grouped_split(ids, seed=0)
    train, val, test = set(ids[s.train]), set(ids[s.val]), set(ids[s.test])
    assert not train & val and not train & test and not val & test
    assert len(s.train) + len(s.val) + len(s.test) == len(ids)


def test_naive_row_split_does_split_matches_which_is_the_point():
    ids = _participant_ids()
    s = naive_row_split(len(ids), seed=0)
    assert set(ids[s.train]) & set(ids[s.test]), "if this ever passes empty, #EVAL-2 measures nothing"


def test_chronological_split_tests_on_the_latest_matches():
    ids = _participant_ids()
    ts = np.repeat(np.arange(60) * 1000, 10)
    s = chronological_split(ids, ts)
    assert ts[s.train].max() < ts[s.val].min() <= ts[s.val].max() < ts[s.test].min()


def test_report_on_perfect_predictions():
    y = np.array([0, 1, 0, 1, 1, 0])
    r = classification_report(y, y.astype(float))
    assert r["roc_auc"] == 1.0 and r["accuracy"] == 1.0 and r["brier"] < 1e-6


def test_canary_flags_a_model_that_finds_what_is_not_there():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 400)
    result = compare({"majority": np.full(400, 0.5), "cheater": y * 0.9 + 0.05},
                     y, split="test", canary=True)
    assert any("cheater" in w and "leak" in w for w in result.warnings)
