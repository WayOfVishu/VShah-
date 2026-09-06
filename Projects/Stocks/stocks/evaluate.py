"""Time-aware validation and honest scoring.

This module exists to stop the pipeline from lying to you, which for a
financial forecasting model is the default outcome rather than an edge case.

**Purged walk-forward splitting.** `PurgedTimeSeriesSplit` is `TimeSeriesSplit`
with a gap between each training fold and its validation fold. The gap is not
an optional refinement:

    as_of dates:  ... Mar 1   Mar 8   Mar 15  Mar 22  Mar 29 ...
    train                                |
    valid                                          |

The row at Mar 15 is labelled with the return from Mar 15 to roughly Apr 12.
The row at Mar 22 is labelled with Mar 22 to Apr 19. Those labels **overlap by
three weeks**. Train on Mar 15 and validate on Mar 22 and the model has already
seen most of the answer -- not through a feature, but through the label of a
neighbouring row. The split is chronological and the leak still happens.

The fix is to purge: drop training rows whose label window reaches into the
validation period. That is what `gap` does, and it must be at least the horizon
in rows (21 trading days / 7-day steps = 3 rows for the defaults).

Skipping this is the single most common way a published-looking backtest turns
out to be worthless, and it is invisible -- purged and unpurged runs both
complete and both print a number. The unpurged one is just bigger.

**The metrics.** `regression_report` leads with R-squared but shows several
others, because R-squared alone is a poor guide here:

    r2                out-of-sample. A 30-day equity return is close to
                      unpredictable; published work treats 0.01 as real.
                      Negative is normal and means you did worse than the mean.
    directional_acc   share of correct sign calls. The tradeable question.
                      50% is a coin flip. 53% sustained is a real edge.
    information_coef  Spearman correlation of prediction with outcome. The
                      standard quant metric, because it is rank-based and so
                      is unmoved by the outliers that dominate MSE. 0.03-0.05
                      is a respectable IC.
    hit_rate_top_decile  among the strongest 10% of predictions, how often was
                      the direction right? This is the one that matters for
                      acting on a forecast -- you never trade the median call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import BaseCrossValidator

from .features.assemble import META_PREFIX
from .windows import DEFAULT_HORIZON_DAYS

log = logging.getLogger(__name__)

__all__ = [
    "PurgedTimeSeriesSplit",
    "regression_report",
    "directional_accuracy",
    "information_coefficient",
    "EvaluationResult",
    "evaluate_pipeline",
    "purge_gap_rows",
]


def purge_gap_rows(step_days: int = 7, horizon_days: int = DEFAULT_HORIZON_DAYS) -> int:
    """How many rows must be purged between train and validation.

    The label at as-of date t covers t to t + horizon. Any training row within
    `horizon` of the validation boundary has a label that overlaps validation
    data. Converting the horizon from trading days to calendar days and
    dividing by the sweep's step gives the number of rows to drop.

    Note that even a 30-day step does not give independent rows at a 21-day
    horizon: the label spans ~34 calendar days, so consecutive rows still
    overlap by four days and one row must still be purged either side.

    >>> purge_gap_rows(step_days=7, horizon_days=21)
    5
    >>> purge_gap_rows(step_days=30, horizon_days=21)
    2
    """
    calendar_days = int(horizon_days * 7 / 5) + 5
    return max(1, int(np.ceil(calendar_days / step_days)))


class PurgedTimeSeriesSplit(BaseCrossValidator):
    """Expanding-window CV with a purge gap. Drop-in for `TimeSeriesSplit`.

        cv = PurgedTimeSeriesSplit(n_splits=5, gap=purge_gap_rows())
        cross_validate(pipe, X, y, cv=cv, scoring="r2")

    Expanding rather than sliding: each fold trains on everything before its
    validation window, which mirrors how the model would actually be used --
    on any given day you have all the history up to that day, not a fixed-width
    slice of it.

    Requires the input to be sorted by as-of date. `build_panel` guarantees
    that; if you resample or shuffle the panel yourself, sort it again first or
    every guarantee in this module is void.
    """

    def __init__(self, n_splits: int = 5, gap: int = 3, min_train_size: int | None = None) -> None:
        if n_splits < 2:
            raise ValueError("n_splits must be >= 2")
        self.n_splits = n_splits
        self.gap = gap
        self.min_train_size = min_train_size

    def get_n_splits(self, X=None, y=None, groups=None) -> int:
        return self.n_splits

    def split(self, X, y=None, groups=None):
        n = len(X)
        fold_size = n // (self.n_splits + 1)
        min_train = self.min_train_size or fold_size

        if fold_size <= self.gap:
            raise ValueError(
                f"panel too small: {n} rows over {self.n_splits} splits gives folds of "
                f"{fold_size} rows, which cannot absorb a purge gap of {self.gap}. "
                "Use fewer splits, or sweep a longer date range."
            )

        for i in range(self.n_splits):
            train_end = fold_size * (i + 1)
            valid_start = train_end + self.gap
            valid_end = min(valid_start + fold_size, n)

            if valid_start >= n or train_end < min_train:
                continue
            yield np.arange(0, train_end), np.arange(valid_start, valid_end)


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Share of predictions with the correct sign.

    Zero-valued truths are excluded -- a return of exactly zero has no
    direction to get right, and counting them inflates the denominator.
    """
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    mask = y_true != 0
    return float(np.mean(np.sign(y_pred[mask]) == np.sign(y_true[mask]))) if mask.any() else float("nan")


