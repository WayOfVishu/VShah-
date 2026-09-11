"""
Honest evaluation: splits that respect matches, metrics that respect
probabilities. **Built for you**, same as Stocks' evaluate.py and for the same
reason -- left alone, a model evaluation lies to you, and the harness that
stops it is infrastructure rather than the lesson.

**Split by match, never by row.** Participant rows are not independent. A
match contributes ten of them, the five teammates share one label, and the
five opponents have exactly the opposite one. Split those rows at random and
the near-twin of almost every test row sits in training: the same ten
champions, from a different seat, with a label you can read straight off it.
The model gets credit for looking up the answer. This is Stocks' overlapping-
labels problem in a different costume -- there, neighbouring weeks shared a
label window; here, neighbouring rows share a match -- and the fix has the same
shape: move whole groups, never pieces of one. `match_grouped_split` does it.
`naive_row_split` exists only so #EVAL-2 can measure what skipping it costs.

**Three splits, not two.** train fits the weights; val decides when to stop
and which settings win (#DL-3, #DL-4); test is looked at once per experiment,
for the number you report. Tune against test and the reported number is
optimistic in a way you cannot defend -- the draft's Section 9 rule.

**Chronological, when it matters.** Within one patch, "train on earlier
matches, test on later ones" costs little and is the honest simulation of
using the model tomorrow. Across a patch boundary it stops being optional.

**The metrics.** `classification_report` leads with ROC-AUC but prints four
numbers, because each one answers a different question:

    roc_auc     ranking: does a higher predicted probability mean a win more
                often? 0.5 is a coin flip. Blind to calibration.
    log_loss    the quantity the networks are trained to minimise. ln(2) =
                0.693 is what a 50/50 guess scores; lower is better.
    brier       mean squared error of the probability. 0.25 for a 50/50 guess.
    accuracy    at a 0.5 threshold. Reported because people ask for it; the
                least informative of the four.

The recommender (#REC-1) ranks items by *differences* in predicted
probability, so calibration matters here more than it would for a plain
classifier -- see #DL-6.

**The canary.** On data where the labels are independent of every feature
(`SyntheticSpec(signal=0)`), any model scoring far from AUC 0.5 has found a
leak. How far is "far" depends on the test size, so the tolerance is computed
from it: three standard errors of AUC under the null hypothesis (the Mann-
Whitney variance, (n0 + n1 + 1) / (12 n0 n1)).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

from leagueml.config import SEED

__all__ = [
    "Splits",
    "match_grouped_split",
    "chronological_split",
    "naive_row_split",
    "classification_report",
    "auc_null_se",
    "EvaluationResult",
    "compare",
]

FLOOR = "logistic_regression"
MAJORITY = "majority"


@dataclass(frozen=True)
class Splits:
    """Row indices for train / val / test."""

    train: np.ndarray
    val: np.ndarray
    test: np.ndarray
    kind: str

    def n_matches(self, match_ids) -> dict[str, int]:
        ids = np.asarray(match_ids)
        return {name: len(np.unique(ids[idx])) for name, idx in
                (("train", self.train), ("val", self.val), ("test", self.test))}


def _allocate(ordered_matches: np.ndarray, match_ids: np.ndarray, val_size: float,
              test_size: float, kind: str) -> Splits:
    """Cut an ordered list of matches into train | val | test and map back to rows."""
    n = len(ordered_matches)
    n_test = max(1, int(round(n * test_size)))
    n_val = max(1, int(round(n * val_size)))
    if n - n_test - n_val < 1:
        raise ValueError(f"{n} matches cannot fill train/val/test at {val_size}/{test_size}")
    test_m = ordered_matches[n - n_test:]
    val_m = ordered_matches[n - n_test - n_val:n - n_test]
    rows = np.arange(len(match_ids))
    in_test = np.isin(match_ids, test_m)
    in_val = np.isin(match_ids, val_m)
    return Splits(rows[~in_test & ~in_val], rows[in_val], rows[in_test], kind)


def match_grouped_split(match_ids, *, val_size: float = 0.15, test_size: float = 0.15,
                        seed: int = SEED) -> Splits:
    """Random split over *matches*: every row of a match lands on the same side."""
    ids = np.asarray(match_ids)
    matches = np.unique(ids)
    np.random.default_rng(seed).shuffle(matches)
    return _allocate(matches, ids, val_size, test_size, "match-grouped")


def chronological_split(match_ids, start_ts, *, val_size: float = 0.15,
                        test_size: float = 0.15) -> Splits:
    """Train on the earliest matches, validate on the next, test on the latest.

    Grouped by construction: the cut is between matches, and every row of a
    match carries that match's start time.
    """
    ids = np.asarray(match_ids)
    first_seen = pd.Series(np.asarray(start_ts)).groupby(ids).min().sort_values(kind="stable")
    return _allocate(first_seen.index.to_numpy(), ids, val_size, test_size, "chronological")


def naive_row_split(n_rows: int, *, val_size: float = 0.15, test_size: float = 0.15,
                    seed: int = SEED) -> Splits:
    """**Wrong on purpose** for participant rows -- it splits matches in pieces.

    Exists for #EVAL-2 only: run the same model under this and under
    match_grouped_split, and the difference in test score is the leak, measured.
    Harmless on match-level rows (one row per match), which is also worth
    noticing.
    """
    # Each row treated as its own "match" -- which is precisely the mistake.
    rows = np.arange(n_rows)
    shuffled = np.random.default_rng(seed).permutation(n_rows)
    return _allocate(shuffled, rows, val_size, test_size, "naive-row")


def auc_null_se(y_true) -> float:
    """Standard error of ROC-AUC when predictions carry no information."""
    y = np.asarray(y_true)
    n1, n0 = int((y == 1).sum()), int((y == 0).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float(np.sqrt((n0 + n1 + 1) / (12.0 * n0 * n1)))


def classification_report(y_true, p_win) -> dict[str, float]:
    """ROC-AUC, log-loss, Brier and accuracy for one model's predicted probabilities."""
    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(p_win, dtype=float), 1e-7, 1 - 1e-7)
    both_classes = 0 < y.sum() < len(y)
    return {
        "roc_auc": float(roc_auc_score(y, p)) if both_classes else float("nan"),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(np.mean((p - y) ** 2)),
        "accuracy": float(np.mean((p >= 0.5) == (y == 1))),
        "n": float(len(y)),
    }


