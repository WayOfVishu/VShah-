"""Valuation and risk math from Bodie/Kane/Marcus, *Investments*, 9th Canadian Edition.

Four modules, each mapped to the chapters in `References/Stocks`:

    returns.py      Ch 5   holding-period returns, annualization, Fisher, geometric mean
    risk.py         Ch 5-6 volatility, Sharpe, VaR, drawdown, higher moments
    portfolio.py    Ch 6-7 capital allocation, utility, y*, two-asset and Markowitz
    index_model.py  Ch 8   the SCL regression: alpha, beta, R-square, residual risk

What is deliberately *not* here: discounted cash flow, dividend discount models,
FCFE, and multiples. Those live in BKM Chapters 13 and 18, which are not in the
reference set, and guessing at them would put unverified formulas next to
verified ones. The valuation content this project has is the risk-return and
index-model tradition, and that is what the features are built from.

Everything is pure functions over pandas/numpy with no I/O and no global state,
so any of it can be checked against the worked examples in a REPL. The examples
themselves are pinned in `tests/test_finance.py` -- if a refactor breaks one of
the textbook numbers, that fails.

Conventions, uniform throughout:

- rates are decimals, never percentages (8% is 0.08)
- `risk_free_rate` arguments are annual and get de-annualized internally
- return series may contain NaN; every function drops rather than fills
- annualization uses 252 trading days
"""

from __future__ import annotations

from .index_model import (
    SCLResult,
    combined_sharpe_squared,
    fit_scl,
    information_ratio,
    residual_series,
    rolling_beta,
    treynor_black_weights,
)
from .portfolio import (
    CompleteAllocation,
    DEFAULT_RISK_AVERSION,
    capital_allocation_line,
    minimum_variance_weights,
    optimal_risky_weight,
    optimal_two_asset_weights,
    portfolio_return,
    portfolio_variance,
    two_asset_return,
    two_asset_variance,
    utility_score,
)
from .returns import (
    TRADING_DAYS_PER_YEAR,
    annualize,
    arithmetic_mean_return,
    effective_annual_rate,
    forward_log_return,
    geometric_mean_return,
    holding_period_return,
    log_returns,
    real_rate_approx,
    real_rate_exact,
    simple_returns,
)
from .risk import (
    annualized_volatility,
    excess_kurtosis,
    expected_shortfall,
    max_drawdown,
    scenario_expected_return,
    scenario_variance,
    sharpe_ratio,
    skewness,
    value_at_risk_historical,
    value_at_risk_normal,
    volatility,
)

__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "DEFAULT_RISK_AVERSION",
    "SCLResult",
    "CompleteAllocation",
    "annualize",
    "annualized_volatility",
    "arithmetic_mean_return",
    "capital_allocation_line",
    "combined_sharpe_squared",
    "effective_annual_rate",
    "excess_kurtosis",
    "expected_shortfall",
    "fit_scl",
    "forward_log_return",
    "geometric_mean_return",
    "holding_period_return",
    "information_ratio",
    "log_returns",
    "max_drawdown",
    "minimum_variance_weights",
    "optimal_risky_weight",
    "optimal_two_asset_weights",
    "portfolio_return",
    "portfolio_variance",
    "real_rate_approx",
    "real_rate_exact",
    "residual_series",
    "rolling_beta",
    "scenario_expected_return",
    "scenario_variance",
    "sharpe_ratio",
    "simple_returns",
    "skewness",
    "treynor_black_weights",
    "two_asset_return",
    "two_asset_variance",
    "utility_score",
    "value_at_risk_historical",
    "value_at_risk_normal",
    "volatility",
]
