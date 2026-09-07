"""Valuation and risk math from Bodie/Kane/Marcus, *Investments*, 9th Canadian Edition.

Eight modules, each mapped to the chapter summaries in `References/Stocks`:

    returns.py       Ch 5    holding-period returns, annualization, Fisher, geometric mean
    risk.py          Ch 5-6  volatility, Sharpe, VaR, drawdown, higher moments
    portfolio.py     Ch 6-7  capital allocation, utility, y*, two-asset and Markowitz
    index_model.py   Ch 8    the SCL regression: alpha, beta, R-square, residual risk
    capm.py          Ch 9    the SML, forward alpha, zero-beta CAPM, hurdle rates
    multifactor.py   Ch 10   joint factor regressions, APT arbitrage, SMB/HML proxies
    event_study.py   Ch 11   abnormal returns, CAR, momentum and reversal anomalies
    technical.py     Ch 12   moving-average crossovers, relative strength, trin, parity

**How the later chapters changed the shape of this package.** Chapters 5-8 all
describe what a security *did*: every function was a statistic over a realised
series. Chapter 9 introduces the first genuinely forward object -- the SML says
what a stock *ought* to return given its beta -- and that is what lets a
forecast be scored rather than merely reported. `capm.evaluate_against_sml`
turns the pipeline's point estimate into an alpha, which is the input Chapter
8's `treynor_black_weights` needed all along and never had.

Chapters 10-12 then each qualify that in a different direction: Chapter 10 says
one beta is not enough to describe systematic risk, Chapter 11 says the alpha
you think you found is probably a mismeasured risk premium, and Chapter 12 says
the price patterns might be real but the procedure that finds them is a
data-mining machine. All three cautions are recorded in the module docstrings
rather than smoothed over, because they are the reason to distrust a good score
from this project, and that reason should live next to the code that produces it.

What is deliberately *not* here: discounted cash flow, dividend discount models,
FCFE, and multiples. Those live in BKM Chapters 13 and 18, which are not in the
reference set, and guessing at them would put unverified formulas next to
verified ones. The valuation content this project has is the risk-return and
index-model, and asset-pricing tradition, and that is what the features are
built from.

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

from .capm import (
    MARKET_RISK_PREMIUM_DEFAULT,
    SMLVerdict,
    beta_from_covariance,
    evaluate_against_sml,
    fair_profit,
    realised_market_risk_premium,
    required_return,
    sml_alpha,
    sml_expected_return,
    zero_beta_expected_return,
)
from .event_study import (
    SIZE_EFFECT_SPREAD,
    EventWindow,
    abnormal_return,
    abnormal_return_series,
    cumulative_abnormal_return,
    long_horizon_reversal,
    momentum_12_1,
)
from .multifactor import (
    MultiFactorResult,
    arbitrage_profit,
    fit_multifactor,
    hml_proxy,
    multifactor_expected_return,
    replicating_weights,
    smb_proxy,
)
from .technical import (
    ma_crossover_age,
    ma_crossover_state,
    moving_average,
    parity_premium,
    parity_ratio,
    relative_strength,
    relative_strength_trend,
    trin,
)
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
    "CompleteAllocation",
    "DEFAULT_RISK_AVERSION",
    "EventWindow",
    "MARKET_RISK_PREMIUM_DEFAULT",
    "MultiFactorResult",
    "SCLResult",
    "SIZE_EFFECT_SPREAD",
    "SMLVerdict",
    "TRADING_DAYS_PER_YEAR",
    "abnormal_return",
    "abnormal_return_series",
    "annualize",
    "annualized_volatility",
    "arbitrage_profit",
    "arithmetic_mean_return",
    "beta_from_covariance",
    "capital_allocation_line",
    "combined_sharpe_squared",
    "cumulative_abnormal_return",
    "effective_annual_rate",
    "evaluate_against_sml",
    "excess_kurtosis",
    "expected_shortfall",
    "fair_profit",
    "fit_multifactor",
    "fit_scl",
    "forward_log_return",
    "geometric_mean_return",
    "hml_proxy",
    "holding_period_return",
    "information_ratio",
    "log_returns",
    "long_horizon_reversal",
    "ma_crossover_age",
    "ma_crossover_state",
    "max_drawdown",
    "minimum_variance_weights",
    "momentum_12_1",
    "moving_average",
    "multifactor_expected_return",
    "optimal_risky_weight",
    "optimal_two_asset_weights",
    "parity_premium",
    "parity_ratio",
    "portfolio_return",
    "portfolio_variance",
    "real_rate_approx",
    "real_rate_exact",
    "realised_market_risk_premium",
    "relative_strength",
    "relative_strength_trend",
    "replicating_weights",
    "required_return",
    "residual_series",
    "rolling_beta",
    "scenario_expected_return",
    "scenario_variance",
    "sharpe_ratio",
    "simple_returns",
    "skewness",
    "smb_proxy",
    "sml_alpha",
    "sml_expected_return",
    "treynor_black_weights",
    "trin",
    "two_asset_return",
    "two_asset_variance",
    "utility_score",
    "value_at_risk_historical",
    "value_at_risk_normal",
    "volatility",
    "zero_beta_expected_return",
]
