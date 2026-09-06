"""Return arithmetic -- Bodie/Kane/Marcus 9CE, Chapter 5.

Every function here maps to a numbered formula on the Chapter 5 key-formulas
page, and the mapping is written in the docstring so you can check the code
against the source rather than trusting it.

One convention that runs through the whole project: **all rates are decimals**,
never percentages. 8% is `0.08`. Mixing the two is the single most common way
to get a plausible-looking wrong answer out of this kind of code -- a Sharpe
ratio comes out 100x too small and still looks like a number -- so there is no
percent-accepting variant of anything here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "simple_returns",
    "log_returns",
    "holding_period_return",
    "annualize",
    "effective_annual_rate",
    "arithmetic_mean_return",
    "geometric_mean_return",
    "real_rate_exact",
    "real_rate_approx",
    "forward_log_return",
]

# Trading days in a year. 252 is the standard convention for both NYSE and TSX
# and is what every annualisation below assumes.
TRADING_DAYS_PER_YEAR = 252


def simple_returns(prices: pd.Series) -> pd.Series:
    """Period-over-period simple return, r_t = P_t / P_{t-1} - 1."""
    return prices.pct_change()


def log_returns(prices: pd.Series) -> pd.Series:
    """Continuously compounded return, ln(P_t / P_{t-1}).

    Preferred as the model target over simple returns for two reasons that
    matter here: log returns add across time (a 21-day return is the sum of 21
    daily ones, so a rolling sum is the correct aggregation), and they are far
    closer to symmetric, which suits the squared-error losses in `pipeline.py`.
    """
    return np.log(prices / prices.shift(1))


def holding_period_return(p_start: float, p_end: float, income: float = 0.0) -> float:
    """HPR = (P_end - P_start + income) / P_start.

    `income` is any cash thrown off over the holding period -- dividends for a
    stock, coupons for a bond. Note this is the total-return definition, so if
    you are feeding it a dividend-adjusted price series you should leave
    `income` at zero or you will count dividends twice.
    """
    if p_start <= 0:
        raise ValueError("starting price must be positive")
    return (p_end - p_start + income) / p_start


def annualize(total_return: float, years: float) -> float:
    """Chapter 5, F2: 1 + r_annual = (1 + r_total)^(1/T).

    Converts a return earned over `years` into the equivalent constant annual
    rate, which is what makes horizons of different lengths comparable.
    """
    if years <= 0:
        raise ValueError("years must be positive")
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def effective_annual_rate(apr: float, periods_per_year: int) -> float:
    """EAR = (1 + APR/n)^n - 1; the n -> infinity limit is exp(APR) - 1.

    Chapter 5, LO2. Restates any quoted rate as if it compounded exactly once a
    year, so a monthly-compounding instrument can be compared with a quarterly
    one. Pass `periods_per_year=0` for continuous compounding.
    """
    if periods_per_year == 0:
        return float(np.expm1(apr))
    if periods_per_year < 0:
        raise ValueError("periods_per_year must be >= 0")
    return (1.0 + apr / periods_per_year) ** periods_per_year - 1.0


def arithmetic_mean_return(returns: pd.Series) -> float:
    """The simple average. The correct estimator of *next period's* expected return."""
    return float(returns.mean())


def geometric_mean_return(returns: pd.Series) -> float:
    """Chapter 5, F4: 1 + g = [(1+r_1)...(1+r_n)]^(1/n).

    The constant rate that compounds to the same terminal wealth as the actual
    sequence. Always <= the arithmetic mean, with the gap roughly half the
    variance for near-normal returns.

    Use the geometric mean to describe what an investment *did*, and the
    arithmetic mean to forecast what it *will do* next period. Reporting the
    arithmetic mean as historical performance overstates it, which is a known
    way to make a backtest look better than it was.
    """
    r = returns.dropna()
    if r.empty:
        return float("nan")
    if (r <= -1.0).any():
        # A -100% return wipes the position out; the product is zero and the
        # geometric mean is -100% regardless of what follows.
        return -1.0
    return float(np.exp(np.log1p(r).mean()) - 1.0)


def real_rate_exact(nominal: float, inflation: float) -> float:
    """Chapter 5, F1 (exact Fisher): 1 + r_real = (1 + r_nom) / (1 + i).

    >>> round(real_rate_exact(0.08, 0.05), 4)
    0.0286
    """
    return (1.0 + nominal) / (1.0 + inflation) - 1.0


def real_rate_approx(nominal: float, inflation: float) -> float:
    """Chapter 5, F1 (approximation): r_real ~= r_nom - i.

    Overstates the real rate by a factor of (1 + i). At 8% nominal and 5%
    inflation that is 3.00% against a true 2.86% -- 14 basis points, which is
    material at bond-desk scale and negligible at this project's scale. Kept
    alongside the exact form so the difference is visible rather than assumed.
    """
    return nominal - inflation


def forward_log_return(prices: pd.Series, horizon_days: int) -> pd.Series:
    """The model target: cumulative log return over the NEXT `horizon_days` bars.

    Indexed at time t, valued with information from t+1 .. t+horizon. Because
    log returns are additive, this is a forward-looking rolling sum, which is
    computed here as a difference of log prices:

        y_t = ln(P_{t+h}) - ln(P_t)

    The final `horizon_days` entries are NaN by construction -- those dates do
    not have their future yet. Do not fill them. Drop the rows. Imputing a
    target is not a missing-data problem, it is fabricating labels.
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be >= 1")
    log_p = np.log(prices)
    return log_p.shift(-horizon_days) - log_p
