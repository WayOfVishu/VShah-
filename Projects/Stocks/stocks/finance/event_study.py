"""Event studies and market-efficiency anomalies -- BKM 9CE, Chapter 11.

Chapter 11 is the chapter that argues this project might not work, and it is
worth implementing for that reason before any other.

**The uncomfortable part first.** Weak-form EMH says everything derivable from
past prices and volume is already in the price, which if true makes every
`tech_*` and `ret_*` feature in `features/tabular.py` worthless. Semistrong
extends that to all public information, which covers every news document DS2
and DS3 will ever return. Taken at face value, the honest expected R-squared of
this entire pipeline is zero.

The chapter does not quite say that, and the gap is where the project lives:
markets are efficient enough that active management struggles to beat its
costs, and not so efficient that no analysis is worthwhile. `pipeline.py`'s
calibration note -- treat R-squared 0.01 as a genuine result, treat 0.4 as a
bug -- is Chapter 11 restated as an engineering expectation.

**The useful part.** LO3's event-study method is a measurement tool this
project can use directly. Abnormal return is what is left of a day's move after
the market's own move is removed:

    e_t = r_t - (alpha + beta * r_Mt)

That is the same residual `index_model.residual_series` produces, and the same
quantity Chapter 8 calls firm-specific. Chapter 11 adds two things to it: the
cumulative version (CAR) over a window, and the methodological rule that alpha
and beta must be estimated from a period well separated from the event, or the
benchmark is contaminated by the very abnormal performance being measured.

**Why CAR belongs in a feature row.** DS2 and DS3 tell the model what was
*said* about a company. CAR tells it how much the market *moved* on firm-
specific news over the same window, with the market's own direction stripped
out. Those are different measurements of the same underlying thing, and the gap
between them is informative: heavy negative coverage with no negative CAR means
the news was already priced -- exactly the semistrong-form prediction -- while
heavy coverage with a large CAR means it was not, which is the post-earnings-
announcement-drift situation the chapter flags as the anomaly most directly in
tension with efficiency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

__all__ = [
    "SIZE_EFFECT_SPREAD",
    "EventWindow",
    "abnormal_return",
    "abnormal_return_series",
    "cumulative_abnormal_return",
    "momentum_12_1",
    "long_horizon_reversal",
]

# Chapter 11, F3: the smallest-firm NYSE decile beat the largest by this much
# per year, 1926-2015, and the gap survives CAPM risk adjustment. Recorded as a
# constant because it is the benchmark any size-related finding in this project
# should be compared against -- and because the chapter's own puzzle (firm size
# is nearly costless to observe, so why has competition not eliminated it?) is
# the right note of scepticism to keep attached to the number.
SIZE_EFFECT_SPREAD = 0.0765


@dataclass(frozen=True, slots=True)
class EventWindow:
    """A cumulative abnormal return measured over a span of days."""

    car: float                   # cumulative abnormal return over the window
    mean_abnormal: float         # per-day average
    std_abnormal: float          # per-day dispersion, for the t-statistic
    n_days: int

    @property
    def tstat(self) -> float:
        """CAR divided by its standard error under independence.

        The independence assumption is the weak link and it is worth naming:
        abnormal returns on consecutive days are not independent when the event
        is a slow information release, which is precisely the post-earnings-
        drift case. This t-statistic is therefore optimistic in exactly the
        situation where the finding would be most interesting. Read it as a
        rough screen, not as inference.
        """
        if self.n_days < 2 or not self.std_abnormal:
            return float("nan")
        return self.car / (self.std_abnormal * np.sqrt(self.n_days))


def abnormal_return(
    actual_return: float, market_return: float, alpha: float, beta: float
) -> float:
    """Chapter 11, F2: one period's abnormal return.

        e_t = r_t - (alpha + beta * r_Mt)

    Example 11.3: alpha 0.05%, beta 0.8, market +1%, stock +2% gives an
    expected 0.85% and an abnormal 1.15%.

    Note these are **total** returns, not excess returns -- Chapter 11's market
    model regresses r on r_M directly, where Chapter 8's SCL regresses R on R_M
    with both in excess form. The two produce the same beta and different
    alphas, and the difference is (1 - beta) * r_f. Mixing the conventions is a
    quiet way to shift every abnormal return by a constant, so the parameter
    names here deliberately say `actual_return` and `market_return` rather than
    reusing the `_excess` naming from `index_model`.
    """
    return actual_return - (alpha + beta * market_return)


def abnormal_return_series(
    stock_returns: pd.Series,
    market_returns: pd.Series,
    alpha: float,
    beta: float,
) -> pd.Series:
    """`abnormal_return` over aligned series (Chapter 11, F1 and F2).

    `alpha` and `beta` are passed in rather than estimated here, and that is
    the chapter's central methodological caution made structural: LO3 requires
    the benchmark parameters to come from a period well separated from the
    event, so a function that estimated them from the same series it then
    measured would be contaminated by construction. The caller fits on the
    estimation window and measures on the event window.
    """
    joined = pd.concat({"stock": stock_returns, "market": market_returns},
                       axis=1, join="inner").dropna()
    return (joined["stock"] - (alpha + beta * joined["market"])).rename("abnormal")


def cumulative_abnormal_return(
    stock_returns: pd.Series,
    market_returns: pd.Series,
    alpha: float,
    beta: float,
    window: int | None = None,
) -> EventWindow:
    """CAR over the last `window` days (all of them if None).

    Abnormal returns are summed rather than compounded, which is the standard
    event-study convention and is exact when the inputs are log returns -- as
    they are everywhere in this project, since `returns.log_returns` feeds the
    whole pipeline. On simple returns the sum is an approximation that drifts
    on large moves.
    """
    resid = abnormal_return_series(stock_returns, market_returns, alpha, beta)
    if window is not None:
        resid = resid.tail(window)
    resid = resid.dropna()

    n = len(resid)
    if n == 0:
        return EventWindow(car=float("nan"), mean_abnormal=float("nan"),
                           std_abnormal=float("nan"), n_days=0)

    return EventWindow(
        car=float(resid.sum()),
        mean_abnormal=float(resid.mean()),
        std_abnormal=float(resid.std(ddof=1)) if n > 1 else float("nan"),
        n_days=n,
    )


def momentum_12_1(prices: pd.Series) -> float:
    """The standard momentum specification: 12-month return, skipping the last month.

    Chapter 11's LO4 documents short-to-intermediate-horizon momentum in
    individual stocks. The academic measure deliberately **excludes the most
    recent month**, and the reason is not cosmetic: at the one-month horizon
    stocks show short-term *reversal*, which is the opposite sign to momentum.
    Including it mixes two effects that point in opposite directions and
    attenuates both.

    This is why the existing `eq_ret_252d` is not a momentum feature. It is a
    twelve-month return with the reversal month left in, so it measures the
    blend rather than either component.
    """
    px = pd.Series(prices).dropna()
    # 252 trading days back to 21 days back: twelve months, minus the last one.
    if len(px) < 253:
        return float("nan")
    return float(np.log(px.iloc[-22] / px.iloc[-253]))


def long_horizon_reversal(prices: pd.Series) -> float:
    """Return over years 2-3 back, the horizon at which winners become losers.

    LO4's other half: past winners fade and past losers rebound over multi-year
    horizons. Emitted with the **sign flipped** so that a positive value means
    "reversal predicts an increase" -- i.e. the stock did badly two-to-three
    years ago and the anomaly says it is due a rebound.

    Flipping the sign here rather than leaving it to the model is a deliberate
    readability choice: a tree can learn either orientation equally well, but a
    Ridge coefficient on a feature whose name states its expected direction is
    something a human can sanity-check, and a negative coefficient on it is
    then immediately visible as the anomaly failing to appear.

    The behavioural reading (Chapter 12) is that short-run overreaction creates
    the momentum, and the long-run reversal is that overreaction correcting.
    """
    px = pd.Series(prices).dropna()
    # 756 trading days is roughly three years; 252 is one.
    if len(px) < 757:
        return float("nan")
    return float(-np.log(px.iloc[-253] / px.iloc[-757]))