@dataclass
class EvaluationResult:
    """Scores for several models on one test set, plus what to make of them."""

    scores: dict[str, dict[str, float]]
    split: str
    n_matches: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    leak_detected: bool = False

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.scores).T[["roc_auc", "log_loss", "brier", "accuracy", "n"]]

    def summary(self) -> str:
        counts = ", ".join(f"{k} {v}" for k, v in self.n_matches.items())
        lines = [f"{self.split} split -- matches: {counts}", ""]
        frame = self.to_frame()
        frame["n"] = frame["n"].astype(int)
        lines.append(frame.round(4).to_string())
        lines.append("")
        lines += [f"  {note}" for note in self.notes]
        lines += [f"  !! {w}" for w in self.warnings]
        return "\n".join(lines)


def compare(predictions: dict[str, np.ndarray], y_test, *, split: str,
            n_matches: dict[str, int] | None = None, canary: bool = False,
            synthetic: bool = False) -> EvaluationResult:
    """Score every model on the same test labels and write down the comparisons
    that stop a table from being over-read -- printed with the numbers rather
    than left to memory, same as Stocks' EvaluationResult.summary()."""
    y = np.asarray(y_test)
    scores = {name: classification_report(y, p) for name, p in predictions.items()}
    result = EvaluationResult(scores=scores, split=split, n_matches=n_matches or {})
    se = auc_null_se(y)

    if canary:
        tolerance = 3 * se
        for name, s in scores.items():
            if name == MAJORITY:
                continue
            gap = abs(s["roc_auc"] - 0.5)
            if gap > tolerance:
                result.leak_detected = True
                result.warnings.append(
                    f"{name} scored AUC {s['roc_auc']:.3f} on labels independent of every "
                    f"feature (tolerance 0.5 +/- {tolerance:.3f}). That is a leak, not a "
                    "pattern -- find it before touching real data."
                )
            else:
                result.notes.append(f"canary clean for {name}: AUC {s['roc_auc']:.3f}, "
                                    f"within 0.5 +/- {tolerance:.3f}.")

    if FLOOR in scores and not canary:
        floor = scores[FLOOR]
        for name, s in scores.items():
            if name in (MAJORITY, FLOOR):
                continue
            d_auc = s["roc_auc"] - floor["roc_auc"]
            d_ll = s["log_loss"] - floor["log_loss"]
            result.notes.append(
                f"{name} vs {FLOOR}: AUC {d_auc:+.3f}, log-loss {d_ll:+.4f}. One split, "
                f"one seed -- a gap inside +/- {se:.3f} is noise until #EVAL-3 repeats it."
            )

    # Ranking can survive overconfidence; log-loss cannot. A model scoring
    # clearly worse than the constant base-rate guess is sure of things that
    # are not so -- on the canary, that is memorised noise. "Clearly" is 5%:
    # any fitted model is a hair worse than the constant on pure noise, and
    # that is not worth an alarm.
    if MAJORITY in scores:
        base = scores[MAJORITY]["log_loss"]
        for name, s in scores.items():
            if name != MAJORITY and s["log_loss"] > 1.05 * base:
                result.warnings.append(
                    f"{name} log-loss {s['log_loss']:.3f} is clearly worse than the constant "
                    f"base-rate guess ({base:.3f}) -- confident and wrong. Overfit (#DL-3) "
                    "or miscalibrated (#DL-6)."
                )

    if synthetic:
        result.notes.append("synthetic data -- these numbers measure plumbing and model "
                            "capacity, not skill at League.")
    return result
