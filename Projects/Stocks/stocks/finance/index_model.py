"""The single-index model -- Bodie/Kane/Marcus 9CE, Chapter 8.

This is the most useful chapter in the course for this project, because it is
the one that says something about a *single stock* rather than a portfolio, and
a single stock is what the web app is asked about.

The central idea (Chapter 8, F1): a security's total risk splits cleanly into
two uncorrelated pieces.

    sigma_i^2  =  beta_i^2 * sigma_M^2   +   sigma^2(e_i)
    total          systematic                firm-specific

Systematic risk comes from the stock's exposure to the market and cannot be
diversified away. Firm-specific risk is everything else, and it averages out in
a large portfolio.

Why that decomposition earns its place in a forecasting pipeline: the two
halves are driven by *different datasets*. Systematic risk is what DS2 (the
indices) speaks to. Firm-specific risk is what DS3 (the synthesised sentiment
brief) speaks to. Regressing the stock on the index and keeping the residual is
what separates the two signals, so the sentiment features are asked to explain
firm-specific moves rather than competing with the index to re-explain market
moves the index already accounts for.

`fit_scl` is therefore not decoration -- `features/tabular.py` calls it, and
`residual_series` produces the cleanest single target this project has.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .returns import TRADING_DAYS_PER_YEAR

__all__ = [
    "SCLResult",
    "fit_scl",
    "residual_series",
    "rolling_beta",
    "information_ratio",
    "treynor_black_weights",
    "combined_sharpe_squared",
]


@dataclass(frozen=True, slots=True)
class SCLResult:
    """Output of the Security Characteristic Line regression (Chapter 8, F2).

        R_i = alpha_i + beta_i * R_M + e_i        where R = r - r_f

    Field names mirror the textbook's notation so the code and the chapter can
    be read side by side. The example in the chapter -- Suncor on the S&P/TSX,
    60 months of 2013-2017 -- yields alpha 0.0016, beta 1.1048, R-square 0.2052,
    and is reproduced as a regression test in tests/test_finance.py.
    """

    alpha: float                 # intercept: non-market expected excess return
    beta: float                  # slope: sensitivity to the index
    r_squared: float             # Chapter 8, F4: fraction of variance the market explains
    residual_std: float          # sigma(e_i): firm-specific risk
    alpha_stderr: float
    beta_stderr: float
    n_obs: int
    periods_per_year: int

    @property
    def alpha_tstat(self) -> float:
        return self.alpha / self.alpha_stderr if self.alpha_stderr else float("nan")

    @property
    def beta_tstat(self) -> float:
        return self.beta / self.beta_stderr if self.beta_stderr else float("nan")

    @property
    def annualized_alpha(self) -> float:
        """Alpha scaled to a year. Returns compound, so this is not alpha * periods."""
        return (1.0 + self.alpha) ** self.periods_per_year - 1.0

    @property
    def correlation(self) -> float:
        """sqrt(R^2), signed by beta -- the chapter reports this alongside R-square."""
        return float(np.sign(self.beta) * np.sqrt(max(self.r_squared, 0.0)))

    @property
    def systematic_variance_share(self) -> float:
        """Same number as R-square, named for what it means in F1's decomposition."""
        return self.r_squared

    @property
    def firm_specific_variance_share(self) -> float:
        """1 - R^2. The share of variance that DS2/DS3 text features have to explain."""
        return 1.0 - self.r_squared

    @property
    def information_ratio(self) -> float:
        """Chapter 8, F5: alpha / sigma(e). Reward per unit of firm-specific risk.

        The right risk-adjusted measure for a single stock, where the Sharpe
        ratio is not -- Sharpe charges the name for diversifiable risk, this
        does not.
        """
        return self.alpha / self.residual_std if self.residual_std else float("nan")


