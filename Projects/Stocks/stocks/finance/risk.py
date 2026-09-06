"""Risk measures -- Bodie/Kane/Marcus 9CE, Chapters 5 and 6.

Volatility, the Sharpe ratio, Value at Risk, drawdown, and the higher moments
that tell you how badly the normal-distribution assumption behind VaR is being
violated for the stock in front of you.

Almost everything here has both a *scenario* form (Chapter 5 F3: you have
probabilities and outcomes) and a *time series* form (Chapter 5 LO5: you have a
history and treat each observation as equally likely). The time-series form is
what the feature pipeline actually calls; the scenario form is here because it
is the one the textbook derives, and having both makes the relationship
between them checkable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .returns import TRADING_DAYS_PER_YEAR

__all__ = [
    "scenario_expected_return",
    "scenario_variance",
    "volatility",
    "annualized_volatility",
    "sharpe_ratio",
    "value_at_risk_normal",
    "value_at_risk_historical",
    "expected_shortfall",
    "max_drawdown",
    "skewness",
    "excess_kurtosis",
]

# Chapter 5, F6. The 1st percentile of the standard normal. The textbook rounds
# to 2.33; scipy would give 2.3263. Kept as the textbook value so worked
# examples reconcile, and named so the choice is visible rather than a literal.
NORMAL_1PCT_QUANTILE = 2.33
NORMAL_5PCT_QUANTILE = 1.645


def scenario_expected_return(probabilities: np.ndarray, returns: np.ndarray) -> float:
    """Chapter 5, F3: E(r) = sum p(s) * r(s)."""
    p, r = np.asarray(probabilities, float), np.asarray(returns, float)
    if not np.isclose(p.sum(), 1.0):
        raise ValueError(f"probabilities must sum to 1, got {p.sum():.6f}")
    return float(p @ r)


def scenario_variance(probabilities: np.ndarray, returns: np.ndarray) -> float:
    """Chapter 5, F3: Var(r) = sum p(s) * (r(s) - E(r))^2."""
    p, r = np.asarray(probabilities, float), np.asarray(returns, float)
    mu = scenario_expected_return(p, r)
    return float(p @ (r - mu) ** 2)


def volatility(returns: pd.Series, ddof: int = 1) -> float:
    """Sample standard deviation of a return series.

    `ddof=1` (Bessel's correction) because these are samples drawn from an
    unknown distribution, not a full population. The textbook's time-series
    section makes the same correction for the same reason. At n = 1260 (five
    years of daily bars) the difference is immaterial; at n = 42 (two months)
    it is not, and this function is called on both.
    """
    return float(returns.dropna().std(ddof=ddof))


def annualized_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Scale periodic volatility to annual by the square root of time.

    Valid only if returns are serially uncorrelated -- variance adds across
    independent periods, so standard deviation grows with sqrt(T). Real equity
    returns show mild negative autocorrelation at short lags and volatility
    clustering at all lags, so this slightly overstates true annual vol. It is
    the universal convention anyway, and the bias is consistent across every
    ticker, so it does not distort cross-sectional comparisons.
    """
    return volatility(returns) * np.sqrt(periods_per_year)


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Chapter 5, F5: S = [E(r_p) - r_f] / sigma_p, annualized.

    `risk_free_rate` is an *annual* rate and is de-annualized here to match the
    frequency of `returns`, so you can pass the 3-month T-bill yield straight
    from FRED without converting it yourself.

    The textbook's warning is worth repeating where the code is: the Sharpe
    ratio is a sound measure for a diversified portfolio and a poor one for a
    single stock, because it charges the stock for diversifiable risk that no
    rational investor would hold unhedged. Since this project forecasts single
    names, treat Sharpe as a feature, not as a verdict -- Chapter 8's
    information ratio in `index_model.py` is the better single-name measure.
    """
    r = returns.dropna()
    if r.empty:
        return float("nan")

    rf_per_period = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess = r - rf_per_period
    sd = excess.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(periods_per_year))


def value_at_risk_normal(returns: pd.Series, quantile: float = NORMAL_1PCT_QUANTILE) -> float:
    """Chapter 5, F6: VaR(1%) = mean - 2.33 * SD, assuming normality.

    Returned as a signed return (negative for a loss), not a positive
    magnitude. Compare with `value_at_risk_historical` on the same series: the
    gap between them is a direct read on how fat the left tail is, and for most
    single equities the normal figure is materially too optimistic.
    """
    r = returns.dropna()
    if r.empty:
        return float("nan")
    return float(r.mean() - quantile * r.std(ddof=1))


def value_at_risk_historical(returns: pd.Series, level: float = 0.01) -> float:
    """Empirical VaR -- the `level` quantile of the realised distribution.

    Chapter 5, LO6 recommends this over the normal formula whenever returns are
    fat-tailed, which for individual stocks they reliably are. It makes no
    distributional assumption, at the cost of being unable to say anything
    about a loss larger than the worst one in the sample.
    """
    r = returns.dropna()
    if r.empty:
        return float("nan")
    return float(np.quantile(r, level))


def expected_shortfall(returns: pd.Series, level: float = 0.01) -> float:
    """Mean return conditional on being worse than VaR -- "how bad is bad".

    Beyond the textbook (which stops at VaR), but cheap to compute and it fixes
    VaR's blind spot: VaR tells you the threshold of the worst 1%, and says
    nothing about how far past it things go. Two stocks can share a VaR and
    have very different expected shortfalls.
    """
    r = returns.dropna()
    if r.empty:
        return float("nan")
    cutoff = np.quantile(r, level)
    tail = r[r <= cutoff]
    return float(tail.mean()) if len(tail) else float(cutoff)


def max_drawdown(prices: pd.Series) -> float:
    """Largest peak-to-trough decline, as a negative fraction.

    Not a Chapter 5 formula, but it captures path risk that standard deviation
    misses entirely: two series can share a mean and variance while one drifts
    and the other collapses 60% in the middle. That distinction is exactly what
    a 30-day forecast cares about.
    """
    p = prices.dropna()
    if p.empty:
        return float("nan")
    running_peak = p.cummax()
    return float((p / running_peak - 1.0).min())


def skewness(returns: pd.Series) -> float:
    """Third standardized moment. Chapter 5, LO6.

    Negative skew -- the common case for equities -- means the left tail is
    longer: occasional large losses against frequent small gains. Any symmetric
    risk measure understates the danger of a negatively skewed series.
    """
    r = returns.dropna()
    return float(((r - r.mean()) ** 3).mean() / r.std(ddof=0) ** 3) if len(r) > 2 else float("nan")


def excess_kurtosis(returns: pd.Series) -> float:
    """Fourth standardized moment, minus 3. Chapter 5, LO6.

    Zero for a normal distribution; positive means fat tails. Daily equity
    returns typically land between 3 and 10, which is the quantitative reason
    `value_at_risk_normal` should not be trusted on its own.
    """
    r = returns.dropna()
    return float(((r - r.mean()) ** 4).mean() / r.std(ddof=0) ** 4 - 3.0) if len(r) > 3 else float("nan")
