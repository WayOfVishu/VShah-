"""The Capital Asset Pricing Model -- Bodie/Kane/Marcus 9CE, Chapter 9.

Chapter 8 gave this project a *historical* alpha: regress the stock on the
index over the past five years and read the intercept. That number describes
what already happened.

Chapter 9 gives it a *forward* alpha, and that is a different and more useful
object. The SML says what return a stock ought to offer given its beta:

    E(r_i) = r_f + beta_i * [E(r_M) - r_f]

Anything a forecaster predicts above that line is alpha (F3). So the moment
this project produces a forecast -- from `pipeline.py`, or from the shrunk
drift baseline in `/api/predict` -- that forecast can be scored against the
line rather than reported as a bare percentage.

**Why that reframing matters more than it sounds.** "+2.3% over 30 days" is
not interpretable without knowing what the stock's risk entitles it to. A
high-beta name in a rising market *should* return more than 2.3%; predicting
2.3% for it is a bearish call wearing a bullish sign. Running the forecast
through F3 turns it into "+1.4% above fair", which is both the honest
statement and exactly the input Chapter 8's `treynor_black_weights` wants.

**On the market risk premium.** Every function here takes it as an argument
rather than hard-coding a number, because it is not observable and reasonable
estimates over the last century range from roughly 3% to 8% depending on the
sample and the averaging method. `MARKET_RISK_PREMIUM_DEFAULT` exists so
callers that genuinely have no view have something to pass, and it is set to
the textbook's own working figure -- but treat any alpha computed from a
default MRP as a sketch, not a valuation.

`realised_market_risk_premium` estimates one from index history instead, then
shrinks it hard toward that default and floors it at a small positive value.
Read its docstring before using the raw sample mean anywhere: one year of index
returns estimates the premium with a standard error several times the premium
itself, and the unshrunk estimate comes out negative often enough to invert the
SML -- which scores every high-beta name backwards.

Nothing here is estimated from data. These are the accounting identities of
the model; `index_model.fit_scl` supplies the beta they consume, and
`event_study.py` (Chapter 11) reuses the same line to define abnormal returns.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

__all__ = [
    "MARKET_RISK_PREMIUM_DEFAULT",
    "SMLVerdict",
    "beta_from_covariance",
    "sml_expected_return",
    "sml_alpha",
    "zero_beta_expected_return",
    "required_return",
    "fair_profit",
    "evaluate_against_sml",
    "realised_market_risk_premium",
    "MRP_SHRINKAGE_DAYS",
    "MRP_FLOOR",
]

# The market risk premium used in Chapter 9's own worked examples (Example 9.1
# states it directly as 8%). Deliberately a named constant rather than a
# literal so that every place it leaks into a default is greppable.
MARKET_RISK_PREMIUM_DEFAULT = 0.08


def beta_from_covariance(covariance: float, market_variance: float) -> float:
    """Chapter 9, F1: beta_i = Cov(r_i, r_M) / sigma_M^2.

    The definitional form. `index_model.fit_scl` estimates the same quantity as
    a regression slope, which is the same number by construction -- this exists
    for the case where you have a covariance matrix rather than two series, and
    to make the identity checkable.
    """
    if market_variance <= 0:
        return float("nan")
    return covariance / market_variance


def sml_expected_return(
    beta: float,
    risk_free_rate: float,
    market_risk_premium: float = MARKET_RISK_PREMIUM_DEFAULT,
) -> float:
    """Chapter 9, F1: the SML's "fair" expected return for a given beta.

        E(r_i) = r_f + beta_i * [E(r_M) - r_f]

    Note what is *absent*: total volatility. A speculative biotech with 90%
    annualised volatility and a beta of 0.4 is entitled to less return than a
    utility with 25% volatility and a beta of 1.1, because the biotech's risk
    is mostly diversifiable and diversifiable risk earns no compensation. This
    is the single most counter-intuitive claim in the chapter and it is the
    reason `eq_vol_*` features must never be read as expected-return features.

    `market_risk_premium` is E(r_M) - r_f, already netted. Passing a total
    market return here instead is the mistake this parameter name exists to
    prevent -- it produces a plausible number that is wrong by r_f.
    """
    return risk_free_rate + beta * market_risk_premium


def sml_alpha(
    forecast_return: float,
    beta: float,
    risk_free_rate: float,
    market_risk_premium: float = MARKET_RISK_PREMIUM_DEFAULT,
) -> float:
    """Chapter 9, F3: alpha as the vertical distance from the SML.

        alpha_i = E(r_i)_actual - [r_f + beta_i * (E(r_M) - r_f)]

    Positive alpha means the security plots above the line: it offers more than
    fair compensation for its systematic risk, so it looks underpriced.
    Negative means the reverse.

    All three rate arguments must be on the **same time basis** -- all annual,
    or all over the same horizon. Mixing an annualised forecast with a
    one-month risk-free rate is the error that makes this function produce
    confident nonsense, and it cannot be detected from the inputs.
    """
    return forecast_return - sml_expected_return(beta, risk_free_rate, market_risk_premium)


def zero_beta_expected_return(
    beta: float, zero_beta_return: float, market_return: float
) -> float:
    """Chapter 9, F2: the zero-beta CAPM, for when borrowing is restricted.

        E(r_i) = E(r_Z) + beta_i * [E(r_M) - E(r_Z)]

    Fischer Black's result: if investors cannot borrow freely at the risk-free
    rate, the risk-free asset is replaced by portfolio Z, the zero-beta
    companion of M. Because E(r_Z) > r_f, the resulting SML is *flatter* --
    risk-tolerant investors who cannot lever up instead crowd into high-beta
    stocks, bidding their prices up and compressing their risk premiums.

    Practical consequence for this project: a flatter empirical SML is one of
    the standard explanations for why high-beta names have historically
    underdelivered against the simple CAPM's prediction. If a model trained
    here shows systematically negative alpha on high-beta names, this is the
    first thing to check before concluding the model found something.
    """
    return zero_beta_return + beta * (market_return - zero_beta_return)


def required_return(
    beta: float,
    risk_free_rate: float,
    market_risk_premium: float = MARKET_RISK_PREMIUM_DEFAULT,
) -> float:
    """Chapter 9, F4: the CAPM hurdle rate.

    Numerically identical to `sml_expected_return` -- same formula, different
    question. The SML asks "what should this security return?"; the hurdle rate
    asks "what must this project clear to be worth funding?", and a regulator
    asks "what profit may this utility fairly earn?". Kept as a separate name
    because code that computes a hurdle rate should read as computing a hurdle
    rate.
    """
    return sml_expected_return(beta, risk_free_rate, market_risk_premium)


def fair_profit(
    invested_capital: float,
    beta: float,
    risk_free_rate: float,
    market_risk_premium: float = MARKET_RISK_PREMIUM_DEFAULT,
) -> float:
    """Chapter 9, F4: Fair Profit = Required Return * Invested Capital.

    Example 9.1's regulated-utility calculation. Not used by the forecasting
    pipeline -- there is no invested-capital figure in any of the datasets --
    but it is one of the four industry applications the chapter names, it is
    two lines, and the worked example pins it.
    """
    return invested_capital * required_return(beta, risk_free_rate, market_risk_premium)


@dataclass(frozen=True, slots=True)
class SMLVerdict:
    """A forecast placed against the security market line.

    This is what `/api/predict` reports as its `valuation` block. The point of
    bundling rather than returning a bare alpha is that alpha is meaningless
    without the beta and MRP that produced it, and a response that carries the
    number but not its inputs invites it being quoted out of context.
    """

    forecast_return: float       # what the model predicts, annualised
    fair_return: float           # what the SML says the beta entitles it to
    alpha: float                 # forecast - fair
    beta: float
    risk_free_rate: float
    market_risk_premium: float

    @property
    def is_underpriced(self) -> bool:
        """Positive alpha: plots above the SML."""
        return self.alpha > 0

    @property
    def verdict(self) -> str:
        """A word for the UI. The band is intentionally wide.

        Alphas inside +/-1% annualised are not a signal at this project's
        precision -- the market risk premium alone is uncertain by several
        percentage points, which swamps them. Calling those "fairly priced" is
        the honest label, and it keeps the frontend from rendering noise as a
        recommendation.
        """
        if not np.isfinite(self.alpha):
            return "unknown"
        if self.alpha > 0.01:
            return "underpriced"
        if self.alpha < -0.01:
            return "overpriced"
        return "fairly_priced"

    @property
    def note(self) -> str:
        if not np.isfinite(self.alpha):
            return "Beta could not be estimated, so no SML comparison is available."
        return (
            f"Beta {self.beta:.2f} entitles this stock to {self.fair_return:.2%} a year "
            f"(risk-free {self.risk_free_rate:.2%} plus {self.beta:.2f} x "
            f"{self.market_risk_premium:.2%}). The forecast is {self.forecast_return:.2%}, "
            f"an alpha of {self.alpha:+.2%}."
        )


def evaluate_against_sml(
    forecast_return: float,
    beta: float,
    risk_free_rate: float,
    market_risk_premium: float = MARKET_RISK_PREMIUM_DEFAULT,
) -> SMLVerdict:
    """Score a forecast against the SML. Chapter 9, F1 and F3 together.

    The bridge between the ML side and the finance side of this project, and
    the reason Chapter 9 is worth implementing at all: `pipeline.py` produces a
    number, and this turns it into a claim about mispricing that Chapter 8's
    Treynor-Black weights can consume directly.

    `forecast_return` must be **annualised and de-logged** -- a simple annual
    rate, matching `risk_free_rate`. The pipeline's native output is a 21-day
    log return, so the caller converts; see `/api/predict`, which does the
    `np.expm1(expected * 252 / horizon)` step before calling here.
    """
    fair = sml_expected_return(beta, risk_free_rate, market_risk_premium)
    return SMLVerdict(
        forecast_return=forecast_return,
        fair_return=fair,
        alpha=forecast_return - fair,
        beta=beta,
        risk_free_rate=risk_free_rate,
        market_risk_premium=market_risk_premium,
    )


# Shrinkage half-weight, in trading days. At a sample of exactly this length
# the estimate below is half realised and half prior; at 252 days it is about
# 17% realised. Five years is chosen because that is roughly the span over
# which a mean equity return begins to be worth anything at all as an estimate.
MRP_SHRINKAGE_DAYS = 1260

# The floor applied to the shrunk estimate. Not a fudge: under CAPM equilibrium
# the market risk premium *must* be positive, because a negative one would mean
# investors are paying to bear undiversifiable risk and nobody would hold the
# market portfolio at all -- which is LO1's argument running backwards. The
# premium is an *expectation*; a catastrophic realised year (2008 came in near
# -40%) is evidence about the sample, not about the forward premium.
#
# Shrinkage alone does not guarantee positivity. At one year of data the sample
# carries ~17% weight, so a realised premium below about -40% still drags the
# blend under zero -- and 2008 was close enough to that to matter. Without the
# floor the SML would slope downward for those rows, scoring every high-beta
# name as entitled to *less* return than a low-beta one, which is not a bearish
# reading but an inverted model.
MRP_FLOOR = 0.01


def realised_market_risk_premium(
    market_returns: pd.Series,
    risk_free_rate: float,
    periods_per_year: int = 252,
    *,
    prior: float = MARKET_RISK_PREMIUM_DEFAULT,
    shrink: bool = True,
) -> float:
    """Estimate the MRP from realised index returns, shrunk toward a prior.

    Uses the arithmetic mean, not the geometric: Chapter 5 is explicit that the
    arithmetic mean is the right estimator for a *forward* expectation, and the
    SML is a statement about expected returns. The geometric mean answers a
    different question -- what the index actually delivered -- and would bias
    the premium down by roughly half the variance.

    **Why the raw sample mean is not usable on its own, and the shrinkage is
    not decoration.** An equity index has annualised volatility around 18%, so
    one year of daily returns estimates its mean with a standard error of about
    18 percentage points. The quantity being estimated is around 5%. The
    estimator's noise is therefore roughly three times the signal, and the
    estimate routinely comes out *negative* -- which is not a bear-market
    reading, it is the CAPM's central premise inverted, and it makes the SML
    slope the wrong way. Every alpha computed from it then flips sign for
    high-beta names.

    So the sample mean is blended toward `prior` with weight n / (n + 1260):

        252 days  ->  17% sample, 83% prior
        1260 days ->  50/50
        2520 days ->  67% sample

    which lets a genuinely sustained regime move the estimate while leaving a
    single noisy year almost untouched.

    The result is then floored at `MRP_FLOOR`. Shrinkage narrows the sign
    problem but does not close it -- at one year of data a realised premium
    below roughly -40% still drags the blend negative, and 2008 was close
    enough to that to matter. The floor is theory, not tidying: a negative
    *expected* premium would mean nobody holds the market portfolio, which
    contradicts the equilibrium the whole chapter is built on.

    Pass `shrink=False` for the raw, unfloored sample mean -- appropriate when
    you are deliberately measuring the estimate's instability (running it over
    several windows and comparing the spread) rather than trying to price
    something with it.
    """
    clean = pd.Series(market_returns).dropna()
    if len(clean) < 2:
        return float("nan")

    sample = float(clean.mean() * periods_per_year - risk_free_rate)
    if not shrink:
        return sample

    weight = len(clean) / (len(clean) + MRP_SHRINKAGE_DAYS)
    blended = weight * sample + (1.0 - weight) * prior
    return max(MRP_FLOOR, blended)
