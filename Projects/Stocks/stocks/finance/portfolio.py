"""Portfolio math -- Bodie/Kane/Marcus 9CE, Chapters 6 and 7.

Capital allocation between a risky portfolio and T-bills (Chapter 6), and
combining risky assets (Chapter 7).

A note on why this module exists in a single-stock forecaster. The forecast
itself never needs these formulas -- you can predict a 30-day return without
knowing what a minimum-variance portfolio is. They earn their place at the
*other* end, turning a prediction into a decision: `optimal_risky_weight`
answers "given this expected return and this volatility, how much should
actually be held?", which is the question a user of the web app really has. A
raw forecast of +3% is not actionable; +3% with 40% annualised vol implying a
y* of 0.19 is.

The three-stage logic from Chapter 7 LO3, which is the shape the app follows:

    1. find the best risky mix P            -- independent of any investor
    2. measure its risk premium and sigma   -- still investor-independent
    3. apply risk aversion A to get y*      -- the only investor-specific step

That separation property is why the model and the recommendation stay cleanly
decoupled: the model produces step 2's inputs and never needs to know A.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

__all__ = [
    "utility_score",
    "complete_portfolio_return",
    "complete_portfolio_std",
    "optimal_risky_weight",
    "capital_allocation_line",
    "two_asset_return",
    "two_asset_variance",
    "minimum_variance_weights",
    "optimal_two_asset_weights",
    "portfolio_return",
    "portfolio_variance",
    "CompleteAllocation",
]

# Chapter 6 uses A = 2 (aggressive) through A = 5 (conservative) in its worked
# examples, with 4 as the representative case. Used as the app's default.
DEFAULT_RISK_AVERSION = 4.0


def utility_score(expected_return: float, std_dev: float, risk_aversion: float) -> float:
    """Chapter 6, F1: U = E(r) - 0.5 * A * sigma^2.

    The CFA Institute's scoring function. A risk-free portfolio (sigma = 0)
    scores exactly its own return, since there is no variance to penalise.

    >>> round(utility_score(0.15, 0.22, 4.0), 4)
    0.0532
    """
    return expected_return - 0.5 * risk_aversion * std_dev**2


def complete_portfolio_return(y: float, risky_return: float, risk_free_rate: float) -> float:
    """Chapter 6, F2: E(r_C) = r_f + y * [E(r_P) - r_f]."""
    return risk_free_rate + y * (risky_return - risk_free_rate)


def complete_portfolio_std(y: float, risky_std: float) -> float:
    """Chapter 6, F3: sigma_C = y * sigma_P.

    Linear in y because the risk-free asset contributes neither variance nor
    covariance. This is what makes the CAL a straight line.

    **`abs(y)`, not `y`.** The chapter writes this as `sigma_C = y * sigma_P`
    because its whole discussion lives in the lending/borrowing range where
    y >= 0. This project reaches y < 0 routinely: `optimal_risky_weight` is fed
    a *forecast* risk premium, and whenever the model predicts a return below
    the risk-free rate the Chapter 6 optimum is a short, so y* comes out
    negative. Applying the formula literally there returns a negative standard
    deviation, which is not a quantity that exists.

    Shorting twice as much is twice as risky, not negatively risky. The sign of
    y is a direction; sigma is a magnitude. Variance is y^2 * sigma_P^2 either
    way, and the positive root is the standard deviation.

    >>> complete_portfolio_std(-0.5, 0.30)
    0.15
    """
    return abs(y) * risky_std


def optimal_risky_weight(
    risky_return: float, risky_std: float, risk_free_rate: float,
    risk_aversion: float = DEFAULT_RISK_AVERSION,
) -> float:
    """Chapter 6, F4: y* = [E(r_P) - r_f] / (A * sigma_P^2).

    The most heavily tested calculation in the chapter, and the one that turns
    a forecast into a position size. Proportional to the risk premium, inversely
    proportional to risk aversion and to variance.

    Returned unclamped. A y* above 1 means borrowing at the risk-free rate to
    lever the position, and a negative y* means the forecast risk premium is
    negative, i.e. short. Both are meaningful answers, and clamping them here
    would hide the model telling you something. Clamp at the presentation layer
    if you want to -- `backend/app/routers/predict.py` does, and says so.

    >>> round(optimal_risky_weight(0.15, 0.22, 0.07, 4.0), 4)
    0.4132
    """
    if risky_std <= 0:
        raise ValueError("risky_std must be positive")
    if risk_aversion <= 0:
        raise ValueError("risk_aversion must be positive")
    return (risky_return - risk_free_rate) / (risk_aversion * risky_std**2)


@dataclass(frozen=True, slots=True)
class CompleteAllocation:
    """A fully solved Chapter 6 capital allocation, for the API to return."""

    y_star: float
    expected_return: float
    std_dev: float
    sharpe_ratio: float
    utility: float
    risk_aversion: float

    @property
    def is_levered(self) -> bool:
        return self.y_star > 1.0

    @property
    def is_short(self) -> bool:
        return self.y_star < 0.0


def capital_allocation_line(
    risky_return: float, risky_std: float, risk_free_rate: float,
    risk_aversion: float = DEFAULT_RISK_AVERSION,
) -> CompleteAllocation:
    """Solve the complete Chapter 6 allocation in one call.

    Reproduces Example 6.4 exactly (r_f = 7%, E(r_P) = 15%, sigma_P = 22%,
    A = 4 -> y* = 0.41, E(r_C) = 10.28%, sigma_C = 9.02%), which is asserted in
    tests/test_finance.py.

    Note that the returned Sharpe ratio equals the risky portfolio's own Sharpe
    ratio, always. Every point on the CAL shares one slope -- that is what makes
    it a line -- so leverage cannot improve risk-adjusted return, only scale it.
    """
    y = optimal_risky_weight(risky_return, risky_std, risk_free_rate, risk_aversion)
    e_rc = complete_portfolio_return(y, risky_return, risk_free_rate)
    sd_c = complete_portfolio_std(y, risky_std)

    sharpe = (risky_return - risk_free_rate) / risky_std if risky_std else float("nan")

    return CompleteAllocation(
        y_star=y,
        expected_return=e_rc,
        std_dev=sd_c,
        sharpe_ratio=sharpe,
        utility=utility_score(e_rc, sd_c, risk_aversion),
        risk_aversion=risk_aversion,
    )


def two_asset_return(w_d: float, e_rd: float, e_re: float) -> float:
    """Chapter 7, F1: E(r_P) = w_D*E(r_D) + w_E*E(r_E), with w_E = 1 - w_D."""
    return w_d * e_rd + (1.0 - w_d) * e_re


def two_asset_variance(w_d: float, sd_d: float, sd_e: float, corr: float) -> float:
    """Chapter 7, F2: sigma_P^2 = w_D^2*sd_D^2 + w_E^2*sd_E^2 + 2*w_D*w_E*Cov.

    Unlike expected return, variance is *not* a weighted average. The covariance
    term is the entire diversification effect: whenever correlation is below +1,
    portfolio standard deviation comes in under the weighted average of the
    components, and at correlation -1 there are weights that drive it to zero.
    """
    if not -1.0 <= corr <= 1.0:
        raise ValueError(f"correlation must be in [-1, 1], got {corr}")
    w_e = 1.0 - w_d
    cov = corr * sd_d * sd_e
    return w_d**2 * sd_d**2 + w_e**2 * sd_e**2 + 2.0 * w_d * w_e * cov


def minimum_variance_weights(sd_d: float, sd_e: float, corr: float) -> tuple[float, float]:
    """Chapter 7, F3: the two-asset weights that minimise variance.

        w_D(min) = [sd_E^2 - Cov] / [sd_D^2 + sd_E^2 - 2*Cov]

    Reproduces Example 7.1 (bond fund sd 12%, stock fund sd 20%, rho 0.30 ->
    w_D = 0.82, sigma_min = 11.45%, below *either* component's own standard
    deviation).
    """
    cov = corr * sd_d * sd_e
    denom = sd_d**2 + sd_e**2 - 2.0 * cov
    if denom == 0:
        raise ValueError("degenerate inputs: variance denominator is zero")
    w_d = (sd_e**2 - cov) / denom
    return w_d, 1.0 - w_d


def optimal_two_asset_weights(
    excess_d: float, excess_e: float, sd_d: float, sd_e: float, corr: float
) -> tuple[float, float]:
    """Chapter 7, F4: the Sharpe-maximising two-asset weights.

        w_D* = [E(R_D)sd_E^2 - E(R_E)Cov] /
               [E(R_D)sd_E^2 + E(R_E)sd_D^2 - (E(R_D)+E(R_E))Cov]

    `excess_d` and `excess_e` are **excess** returns over r_f, not total
    returns. The chapter flags this as a common point of confusion, and passing
    total returns here produces a plausible wrong answer rather than an error,
    so the parameters are named to make the mistake harder.

    Reproduces Example 7.2: w_D = 0.40, w_E = 0.60, Sharpe 0.42.
    """
    cov = corr * sd_d * sd_e
    num = excess_d * sd_e**2 - excess_e * cov
    denom = excess_d * sd_e**2 + excess_e * sd_d**2 - (excess_d + excess_e) * cov
    if denom == 0:
        raise ValueError("degenerate inputs: optimal-weight denominator is zero")
    w_d = num / denom
    return w_d, 1.0 - w_d


def portfolio_return(weights: np.ndarray, expected_returns: np.ndarray) -> float:
    """Chapter 7, F5 (Markowitz, n assets): E(r_P) = sum w_i * E(r_i)."""
    w, mu = np.asarray(weights, float), np.asarray(expected_returns, float)
    if w.shape != mu.shape:
        raise ValueError(f"shape mismatch: weights {w.shape} vs returns {mu.shape}")
    return float(w @ mu)


def portfolio_variance(weights: np.ndarray, cov_matrix: np.ndarray | pd.DataFrame) -> float:
    """Chapter 7, F5 (Markowitz, n assets): sigma_P^2 = w' * Cov * w.

    The full quadratic form. Note the input burden the chapter points out and
    which motivates Chapter 8's index model: n assets need n expected returns,
    n variances, and n(n-1)/2 distinct covariances. At n = 500 that is over
    124,000 covariance estimates from a few years of data -- which is why the
    single-index model, needing only n betas, exists at all.
    """
    w = np.asarray(weights, float)
    cov = cov_matrix.to_numpy(float) if isinstance(cov_matrix, pd.DataFrame) else np.asarray(cov_matrix, float)
    if cov.shape != (w.size, w.size):
        raise ValueError(f"covariance matrix must be {w.size}x{w.size}, got {cov.shape}")
    return float(w @ cov @ w)
