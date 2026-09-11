"""
Offline synthetic matches with a planted, known answer.

**Built for you.** Same role as Stocks' synthetic providers: every modelling
module runs on a fresh clone with no Riot key, no network and no ingested
data. That matters more here than it did in Stocks, because real data arrives
only after #ING-1..4 and #FEAT-1..4 are done -- months in, at 3-4 hours a
week. The deep learning does not have to wait for that. Develop against this,
then point the same code at real data.

It is also the only dataset in this project where you know the right answer,
which makes it a measuring instrument rather than just a stand-in:

- `signal=0` is the canary. Outcomes are coin flips, independent of every
  feature. A model that scores meaningfully above AUC 0.5 on it has found a
  leak, not a pattern -- `py run.py demo` runs this first.
- `signal>0` makes outcomes depend on three planted effects, chosen so each
  needs a little more model to find:
    1. champion strength  -- additive. Logistic regression on a side encoding
                             recovers it exactly; nothing deep required.
    2. same-team synergy  -- specific champion *pairs* on one team. An
                             interaction, invisible to a linear model over
                             one-hot columns. The honest case for a network.
    3. champion-item fit  -- each champion has two items that suit it. What
                             the recommender (#REC-1) has to rediscover.
  Plus a gold-difference trajectory that drifts toward the side the draft
  favours, for the sequence model (#DL-7).

One more thing is planted on purpose: **how many items a player owns at the
snapshot depends on whether their team is ahead in gold.** Real players who
are winning can afford more, so "owns lots of items at minute 10" predicts a
win without causing one. That is the confounding trap #REC-1 has to handle,
reproduced where you can see it.

Synthetic scores measure plumbing and model capacity, never skill at League.
What transfers to real matches is whether your code can find a pattern that is
known to be there -- and whether it refuses to find one that is not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from leagueml.config import FRAME_MINUTES, SNAPSHOT_MINUTE
from leagueml.features.build_feature_table import PARTICIPANT_COLUMNS

__all__ = [
    "ROLES",
    "ITEM_SLOTS",
    "SyntheticSpec",
    "SyntheticTruth",
    "generate_matches",
    "to_participant_rows",
    "side_encoding",
]

ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")

# Six inventory slots. The trinket is left out: everyone has one, so it says
# nothing about who wins.
ITEM_SLOTS = 6

# Synthetic item ids start above 1000 so they look like Riot's (1055, 3031,
# ...) rather than 1..n. Real item ids are sparse, and an encoder that quietly
# assumes a dense 1..n range should break here, not on real data.
ITEM_ID_OFFSET = 1000

# Where the synthetic calendar starts (epoch millis, late August 2026). Matches
# are spaced 90 seconds apart, so id order is chronological order.
_START_TS = 1_788_000_000_000


@dataclass(frozen=True)
class SyntheticSpec:
    """Knobs for the generator. The defaults make a small, learnable world."""

    n_champions: int = 30
    n_items: int = 24
    n_minutes: int = FRAME_MINUTES
    signal: float = 1.0        # 0 -> the canary: outcomes ignore every feature
    strength: float = 0.5      # spread of additive champion strength. 0 leaves only the
                               # interactions -- a world the linear floor is nearly blind to (#EVAL-3)
    synergy: float = 1.0       # log-odds bonus per planted pair on one team
    n_synergy_pairs: int = 12
    item_fit: float = 0.4      # log-odds bonus per owned item that suits its champion
    seed: int = 0


@dataclass(frozen=True)
class SyntheticTruth:
    """The planted answer. Real data never hands you this; keep it for checks
    such as "did the embedding put synergy pairs close together?" (#DL-8)."""

    strength: np.ndarray                         # (n_champions + 1,), index 0 unused
    synergy_pairs: tuple[tuple[int, int], ...]
    fit_items: np.ndarray                        # (n_champions + 1, 2) item ids


def _plant(spec: SyntheticSpec, rng: np.random.Generator) -> SyntheticTruth:
    champions = np.arange(1, spec.n_champions + 1)
    strength = np.concatenate([[0.0], rng.normal(0.0, 1.0, spec.n_champions) * spec.strength])

    pairs: set[tuple[int, int]] = set()
    while len(pairs) < spec.n_synergy_pairs:
        a, b = sorted(rng.choice(champions, size=2, replace=False).tolist())
        pairs.add((a, b))

    item_ids = np.arange(ITEM_ID_OFFSET + 1, ITEM_ID_OFFSET + spec.n_items + 1)
    fit = np.zeros((spec.n_champions + 1, 2), dtype=np.int64)
    for c in champions:
        fit[c] = rng.choice(item_ids, size=2, replace=False)

    return SyntheticTruth(strength, tuple(sorted(pairs)), fit)


def _draft_edge(team: np.ndarray, truth: SyntheticTruth, spec: SyntheticSpec) -> float:
    """Additive strength plus the synergy bonus for every planted pair on the team."""
    members = set(team.tolist())
    pairs_present = sum(1 for a, b in truth.synergy_pairs if a in members and b in members)
    return float(truth.strength[team].sum() + spec.synergy * pairs_present)


def generate_matches(
    n_matches: int, spec: SyntheticSpec | None = None
) -> tuple[pd.DataFrame, SyntheticTruth]:
    """One row per match: both teams' champions (ids 1..n_champions, ordered by
    ROLES), their items at the snapshot, the gold-difference curve, the winner.

    Returns the matches and the planted truth. Deterministic for a given spec.
    """
    spec = spec or SyntheticSpec()
    if spec.n_champions < 10:
        raise ValueError("need at least 10 champions to field two teams of five")
    if spec.n_items < 2:
        raise ValueError("need at least 2 items so every champion can have two that suit it")

    rng = np.random.default_rng(spec.seed)
    truth = _plant(spec, rng)
    champions = np.arange(1, spec.n_champions + 1)
    item_ids = np.arange(ITEM_ID_OFFSET + 1, ITEM_ID_OFFSET + spec.n_items + 1)
    snapshot = min(SNAPSHOT_MINUTE, spec.n_minutes) - 1  # index into the gold curve

    records = []
    for m in range(n_matches):
        picks = rng.choice(champions, size=10, replace=False)
        blue, red = picks[:5], picks[5:]
        edge = _draft_edge(blue, truth, spec) - _draft_edge(red, truth, spec)

        # Blue minus red team gold, minute by minute: a random walk that
        # drifts toward whichever side the draft favours. Real games snowball
        # the same way, which is why gold at minute 10 predicts so well.
        drift = spec.signal * 300.0 * np.tanh(edge)
        gold_diff = np.cumsum(rng.normal(drift, 500.0, spec.n_minutes))

        # Items owned at the snapshot. The count follows the gold lead -- the
        # planted confounder (module docstring). Half of each pick is one of
        # the champion's two suited items, half anything at all.
        lead = gold_diff[snapshot]
        items = np.zeros((10, ITEM_SLOTS), dtype=np.int64)
        fit_owned = [0, 0]
        for p, champ in enumerate(picks):
            side_lead = lead if p < 5 else -lead
            n_owned = int(np.clip(rng.poisson(max(0.5, 2.0 + side_lead / 1500.0)), 1, ITEM_SLOTS))
            owned: set[int] = set()
            while len(owned) < n_owned:
                pool = truth.fit_items[champ] if rng.random() < 0.5 else item_ids
                owned.add(int(rng.choice(pool)))
            items[p, :n_owned] = sorted(owned)
            fit_owned[p // 5] += len(owned & set(truth.fit_items[champ].tolist()))

        logit = spec.signal * (edge + spec.item_fit * (fit_owned[0] - fit_owned[1]))
        blue_win = int(rng.random() < 1.0 / (1.0 + np.exp(-logit)))

        records.append({
            "meta_match_id": f"SYN_{m:06d}",
            "meta_game_start_ts": _START_TS + m * 90_000,
            "blue_champions": blue.astype(np.int64),
            "red_champions": red.astype(np.int64),
            "blue_items": items[:5],
            "red_items": items[5:],
            "gold_diff": gold_diff.astype(np.float32),
            "blue_win": blue_win,
        })

    return pd.DataFrame.from_records(records), truth


def _champion_name(champion_id: int) -> str:
    return f"C{int(champion_id):02d}"


def to_participant_rows(matches: pd.DataFrame) -> pd.DataFrame:
    """Ten rows per match, each from one participant's point of view.

    Exactly build_feature_table.PARTICIPANT_COLUMNS, so #FEAT-2's encoder and
    the participant-level networks can be built here before #FEAT-3 exists.
    Champions become names ("C07") because real champions are names; items
    stay integer ids because real items are.
    """
    rows = []
    for m in matches.itertuples(index=False):
        snapshot = min(SNAPSHOT_MINUTE, len(m.gold_diff)) - 1
        sides = {
            100: (m.blue_champions, m.blue_items, m.red_champions, m.blue_win, 1.0),
            200: (m.red_champions, m.red_items, m.blue_champions, 1 - m.blue_win, -1.0),
        }
        for team_id, (own, own_items, other, won, sign) in sides.items():
            for slot, role in enumerate(ROLES):
                rows.append({
                    "meta_match_id": m.meta_match_id,
                    "meta_participant_id": f"{m.meta_match_id}_{team_id}_{role}",
                    "meta_game_start_ts": m.meta_game_start_ts,
                    "champion": _champion_name(own[slot]),
                    "role": role,
                    "enemy_laner": _champion_name(other[slot]),
                    "allies": [_champion_name(c) for i, c in enumerate(own) if i != slot],
                    "enemies": [_champion_name(c) for c in other],
                    "items": [int(i) for i in own_items[slot] if i],
                    "gold_diff_at_snapshot": sign * float(m.gold_diff[snapshot]),
                    "win": int(won),
                })
    return pd.DataFrame.from_records(rows, columns=list(PARTICIPANT_COLUMNS))


def side_encoding(matches: pd.DataFrame, n_champions: int) -> np.ndarray:
    """Demo-only features: one column per champion, +1 on blue, -1 on red.

    The classic team-composition encoding. With logistic regression on top it
    is a Bradley-Terry model -- each team's strength is the sum of its
    champions', and the log-odds of blue winning is the difference.

    It deliberately ducks everything #FEAT-2 has to decide -- roles, items,
    gold, champions the vocabulary has never seen -- and works only because
    synthetic champion ids are already 1..n. It exists so `py run.py demo`
    has something to run. It is not the encoder.
    """
    X = np.zeros((len(matches), n_champions + 1), dtype=np.float32)
    rows = np.arange(len(matches))[:, None]
    X[rows, np.stack(matches["blue_champions"].to_list())] = 1.0
    X[rows, np.stack(matches["red_champions"].to_list())] = -1.0
    return X[:, 1:]  # column 0 would be the unused id 0
