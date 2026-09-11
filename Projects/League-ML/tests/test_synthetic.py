"""The synthetic generator is the measuring instrument for every model here, so
it gets real tests: if it quietly leaked or quietly lost its signal, every
comparison built on it would be wrong in a way nothing downstream could see."""

import numpy as np

from leagueml.evaluate import classification_report, match_grouped_split
from leagueml.features.build_feature_table import PARTICIPANT_COLUMNS
from leagueml.models.baselines import train_logistic_regression
from leagueml.synthetic import SyntheticSpec, generate_matches, side_encoding, to_participant_rows


def test_teams_are_five_distinct_champions_and_share_none():
    matches, _ = generate_matches(200, SyntheticSpec(seed=1))
    for blue, red in zip(matches["blue_champions"], matches["red_champions"]):
        assert len(set(blue)) == 5 and len(set(red)) == 5
        assert not set(blue) & set(red)


def test_same_seed_same_matches():
    a, _ = generate_matches(50, SyntheticSpec(seed=7))
    b, _ = generate_matches(50, SyntheticSpec(seed=7))
    assert a["blue_win"].tolist() == b["blue_win"].tolist()
    assert np.array_equal(np.stack(a["gold_diff"].to_list()), np.stack(b["gold_diff"].to_list()))


def _floor_auc(signal: float) -> float:
    matches, _ = generate_matches(3000, SyntheticSpec(signal=signal, seed=0))
    x = side_encoding(matches, 30)
    y = matches["blue_win"].to_numpy()
    s = match_grouped_split(matches["meta_match_id"].to_numpy(), seed=0)
    lr = train_logistic_regression(x[s.train], y[s.train])
    return classification_report(y[s.test], lr.predict_proba(x[s.test])[:, 1])["roc_auc"]


def test_the_canary_has_nothing_to_find():
    # 450 test matches -> AUC standard error ~0.027 under the null; 0.08 is ~3 SE.
    assert abs(_floor_auc(signal=0.0) - 0.5) < 0.08


def test_planted_signal_is_findable():
    assert _floor_auc(signal=1.0) > 0.6


def test_participant_rows_honour_the_real_table_contract():
    matches, _ = generate_matches(20, SyntheticSpec(seed=2))
    rows = to_participant_rows(matches)
    assert list(rows.columns) == list(PARTICIPANT_COLUMNS)
    assert len(rows) == 10 * len(matches)
    for _, match in rows.groupby("meta_match_id"):
        # Five winners and five losers: the dependence #EVAL-2 is about.
        assert sorted(match["win"].tolist()) == [0] * 5 + [1] * 5
        assert all(len(a) == 4 for a in match["allies"])
        assert all(len(e) == 5 for e in match["enemies"])
        assert all(0 < len(i) <= 6 for i in match["items"])