def information_coefficient(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Spearman rank correlation between predictions and outcomes.

    Rank-based, so a single 40% move does not dominate the score the way it
    dominates MSE. This is the metric the quant literature reports, and an IC
    of 0.03-0.05 that holds out of sample is a real, usable signal -- which is
    worth internalising, because it looks like nothing next to a classification
    accuracy.
    """
    s_true = pd.Series(np.asarray(y_true, float))
    s_pred = pd.Series(np.asarray(y_pred, float))
    if s_true.nunique() < 2 or s_pred.nunique() < 2:
        return float("nan")
    return float(s_true.corr(s_pred, method="spearman"))


def hit_rate_top_decile(y_true: np.ndarray, y_pred: np.ndarray, q: float = 0.1) -> float:
    """Directional accuracy among the strongest-conviction predictions.

    You would never act on the model's median call. What matters is whether the
    predictions it is *most confident about* are right, and it is entirely
    possible for overall directional accuracy to sit at 50% while this is 58% --
    that is a usable model. It is also possible for this to be worse than the
    overall rate, which means confidence is anti-correlated with correctness and
    the model should not be traded at all.
    """
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    if len(y_true) < 20:
        return float("nan")
    threshold = np.quantile(np.abs(y_pred), 1.0 - q)
    mask = (np.abs(y_pred) >= threshold) & (y_true != 0)
    return float(np.mean(np.sign(y_pred[mask]) == np.sign(y_true[mask]))) if mask.any() else float("nan")


def regression_report(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Every metric worth reading, in one dict."""
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[mask], y_pred[mask]

    if len(y_true) < 2:
        return {k: float("nan") for k in
                ("r2", "rmse", "mae", "directional_accuracy", "information_coefficient",
                 "hit_rate_top_decile", "n")}

    return {
        "r2": float(r2_score(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "directional_accuracy": directional_accuracy(y_true, y_pred),
        "information_coefficient": information_coefficient(y_true, y_pred),
        "hit_rate_top_decile": hit_rate_top_decile(y_true, y_pred),
        "n": float(len(y_true)),
    }


@dataclass(slots=True)
class EvaluationResult:
    """Per-fold and pooled scores from a walk-forward evaluation."""

    fold_scores: list[dict[str, float]] = field(default_factory=list)
    pooled: dict[str, float] = field(default_factory=dict)
    n_splits: int = 0
    gap: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.fold_scores, index=[f"fold {i + 1}" for i in range(len(self.fold_scores))])

    def summary(self) -> str:
        lines = [f"walk-forward evaluation -- {self.n_splits} splits, purge gap {self.gap} rows", ""]
        lines.append(self.to_frame().round(4).to_string())
        lines += ["", "pooled across folds:"]
        for k, v in self.pooled.items():
            lines.append(f"  {k:<26} {v:>10.4f}")

        # The comparisons that stop a run from being over-read. Printed with
        # the numbers rather than left to the reader to remember.
        r2 = self.pooled.get("r2", float("nan"))
        da = self.pooled.get("directional_accuracy", float("nan"))
        lines.append("")
        if np.isfinite(r2):
            if r2 > 0.15:
                lines.append("  !! R-squared above 0.15 on a 30-day horizon is implausible.")
                lines.append("     Check for leakage before believing this.")
            elif r2 > 0:
                lines.append(f"  R-squared is positive ({r2:.4f}) -- beating the mean. For this")
                lines.append("     horizon that is a genuine result, however small it looks.")
            else:
                lines.append("  R-squared is negative -- worse than predicting the mean. Normal")
                lines.append("     for a first run; compare against the zero baseline (#ML-3).")
        if np.isfinite(da):
            lines.append(f"  Directional accuracy {da:.1%} against a 50% coin flip.")

        for w in self.warnings:
            lines.append(f"  !! {w}")
        return "\n".join(lines)


def evaluate_pipeline(
    pipe,
    panel: pd.DataFrame,
    *,
    n_splits: int = 5,
    step_days: int = 7,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    target_col: str = "target",
) -> EvaluationResult:
    """Fit and score `pipe` across purged walk-forward folds.

    Returns per-fold and pooled metrics. Pooled scores are computed on the
    concatenated out-of-fold predictions rather than by averaging fold scores --
    averaging R-squared across folds of unequal size and variance is not a
    meaningful quantity, whereas a single R-squared over all out-of-fold
    predictions is.
    """
    if target_col not in panel.columns:
        raise ValueError(f"panel has no {target_col!r} column")

    panel = panel.sort_values(f"{META_PREFIX}as_of") if f"{META_PREFIX}as_of" in panel else panel
    X = panel.drop(columns=[target_col])
    y = panel[target_col].to_numpy(float)

    gap = purge_gap_rows(step_days, horizon_days)
    cv = PurgedTimeSeriesSplit(n_splits=n_splits, gap=gap)

    result = EvaluationResult(n_splits=n_splits, gap=gap)

    if f"{META_PREFIX}n_synthetic" in panel and (panel[f"{META_PREFIX}n_synthetic"] > 0).any():
        result.warnings.append(
            "panel contains synthetic data -- these scores measure plumbing, not skill"
        )

    all_true, all_pred = [], []
    for train_idx, valid_idx in cv.split(X):
        pipe.fit(X.iloc[train_idx], y[train_idx])
        pred = pipe.predict(X.iloc[valid_idx])
        result.fold_scores.append(regression_report(y[valid_idx], pred))
        all_true.append(y[valid_idx])
        all_pred.append(pred)

    if not all_true:
        raise RuntimeError("no folds produced predictions -- panel is likely too small")

    result.pooled = regression_report(np.concatenate(all_true), np.concatenate(all_pred))
    return result
