"""Technical analysis and its behavioural rationale -- BKM 9CE, Chapter 12.

Chapter 12 is where the textbook stops arguing that price patterns cannot exist
and starts offering a mechanism for why they might. That shift is what makes
this module defensible rather than superstition, and the distinction is worth
holding onto while reading the functions below.

**The mechanism.** The disposition effect -- investors hold losers too long and
sell winners too early -- generates real price momentum *even when fundamental
value follows a pure random walk*, because supply and demand respond to the
purchase price rather than to value. Overconfidence links trading volume to
subsequent returns, which is why technicians watch volume alongside price
rather than price alone. Neither claim requires markets to be irrational in any
deep sense; both require only that a large number of people share a
well-documented bias.

**The counter-argument, which the chapter takes seriously and so should this
module.** Technical signals are defined loosely enough that they can be fitted
to almost any chart after the fact, and testing enough patterns against history
will always turn up some that look significant by chance. The chapter names
this as data mining, and this project is exactly the setting where it bites: a
`GridSearchCV` over hundreds of feature-model combinations on a couple of
thousand overlapping rows is a data-mining machine. That is why
`evaluate.py`'s purged time-series split matters more than any indicator here,
and why every function in this module is a *feature* rather than a *signal* --
none of them return a buy or sell, they return a number the model may or may
not find useful, and `#ML-6`'s ablation is what decides which.

**What is missing and why.** The trin statistic (F3) is implemented but has no
data source: it needs market-wide advancing/declining issue counts and their
volumes, which neither yfinance nor GDELT serves. It is here because the
formula is verifiable and the worked examples pin it, and it is not wired into
`features/tabular.py` because there is nothing to wire. If a breadth provider
is ever added, this is the function it feeds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "moving_average",
    "ma_crossover_state",
    "ma_crossover_age",
    "relative_strength",
    "relative_strength_trend",
    "trin",
    "parity_ratio",
    "parity_premium",
]


def moving_average(prices: pd.Series, window: int = 50) -> pd.Series:
    """Chapter 12, F2: the simple n-day moving average.

        MA_t = (P_t + P_{t-1} + ... + P_{t-n+1}) / n

    Trailing only, never centred. A centred moving average is the single most
    effective way to leak the future into a price feature and it is invisible
    in a feature table -- see the module docstring of `features/tabular.py`.
    """
    return pd.Series(prices).rolling(window).mean()


def ma_crossover_state(prices: pd.Series, window: int = 50) -> float:
    """Where price sits relative to its moving average: +1 above, -1 below.

    The chapter's worked example: after a falling stretch the moving average
    sits above the price (it still carries stale higher prices), and a price
    breaking up through it is read as a shift from a falling to a rising trend.

    `features/tabular.py` already emits `tech_sma_dist_*`, the *distance* from
    the average as a fraction, which strictly contains this sign. This is
    emitted anyway because the crossover is the thing Chapter 12 actually
    describes, and a tree model has to spend a split to recover a sign from a
    continuous feature -- handing it over directly costs one column and saves
    that split. On a panel this small, that trade is worth making.
    """
    px = pd.Series(prices).dropna()
    ma = moving_average(px, window)
    if len(px) < window or not np.isfinite(ma.iloc[-1]):
        return float("nan")
    return 1.0 if px.iloc[-1] >= ma.iloc[-1] else -1.0


def ma_crossover_age(prices: pd.Series, window: int = 50, max_lookback: int = 252) -> float:
    """Trading days since price last crossed its moving average.

    The signal a technician acts on is the *crossing*, not the state -- a stock
    that has sat above its 50-day average for eight months crossed long ago and
    is not a fresh breakout. `ma_crossover_state` cannot tell those apart and
    this can.

    Returns `max_lookback` when no crossing is found in the window, rather than
    NaN: "no crossing in a year" is a real and meaningful observation about a
    persistent trend, and imputing it as missing would let the median imputer
    replace a genuine extreme with a typical value.
    """
    px = pd.Series(prices).dropna()
    ma = moving_average(px, window)
    side = np.sign(px - ma)
    side = side[np.isfinite(side)].tail(max_lookback)

    if len(side) < 2:
        return float("nan")

    current = side.iloc[-1]
    # Walk backwards to the most recent bar on the other side of the average.
    for age, value in enumerate(reversed(side.to_list())):
        if value != current and value != 0:
            return float(age)
    return float(max_lookback)


def relative_strength(stock_prices: pd.Series, benchmark_prices: pd.Series,
                      window: int = 63) -> float:
    """Relative strength: the stock's return over the benchmark's, same window.

    Chapter 12's LO2 describes this as comparing a security directly against a
    broader benchmark rather than looking at absolute price levels -- Toyota
    against the auto industry, in the chapter's example. Technicians who find
    relative strength persisting invest in the stronger performer, sometimes as
    a long-short across the pair.

    **How this differs from Chapter 8's beta, which is easy to conflate.** Beta
    is a regression slope over years, describing how the stock *co-moves* with
    the index. This is a simple return difference over one recent window,
    describing whether it *outperformed*. A stock with beta 1.0 can have
    strongly positive relative strength; the two are close to orthogonal, and
    both belong in the row.
    """
    stock = pd.Series(stock_prices).dropna()
    bench = pd.Series(benchmark_prices).dropna()
    if len(stock) <= window or len(bench) <= window:
        return float("nan")

    stock_ret = float(np.log(stock.iloc[-1] / stock.iloc[-1 - window]))
    bench_ret = float(np.log(bench.iloc[-1] / bench.iloc[-1 - window]))
    return stock_ret - bench_ret


def relative_strength_trend(stock_prices: pd.Series, benchmark_prices: pd.Series,
                            window: int = 63) -> float:
    """Change in relative strength: this window's, minus the preceding window's.

    Persistence is the property technicians claim for relative strength, so the
    question of whether it is *strengthening* is the one the chapter's argument
    actually turns on. A stock that outperformed by 5% last quarter and 8% this
    quarter is a different case from one that outperformed by 8% and then 5%,
    and a single-window measure reports them identically.
    """
    stock = pd.Series(stock_prices).dropna()
    bench = pd.Series(benchmark_prices).dropna()
    if len(stock) <= 2 * window or len(bench) <= 2 * window:
        return float("nan")

    def spread(offset: int) -> float:
        s = float(np.log(stock.iloc[-1 - offset] / stock.iloc[-1 - offset - window]))
        b = float(np.log(bench.iloc[-1 - offset] / bench.iloc[-1 - offset - window]))
        return s - b

    return spread(0) - spread(window)


def trin(
    advancing_volume: float, n_advancing: int,
    declining_volume: float, n_declining: int,
) -> float:
    """Chapter 12, F3: the trin statistic, a volume-weighted breadth measure.

        Trin = (declining volume / n declining) / (advancing volume / n advancing)

    Above 1.0 is conventionally read as bearish: volume is concentrating in
    falling issues relative to rising ones. Below 1.0, bullish.

    **Not wired into the feature pipeline**, because it needs market-wide
    advance/decline counts and volumes and no provider in `ingest/` serves
    them. Implemented because the formula is verifiable against the chapter and
    because leaving a hole where a named textbook formula should be is worse
    than a function with a docstring saying it has no inputs yet.
    """
    if n_advancing <= 0 or n_declining <= 0 or advancing_volume <= 0:
        return float("nan")
    return (declining_volume / n_declining) / (advancing_volume / n_advancing)


def parity_ratio(split_a: float, split_b: float) -> float:
    """Chapter 12, F1: the fair price ratio for profit-sharing "Siamese twin" shares.

    Royal Dutch and Shell split all profits 60/40, so Royal Dutch should always
    trade at exactly 60/40 = 1.5 times Shell. It did not -- a 10% premium in
    February 1993 that widened to 17% before reversing after 1999.
    """
    if split_b == 0:
        return float("nan")
    return split_a / split_b


def parity_premium(actual_ratio: float, fair_ratio: float) -> float:
    """Chapter 12, F1: fractional deviation from Law-of-One-Price parity.

        premium = (actual - fair) / fair

    Worth keeping in a project about forecasting because of what the Royal
    Dutch/Shell case demonstrates rather than what it computes. An arbitrageur
    who spotted the 10% mispricing in 1993 and traded it correctly would have
    watched it widen to 17% and lost money for six years before being right.
    Being right about value and being right about the next thirty days are
    different claims, and a model that predicts the former is not automatically
    useful for the latter -- which is the honest caveat on every alpha this
    project's Chapter 9 module produces.
    """
    if not fair_ratio:
        return float("nan")
    return (actual_ratio - fair_ratio) / fair_ratio
