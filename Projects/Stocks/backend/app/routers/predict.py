"""POST /api/predict -- the 30-day forecast.

**This endpoint is wired but not trained.** It builds the five datasets, turns
them into a feature row, and calls a model. Until you train one and save it to
`models/`, it returns the statistical baseline instead and says so in the
response body -- `model.trained` is `false` and `model.kind` is `"baseline"`.

That is a deliberate choice over raising a 503. The whole path -- ingest,
features, allocation, response shape -- is exercisable today, so the frontend
can be built against a real response while the model is still being developed.
The response is honest about what it is, and the honesty is machine-readable so
the UI can render it differently rather than relying on someone reading a note.

**The forecast is not just a number.** It returns:

    expected_return   the point estimate
    interval          an uncertainty band -- see the note below
    allocation        Chapter 6's y*: how much to actually hold, given the
                      forecast, its volatility, and the user's risk aversion
    context           beta, R-squared, and the sentiment shift that drove it

The allocation block is what makes the forecast usable. "+2.3% over 30 days" is
not a decision. "+2.3% with 38% annualised volatility, so y* = 0.16 for a
moderately risk-averse investor" is one, and it comes straight from
`finance.portfolio.capital_allocation_line`.

**On the interval.** The baseline interval is the historical volatility scaled
to the horizon -- an honest statement of how much this stock moves in 30 days,
and *not* a confidence interval for the model. Once you have a quantile model
(#ML-10) this should carry real predictive quantiles. The distinction is
recorded in `interval.method` so the UI never presents the former as the latter.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from stocks.config import PROJECT_ROOT
from stocks.features.assemble import build_row
from stocks.finance import portfolio, returns as ret, risk
from stocks.ingest.registry import build_datasets
from stocks.windows import DEFAULT_HORIZON_DAYS, WindowSpec

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["predict"])

MODEL_PATH = PROJECT_ROOT / "models" / "forecaster.joblib"


class PredictRequest(BaseModel):
    symbol: str = Field(..., examples=["AAPL"])
    as_of: date | None = Field(None, description="defaults to today")
    horizon_days: int = Field(DEFAULT_HORIZON_DAYS, ge=1, le=252,
                              description="trading days; 21 is about one month")
    risk_aversion: float = Field(
        portfolio.DEFAULT_RISK_AVERSION, ge=0.5, le=10.0,
        description="Chapter 6 coefficient A. 2 aggressive, 4 typical, 5+ conservative.",
    )


class Interval(BaseModel):
    low: float
    high: float
    confidence: float = Field(..., description="nominal coverage, e.g. 0.80")
    method: str = Field(..., description="historical_volatility | model_quantiles")


class Allocation(BaseModel):
    y_star: float = Field(..., description="Chapter 6 F4 optimal weight in the risky asset")
    y_star_clamped: float = Field(..., description="y* clamped to [0, 1] for display")
    expected_return: float
    std_dev: float
    sharpe_ratio: float
    utility: float
    risk_aversion: float
    is_levered: bool
    is_short: bool
    note: str


class ModelInfo(BaseModel):
    trained: bool
    kind: str = Field(..., description="baseline | trained")
    path: str | None = None
    note: str


class Context(BaseModel):
    beta_sp500: float | None = None
    r_squared_sp500: float | None = None
    firm_specific_share: float | None = None
    annualized_volatility: float | None = None
    sentiment_shift: float | None = None
    attention_ratio: float | None = None
    n_recent_documents: int = 0
    n_baseline_documents: int = 0


class PredictResponse(BaseModel):
    symbol: str
    as_of: date
    horizon_days: int
    horizon_end: date

    expected_return: float = Field(..., description="cumulative log return over the horizon")
    expected_return_pct: float = Field(..., description="the same, as a simple percentage")
    direction: str = Field(..., description="up | down | flat")
    interval: Interval

    allocation: Allocation
    context: Context
    model: ModelInfo

    sources: dict[str, str]
    synthetic: list[str]
    warning: str | None = None


def _load_model():
    """Load the trained pipeline if one has been saved. Returns None otherwise.

    Not cached on purpose during development -- retraining and re-hitting the
    endpoint should pick up the new model without a restart. Add an lru_cache
    here when you deploy.
    """
    if not MODEL_PATH.exists():
        return None
    try:
        import joblib

        return joblib.load(MODEL_PATH)
    except Exception as exc:
        log.warning("failed to load %s (%s); falling back to the baseline", MODEL_PATH, exc)
        return None


@router.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    spec = WindowSpec.for_as_of(req.as_of)

    try:
        bundle = build_datasets(req.symbol.upper(), spec.as_of, spec=spec)
    except Exception as exc:
        raise HTTPException(502, f"dataset build failed: {exc}") from exc

    if bundle.prices_equity.empty:
        raise HTTPException(404, f"no price history for {req.symbol!r}")

    row = build_row(bundle)
    px = bundle.prices_equity["adj_close"].dropna()
    daily = ret.log_returns(px).dropna()

    annual_vol = risk.annualized_volatility(daily.tail(252)) if len(daily) > 20 else float("nan")
    # Volatility scales with the square root of time, so a 21-day sigma is the
    # annual figure divided by sqrt(252/21). Same assumption as
    # `annualized_volatility` -- see the caveat in finance/risk.py.
    horizon_vol = annual_vol * np.sqrt(req.horizon_days / 252.0) if np.isfinite(annual_vol) else float("nan")

    model = _load_model()
    if model is not None:
        try:
            expected = float(model.predict(pd.DataFrame([row]))[0])
            info = ModelInfo(trained=True, kind="trained", path=str(MODEL_PATH),
                             note="prediction from the trained pipeline")
        except Exception as exc:
            log.warning("model prediction failed (%s); using the baseline", exc)
            expected, info = _baseline_forecast(daily, req.horizon_days)
    else:
        expected, info = _baseline_forecast(daily, req.horizon_days)

    # Chapter 6: turn the forecast into a position size. The expected return is
    # a log return over the horizon; annualise it and de-log so it is on the
    # same footing as the annualised volatility the formula expects.
    annual_expected = float(np.expm1(expected * 252.0 / req.horizon_days))
    rf = float(bundle.risk_free.dropna().iloc[-1]) if len(bundle.risk_free.dropna()) else 0.04

    if np.isfinite(annual_vol) and annual_vol > 0:
        alloc = portfolio.capital_allocation_line(annual_expected, annual_vol, rf, req.risk_aversion)
        allocation = Allocation(
            y_star=alloc.y_star,
            # Clamped for display only. The unclamped value is kept alongside
            # because a y* of 2.4 or -0.8 is the model saying something
            # specific, and hiding it would be misleading.
            y_star_clamped=float(np.clip(alloc.y_star, 0.0, 1.0)),
            expected_return=alloc.expected_return,
            std_dev=alloc.std_dev,
            sharpe_ratio=alloc.sharpe_ratio,
            utility=alloc.utility,
            risk_aversion=alloc.risk_aversion,
            is_levered=alloc.is_levered,
            is_short=alloc.is_short,
            note=_allocation_note(alloc),
        )
    else:
        raise HTTPException(422, "not enough price history to compute volatility")

    warning = None
    if bundle.has_synthetic:
        warning = (
            f"{len(bundle.synthetic)} of 5 datasets came from the offline synthetic "
            "fallback -- this forecast is not based on real data."
        )
    elif not info.trained:
        warning = (
            "No trained model found; this is the statistical baseline, not a "
            "machine-learning forecast. Train one with `py run.py train`."
        )

    return PredictResponse(
        symbol=bundle.symbol,
        as_of=bundle.as_of,
        horizon_days=req.horizon_days,
        horizon_end=spec.label_window(req.horizon_days).end,
        expected_return=expected,
        expected_return_pct=float(np.expm1(expected) * 100.0),
        direction="up" if expected > 0.002 else "down" if expected < -0.002 else "flat",
        interval=Interval(
            # 1.2816 is the 80% two-sided normal quantile. See the module
            # docstring: this is a volatility band, not a model confidence
            # interval, and `method` says so.
            low=expected - 1.2816 * horizon_vol,
            high=expected + 1.2816 * horizon_vol,
            confidence=0.80,
            # Always historical for now. It becomes "model_quantiles" once a
            # quantile model exists (#ML-10); until then this field must not
            # claim the band is a model confidence interval, because it is not
            # -- it is just how much this stock moves in 30 days.
            method="historical_volatility",
        ),
        allocation=allocation,
        context=Context(
            beta_sp500=row.get("scl_gspc_beta"),
            r_squared_sp500=row.get("scl_gspc_r_squared"),
            firm_specific_share=row.get("scl_gspc_firm_specific_share"),
            annualized_volatility=annual_vol,
            sentiment_shift=row.get("shift_sentiment_delta"),
            attention_ratio=row.get("shift_attention_ratio"),
            n_recent_documents=len(bundle.news_recent),
            n_baseline_documents=len(bundle.news_baseline),
        ),
        model=info,
        sources=bundle.sources,
        synthetic=sorted(bundle.synthetic),
        warning=warning,
    )


def _baseline_forecast(daily: pd.Series, horizon_days: int) -> tuple[float, ModelInfo]:
    """The no-model fallback: the trailing drift, shrunk hard toward zero.

    Not a real forecast, and the shrinkage says so. The trailing 252-day mean
    return is a famously poor predictor of the next month -- momentum at this
    horizon is weak and unstable -- so extrapolating it naively would produce
    confident nonsense. The 0.25 factor pulls it most of the way to zero, which
    is close to the honest answer in the absence of a model.

    Keep this as the comparison your trained model has to beat (#ML-3). A model
    that cannot beat "roughly zero" is not adding information.
    """
    drift = float(daily.tail(252).mean()) if len(daily) > 60 else 0.0
    expected = drift * horizon_days * 0.25

    return expected, ModelInfo(
        trained=False,
        kind="baseline",
        path=None,
        note=(
            "No trained model on disk. This is a heavily shrunk trailing-drift "
            "estimate -- a placeholder so the endpoint is exercisable, not a "
            "forecast. Train a model with `py run.py train` and save it to "
            "models/forecaster.joblib."
        ),
    )


def _allocation_note(alloc: portfolio.CompleteAllocation) -> str:
    if alloc.is_short:
        return (
            f"y* is negative ({alloc.y_star:.2f}): the forecast risk premium is below the "
            "risk-free rate, so the Chapter 6 optimum is a short position. Displayed clamped to 0."
        )
    if alloc.is_levered:
        return (
            f"y* is {alloc.y_star:.2f}, above 1: the optimum implies borrowing at the risk-free "
            "rate to lever up. Displayed clamped to 1."
        )
    return (
        f"Hold {alloc.y_star:.0%} of the portfolio in this stock and the rest risk-free, "
        f"for an investor with risk aversion A = {alloc.risk_aversion:g}."
    )