def fit_scl(
    stock_excess: pd.Series,
    market_excess: pd.Series,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> SCLResult:
    """Regress stock excess returns on market excess returns (Chapter 8, F2).

    Both inputs must be **excess** returns (r - r_f), not total returns. The
    chapter is emphatic about this and the reason is economic, not cosmetic: it
    is the spread between the market return and the risk-free rate that signals
    good or bad macro news. An 8% return was disappointing when bills yielded
    10% and excellent when they yielded 3%, and a regression on total returns
    cannot tell those apart.

    Implemented with `np.polyfit` rather than statsmodels to keep the dependency
    list short -- ordinary least squares on one regressor is a closed form, and
    the standard errors below are the textbook formulas rather than anything
    exotic.

    The two series are inner-joined on their index first, so a stock that did
    not trade on a day the index did is dropped rather than silently misaligned
    by one bar. Misalignment by one bar is a real and very hard-to-spot way to
    manufacture alpha out of nothing.
    """
    joined = pd.concat(
        {"stock": stock_excess, "market": market_excess}, axis=1, join="inner"
    ).dropna()

    n = len(joined)
    if n < 3:
        raise ValueError(f"need at least 3 aligned observations, got {n}")

    x = joined["market"].to_numpy(float)
    y = joined["stock"].to_numpy(float)

    beta, alpha = np.polyfit(x, y, 1)

    fitted = alpha + beta * x
    resid = y - fitted

    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    # Residual standard error uses n - 2 degrees of freedom: two parameters
    # (alpha, beta) were estimated from the same data.
    dof = n - 2
    resid_var = ss_res / dof
    sxx = float(((x - x.mean()) ** 2).sum())

    beta_se = float(np.sqrt(resid_var / sxx)) if sxx > 0 else float("nan")
    alpha_se = float(np.sqrt(resid_var * (1.0 / n + x.mean() ** 2 / sxx))) if sxx > 0 else float("nan")

    return SCLResult(
        alpha=float(alpha),
        beta=float(beta),
        r_squared=float(r_squared),
        residual_std=float(np.sqrt(resid_var)),
        alpha_stderr=alpha_se,
        beta_stderr=beta_se,
        n_obs=n,
        periods_per_year=periods_per_year,
    )


def residual_series(
    stock_excess: pd.Series, market_excess: pd.Series, scl: SCLResult | None = None
) -> pd.Series:
    """The e_i series: the stock's return with the market's influence removed.

    This is the most useful single output of the module for the ML side. A
    model trained to predict raw stock returns spends most of its capacity
    re-learning "the market went up". A model trained on residuals is being
    asked the question the news datasets can actually answer: what did this
    company do that the market did not?

    Consider it as an alternative target in `features/assemble.py` -- it is
    wired up there behind `target="residual"`.
    """
    scl = scl or fit_scl(stock_excess, market_excess)
    joined = pd.concat(
        {"stock": stock_excess, "market": market_excess}, axis=1, join="inner"
    ).dropna()
    return joined["stock"] - (scl.alpha + scl.beta * joined["market"])


def rolling_beta(
    stock_excess: pd.Series, market_excess: pd.Series, window: int = 126
) -> pd.Series:
    """Beta estimated over a trailing window, as a time-varying feature.

    A single beta over five years is one number that assumes the relationship
    never changed. It always changed. 126 bars is roughly six months -- long
    enough for a stable estimate, short enough to move when the business does.

    The *direction* of this series is often the informative part: a beta that
    has been climbing means the name is becoming more macro-sensitive, which
    shifts predictive weight from DS3 (sentiment) toward DS2 (the indices).
    """
    joined = pd.concat(
        {"stock": stock_excess, "market": market_excess}, axis=1, join="inner"
    ).dropna()

    cov = joined["stock"].rolling(window).cov(joined["market"])
    var = joined["market"].rolling(window).var()
    return (cov / var).rename("rolling_beta")


def information_ratio(alpha: float, residual_std: float) -> float:
    """Chapter 8, F5: alpha / sigma(e). Free function for use outside SCLResult."""
    return alpha / residual_std if residual_std else float("nan")


def treynor_black_weights(alphas: pd.Series, residual_variances: pd.Series) -> pd.Series:
    """Chapter 8, F6: w_i proportional to alpha_i / sigma^2(e_i), normalized to sum 1.

    Given per-security alphas and residual variances, this gives the optimal
    active-portfolio weights. Securities with negative alpha get negative
    (short) weights, and the weights are scaled to sum to one.

    Not needed to forecast one stock, but this is where the project goes if you
    extend it from "predict this ticker" to "rank a universe and build a
    portfolio" -- the model's per-name predicted alpha feeds straight in here.
    Left implemented rather than stubbed because it is four lines and having it
    present makes the extension obvious.
    """
    ratios = (alphas / residual_variances).dropna()
    total = ratios.sum()
    if total == 0:
        raise ValueError("alpha/residual-variance ratios sum to zero; weights undefined")
    return ratios / total


def combined_sharpe_squared(market_sharpe: float, active_information_ratio: float) -> float:
    """Chapter 8, F5: S_P^2 = S_M^2 + [alpha_A / sigma(e_A)]^2.

    The optimally combined portfolio's squared Sharpe ratio is the passive
    index's plus the square of the active portfolio's information ratio. Since
    the second term cannot be negative, security analysis can only help -- if it
    is implemented optimally.

    That last clause is the load-bearing one, and it is the honest frame for
    this whole project: the ceiling on how much a forecasting model can add is
    set by its information ratio, and information ratios that survive
    out-of-sample testing are small. `evaluate.py` reports this number so the
    result is stated in the units the textbook uses.
    """
    return market_sharpe**2 + active_information_ratio**2
