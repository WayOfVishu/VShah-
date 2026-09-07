"""Multifactor models and the APT -- Bodie/Kane/Marcus 9CE, Chapter 10.

Chapter 8 summarises all systematic risk in one number. Chapter 10's objection
is that two stocks with the same market beta can respond completely differently
to an interest-rate shock, and collapsing that into a single beta throws the
difference away.

**What this project was doing before, and why it is not the same thing.**
`features/tabular.py` already regresses the stock against four indices -- but
*separately*, one univariate fit each. Four single-factor models are not a
multifactor model. Because the S&P 500 and the NASDAQ are correlated around
0.9, `scl_gspc_beta` and `scl_ixic_beta` are largely the same number twice, and
neither is the *marginal* sensitivity to tech given broad-market exposure.
`fit_multifactor` runs one joint regression, so each loading is conditional on
the others, which is the quantity Chapter 10 is actually about.

**The factor proxies here are proxies, and the naming says so.** Real
Fama-French SMB and HML come from Ken French's data library, built from CRSP
book-to-market sorts. This module builds `smb_proxy` and `hml_proxy` from
long-short spreads between index ETFs, because those are free, keyless, and
already flowing through DS2. They are correlated with the real factors but they
are not them, and any loading estimated against them should be read as
directional rather than comparable to a published FF loading. Chapter 10's own
closing caution -- that empirically chosen factors are unstable once
discovered -- applies doubly to a proxy of a proxy.

The APT half of the chapter (F1, F4) is arbitrage logic rather than estimation:
a replicating portfolio matched on factor betas, and the riskless profit when
its expected return differs from the portfolio it replicates. Implemented
because the worked examples pin it, and because `arbitrage_profit` is the
cleanest statement of what a mispricing is worth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .returns import TRADING_DAYS_PER_YEAR

__all__ = [
    "MultiFactorResult",
    "fit_multifactor",
    "multifactor_expected_return",
    "replicating_weights",
    "arbitrage_profit",
    "smb_proxy",
    "hml_proxy",
]


@dataclass(frozen=True, slots=True)
class MultiFactorResult:
    """A joint regression of excess returns on several factors (Chapter 10, F3).

        R_i = alpha_i + sum_k beta_ik * F_k + e_i

    `betas` is ordered as the caller supplied the factors. Every loading is
    conditional on the others being in the model, which is the whole point --
    dropping a correlated factor will move the remaining loadings, sometimes a
    lot, and that is a property of the model rather than instability in it.
    """

    alpha: float
    betas: dict[str, float]
    r_squared: float
    adj_r_squared: float
    residual_std: float
    standard_errors: dict[str, float] = field(default_factory=dict)
    alpha_stderr: float = float("nan")
    n_obs: int = 0
    periods_per_year: int = TRADING_DAYS_PER_YEAR

    @property
    def alpha_tstat(self) -> float:
        return self.alpha / self.alpha_stderr if self.alpha_stderr else float("nan")

    @property
    def annualized_alpha(self) -> float:
        return (1.0 + self.alpha) ** self.periods_per_year - 1.0

    @property
    def firm_specific_variance_share(self) -> float:
        """1 - R^2, as in Chapter 8 -- but against a richer systematic model.

        Worth comparing to the single-index `scl_*_firm_specific_share`. If the
        multifactor R-squared is much higher, the extra factors are explaining
        variance the single-index model was mislabelling as firm-specific --
        which means the text features were being asked to explain something
        that was systematic all along.
        """
        return 1.0 - self.r_squared

    def tstat(self, factor: str) -> float:
        se = self.standard_errors.get(factor)
        return self.betas[factor] / se if se else float("nan")


def fit_multifactor(
    stock_excess: pd.Series,
    factors: dict[str, pd.Series],
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> MultiFactorResult:
    """Joint OLS of stock excess returns on several factor series (F3).

    All series are inner-joined before fitting, so a day any one factor is
    missing drops out of the whole regression. That is stricter than fitting
    each factor on its own available days, and deliberately so: loadings from
    regressions run on different day-sets are not comparable to each other,
    which defeats the purpose of fitting them jointly.

    `stock_excess` must be excess returns for the same Chapter 8 reason the SCL
    requires them. The factor series are already spreads (SMB, HML) or excess
    market returns; a spread between two risky assets is self-financing and
    needs no further risk-free adjustment -- subtracting r_f from an SMB series
    would be a real error, not a harmless one.

    Solved with `np.linalg.lstsq` rather than the normal equations, which is
    slower and much better conditioned. These factors are correlated by
    construction and `(X'X)^-1` on correlated columns is exactly where a naive
    implementation quietly loses precision.
    """
    if not factors:
        raise ValueError("need at least one factor series")

    joined = pd.concat({"stock": stock_excess, **factors}, axis=1, join="inner").dropna()

    names = list(factors)
    n = len(joined)
    k = len(names)
    # n - k - 1 degrees of freedom, and a regression with none of them left is
    # not underdetermined so much as meaningless: it fits perfectly by
    # construction and reports R-squared 1.0.
    if n < k + 2:
        raise ValueError(f"need at least {k + 2} aligned observations for {k} factors, got {n}")

    y = joined["stock"].to_numpy(float)
    # Leading column of ones is the intercept (alpha).
    X = np.column_stack([np.ones(n)] + [joined[name].to_numpy(float) for name in names])

    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ coefs
    resid = y - fitted

    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    dof = n - k - 1
    resid_var = ss_res / dof
    # Adjusted R-squared, because adding a factor can only raise the raw one.
    # With four correlated proxies against a couple of years of daily bars, the
    # unadjusted figure will flatter every model that adds columns.
    adj_r_squared = 1.0 - (1.0 - r_squared) * (n - 1) / dof if np.isfinite(r_squared) else float("nan")

    try:
        # Standard errors from the diagonal of resid_var * (X'X)^-1. pinv rather
        # than inv so near-collinear factors degrade to a least-norm solution
        # instead of raising -- the loadings are then unreliable, which the
        # t-statistics will show, rather than absent.
        cov = resid_var * np.linalg.pinv(X.T @ X)
        errs = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    except np.linalg.LinAlgError:
        errs = np.full(k + 1, np.nan)

    return MultiFactorResult(
        alpha=float(coefs[0]),
        betas={name: float(c) for name, c in zip(names, coefs[1:])},
        r_squared=float(r_squared),
        adj_r_squared=float(adj_r_squared),
        residual_std=float(np.sqrt(resid_var)),
        standard_errors={name: float(e) for name, e in zip(names, errs[1:])},
        alpha_stderr=float(errs[0]),
        n_obs=n,
        periods_per_year=periods_per_year,
    )


def multifactor_expected_return(
    betas: dict[str, float],
    factor_premia: dict[str, float],
    risk_free_rate: float,
) -> float:
    """Chapter 10, F2: the multifactor SML.

        E(r_P) = r_f + sum_k beta_Pk * [E(r_k) - r_f]

    `factor_premia` are premia -- already net of r_f for factor portfolios, and
    already spreads for SMB/HML. The total risk premium is the sum of the
    compensation for each separate exposure, which is why Example 10.3's
    portfolio can have both betas below 1 and still carry a 9% risk premium.
    That is the chapter's headline point: "aggressive versus defensive" is a
    statement about the sum, not about any single beta.

    Factors present in `betas` but absent from `factor_premia` are treated as
    unpriced (zero premium) rather than raising. A factor can be a genuine
    source of covariation without carrying a risk premium, and that is a
    modelling claim the caller is entitled to make by omission.
    """
    premium = sum(beta * factor_premia.get(name, 0.0) for name, beta in betas.items())
    return risk_free_rate + premium


def replicating_weights(
    target_betas: dict[str, float],
) -> dict[str, float]:
    """Chapter 10, F4: weights of portfolio Q matching a target's factor betas.

    With one pure factor portfolio per factor (each with beta 1 on its own
    factor and 0 on the others), matching betas is trivial: the weight on
    factor portfolio k *is* beta_k, and T-bills absorb the remainder so the
    weights sum to one. Example 10.4's 0.5 / 0.75 / -0.25 falls straight out --
    the negative T-bill weight means borrowing at the risk-free rate.

    Returns the factor weights plus a `risk_free` entry. Trivial arithmetic,
    but writing it down is what makes the arbitrage argument concrete rather
    than a paragraph, and the negative T-bill weight is the part people get
    wrong when doing it by hand.
    """
    weights = dict(target_betas)
    weights["risk_free"] = 1.0 - sum(target_betas.values())
    return weights


def arbitrage_profit(
    replicating_return: float, actual_return: float, dollars: float = 1.0
) -> float:
    """Chapter 10, F4: profit from long $1 of Q, short $1 of A.

        profit = dollars * [E(r_Q) - E(r_A)]

    Riskless and zero-net-investment *only* because Q was built to match A's
    factor betas exactly, so the systematic exposures cancel. Chapter 10's LO3
    is careful that this holds exactly for well-diversified portfolios and only
    approximately for individual securities, which still carry firm-specific
    risk -- meaning a single mispriced stock cannot actually be arbitraged
    risklessly. Chapter 12's Royal Dutch/Shell example is what that limitation
    looks like when it costs someone six years of losses.
    """
    return dollars * (replicating_return - actual_return)


def smb_proxy(small_cap_returns: pd.Series, large_cap_returns: pd.Series) -> pd.Series:
    """A Small-Minus-Big proxy: small-cap index return minus large-cap (F3).

    Built from `^RUT` minus `^GSPC` with the tickers this project already
    fetches. Chapter 11's size effect (F3, a 7.65%/yr spread between the
    smallest and largest NYSE deciles, 1926-2015) is the anomaly this factor
    was constructed to price.

    **Honest about what it is not.** Fama-French's SMB sorts the whole CRSP
    universe into size deciles and takes a genuine long-short of the extremes.
    The Russell 2000 minus the S&P 500 is a spread between two *cap-weighted
    indices whose constituents differ in more than size* -- sector composition
    especially, since small-cap indices carry far more regional banks and far
    fewer megacap technology names. A loading on this series is a loading on
    "small-cap-index-relative performance", which is correlated with SMB and is
    not SMB.
    """
    joined = pd.concat({"small": small_cap_returns, "big": large_cap_returns},
                       axis=1, join="inner").dropna()
    return (joined["small"] - joined["big"]).rename("smb")


def hml_proxy(value_returns: pd.Series, growth_returns: pd.Series) -> pd.Series:
    """A High-Minus-Low (book-to-market) proxy: value index minus growth index.

    Built from a value ETF minus a growth ETF (IWD - IWF by default in
    `config.DEFAULT_FACTOR_TICKERS`). Same caveat as `smb_proxy`, and slightly
    worse: index providers disagree about what "value" means, so the proxy
    inherits one vendor's definition of book-to-market rather than the
    academic sort.

    Kept anyway because the alternative is having no value dimension at all,
    and Chapter 10's argument is precisely that a single market beta cannot see
    this axis. A crude measurement of a real dimension beats a clean
    measurement of nothing -- as long as the docstring says which it is.
    """
    joined = pd.concat({"value": value_returns, "growth": growth_returns},
                       axis=1, join="inner").dropna()
    return (joined["value"] - joined["growth"]).rename("hml")
