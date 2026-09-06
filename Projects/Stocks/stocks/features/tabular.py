"""Tabular features from DS1 (equity prices) and DS4 (index prices).

Everything here reduces a window of price history to a **single row** of
numbers describing the state of the stock as of that window's end. One as-of
date, one row. The walk-forward sweep calls this once per as-of and stacks the
results into the training panel.

Two rules run through the whole module.

**Only backward-looking windows.** Every rolling statistic is computed with
`.rolling(...)` and read at the last row. Nothing centred, nothing
interpolated, no `.shift(-n)` anywhere except in the target. This is enforced
by construction rather than checked, because a centred moving average is
invisible in a feature table and inflates backtest scores by a lot.

**Returns come from `adj_close`.** Split- and dividend-adjusted, so a 3-for-1
split is not read as a -67% day. See `ingest/prices.py`.

The features are grouped by what they measure, and the groups matter because
`features/assemble.py` prefixes them and `pipeline.py` can select on the
prefix -- letting you ask "do the text features add anything over the price
features alone?", which is the first question worth answering about this
project.

    ret_*    returns over various lookbacks
    vol_*    realised volatility, at several horizons
    risk_*   Chapter 5/6 risk measures: Sharpe, VaR, drawdown, moments
    scl_*    Chapter 8 single-index regression against each index
    tech_*   ordinary technical descriptors: RSI, moving-average distance
    vol_liq_* volume and liquidity
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..finance import index_model, returns as ret, risk
from ..finance.returns import TRADING_DAYS_PER_YEAR

log = logging.getLogger(__name__)

__all__ = ["price_features", "index_features", "relative_features", "LOOKBACKS"]

# Lookbacks in trading days: ~1w, ~1m, ~3m, ~6m, ~1y, ~2y.
# Deliberately spaced roughly geometrically. Adjacent lookbacks are highly
# correlated, so 5/10/15/20 would add columns without adding information and
# would make any linear model's coefficients unstable.
LOOKBACKS = (5, 21, 63, 126, 252, 504)


def _last(series: pd.Series) -> float:
    """Last finite value, or NaN. Used to read a rolling series at the as-of edge."""
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else float("nan")


def price_features(prices: pd.DataFrame, risk_free: pd.Series | None = None,
                   prefix: str = "eq") -> dict[str, float]:
    """Reduce one equity price window (DS1) to a feature row.

    `risk_free` is an annual decimal rate indexed by date, from FRED. When it
    is absent the Sharpe ratios come back computed against zero, which
    overstates them by roughly the T-bill rate -- so the caller is warned
    rather than left to notice.
    """
    if prices.empty or "adj_close" not in prices:
        return {}

    px = prices["adj_close"].dropna()
    if len(px) < 2:
        return {}

    daily = ret.log_returns(px).dropna()
    simple = ret.simple_returns(px).dropna()

    rf_annual = 0.0
    if risk_free is not None and not risk_free.empty:
        rf_annual = float(risk_free.dropna().iloc[-1]) if len(risk_free.dropna()) else 0.0
    else:
        log.debug("no risk-free series supplied; Sharpe ratios computed against zero")

    f: dict[str, float] = {}

    # --- returns over each lookback --------------------------------------
    for lb in LOOKBACKS:
        if len(px) > lb:
            # Log return over the window, so these add across lookbacks the way
            # the target does.
            f[f"{prefix}_ret_{lb}d"] = float(np.log(px.iloc[-1] / px.iloc[-1 - lb]))
        else:
            f[f"{prefix}_ret_{lb}d"] = np.nan

    # --- realised volatility ---------------------------------------------
    for lb in LOOKBACKS:
        window = daily.tail(lb)
        f[f"{prefix}_vol_{lb}d"] = (
            risk.annualized_volatility(window) if len(window) >= max(5, lb // 4) else np.nan
        )

    # The volatility term structure. A ratio above 1 means short-horizon vol is
    # elevated against the long-run level -- the stock is in a stressed regime
    # right now. This is often more informative than either level alone, and a
    # tree model would have to spend splits to discover it.
    short_vol, long_vol = f.get(f"{prefix}_vol_21d"), f.get(f"{prefix}_vol_252d")
    f[f"{prefix}_vol_ratio_21_252"] = (
        short_vol / long_vol if short_vol and long_vol and long_vol > 0 else np.nan
    )

    # --- Chapter 5/6 risk measures ---------------------------------------
    f[f"{prefix}_risk_sharpe_252d"] = risk.sharpe_ratio(daily.tail(252), rf_annual)
    f[f"{prefix}_risk_sharpe_63d"] = risk.sharpe_ratio(daily.tail(63), rf_annual)
    f[f"{prefix}_risk_var_normal_1pct"] = risk.value_at_risk_normal(daily.tail(252))
    f[f"{prefix}_risk_var_hist_1pct"] = risk.value_at_risk_historical(daily.tail(252))
    # The gap between normal and empirical VaR is a direct read on tail
    # fatness: large and negative means the normal assumption is badly
    # optimistic for this name.
    f[f"{prefix}_risk_var_gap"] = (
        f[f"{prefix}_risk_var_hist_1pct"] - f[f"{prefix}_risk_var_normal_1pct"]
    )
    f[f"{prefix}_risk_expected_shortfall"] = risk.expected_shortfall(daily.tail(252))
    f[f"{prefix}_risk_max_drawdown_252d"] = risk.max_drawdown(px.tail(252))
    f[f"{prefix}_risk_max_drawdown_full"] = risk.max_drawdown(px)
    f[f"{prefix}_risk_skew_252d"] = risk.skewness(daily.tail(252))
    f[f"{prefix}_risk_kurtosis_252d"] = risk.excess_kurtosis(daily.tail(252))

    # Arithmetic minus geometric mean. Chapter 5 notes this gap is roughly half
    # the variance for near-normal returns, so a large divergence is itself a
    # non-normality signal, computed almost for free.
    arith = ret.arithmetic_mean_return(simple.tail(252))
    geo = ret.geometric_mean_return(simple.tail(252))
    f[f"{prefix}_risk_arith_geo_gap"] = arith - geo if np.isfinite(arith) and np.isfinite(geo) else np.nan

    # --- technicals -------------------------------------------------------
    for lb in (21, 63, 126, 252):
        if len(px) > lb:
            sma = px.rolling(lb).mean()
            # Distance from the moving average as a fraction, not the average
            # itself -- a raw SMA is a price level, which is not comparable
            # across tickers and would make the model memorise price scale.
            f[f"{prefix}_tech_sma_dist_{lb}d"] = float(px.iloc[-1] / _last(sma) - 1.0)
        else:
            f[f"{prefix}_tech_sma_dist_{lb}d"] = np.nan

    f[f"{prefix}_tech_rsi_14d"] = _rsi(px, 14)
    f[f"{prefix}_tech_pct_from_52w_high"] = _pct_from_extreme(px, 252, high=True)
    f[f"{prefix}_tech_pct_from_52w_low"] = _pct_from_extreme(px, 252, high=False)

    # --- volume / liquidity ----------------------------------------------
    if "volume" in prices and prices["volume"].notna().any():
        vol = prices["volume"].dropna()
        recent, baseline = vol.tail(21).mean(), vol.tail(252).mean()
        # Relative volume, not absolute -- absolute share volume is a proxy for
        # market cap, which is not what we are trying to measure.
        f[f"{prefix}_vol_liq_rel_volume_21d"] = (
            float(recent / baseline) if baseline > 0 else np.nan
        )
        f[f"{prefix}_vol_liq_log_dollar_volume"] = (
            float(np.log1p(recent * px.iloc[-1])) if recent > 0 else np.nan
        )

    return f


def index_features(indices: dict[str, pd.DataFrame], risk_free: pd.Series | None = None) -> dict[str, float]:
    """Reduce DS4 to a feature row: one block per index.

    The same `price_features` treatment applied to each index, prefixed by a
    cleaned ticker. `^VIX` gets included and is worth keeping even though it is
    not really a price series -- its *level* is a direct measure of expected
    market volatility over the next 30 days, which is precisely this project's
    forecast horizon.
    """
    out: dict[str, float] = {}
    for ticker, frame in indices.items():
        key = ticker.lstrip("^").lower()
        out.update(price_features(frame, risk_free, prefix=f"idx_{key}"))
    return out


def relative_features(
    equity: pd.DataFrame,
    indices: dict[str, pd.DataFrame],
    risk_free: pd.Series | None = None,
) -> dict[str, float]:
    """Chapter 8: the stock regressed on each index. The core of DS1 x DS4.

    This is where the two tabular datasets stop being separate. For each index
    we fit the Security Characteristic Line and emit alpha, beta, R-square,
    residual volatility, and the information ratio.

    Why these features are the most valuable in the module: R-square says what
    fraction of the stock's variance the market explains, and 1 - R-square is
    the share left for firm-specific news. A name at R-square 0.7 is mostly a
    market instrument, and DS2/DS3 have little room to add. A name at 0.15 is
    mostly its own story, and the text datasets are where the signal must be.
    Handing the model that ratio explicitly means it can learn to weight the
    text block differently by regime, rather than having to infer it.

    `scl_beta_delta` is emitted for the same reason `rolling_beta` exists: a
    beta that is moving tells you the name's sensitivity is changing, which
    shifts predictive weight between the datasets.
    """
    out: dict[str, float] = {}
    if equity.empty or "adj_close" not in equity:
        return out

    stock_ret = ret.log_returns(equity["adj_close"]).dropna()
    if len(stock_ret) < 30:
        return out

    rf_daily = _daily_risk_free(risk_free, stock_ret.index)
    stock_excess = (stock_ret - rf_daily).dropna()

    for ticker, frame in indices.items():
        if frame.empty or "adj_close" not in frame:
            continue
        # The VIX is a volatility index, not an investable asset; regressing a
        # stock on it produces a "beta" with no Chapter 8 interpretation. Its
        # level is used as a feature in index_features instead.
        if ticker == "^VIX":
            continue

        key = ticker.lstrip("^").lower()
        mkt_ret = ret.log_returns(frame["adj_close"]).dropna()
        mkt_excess = (mkt_ret - _daily_risk_free(risk_free, mkt_ret.index)).dropna()

        try:
            scl = index_model.fit_scl(stock_excess, mkt_excess)
        except ValueError as exc:
            log.debug("SCL fit failed for %s vs %s: %s", "stock", ticker, exc)
            continue

        out[f"scl_{key}_alpha"] = scl.alpha
        out[f"scl_{key}_alpha_annual"] = scl.annualized_alpha
        out[f"scl_{key}_alpha_tstat"] = scl.alpha_tstat
        out[f"scl_{key}_beta"] = scl.beta
        out[f"scl_{key}_beta_tstat"] = scl.beta_tstat
        out[f"scl_{key}_r_squared"] = scl.r_squared
        out[f"scl_{key}_correlation"] = scl.correlation
        out[f"scl_{key}_residual_std"] = scl.residual_std
        out[f"scl_{key}_information_ratio"] = scl.information_ratio
        # 1 - R^2: how much room the text datasets have to explain anything.
        out[f"scl_{key}_firm_specific_share"] = scl.firm_specific_variance_share

        # Recent vs. older beta -- is this name becoming more macro-sensitive?
        try:
            rb = index_model.rolling_beta(stock_excess, mkt_excess, window=126).dropna()
            if len(rb) > 126:
                out[f"scl_{key}_beta_now"] = float(rb.iloc[-1])
                out[f"scl_{key}_beta_delta"] = float(rb.iloc[-1] - rb.iloc[-126])
        except Exception as exc:
            log.debug("rolling beta failed for %s: %s", ticker, exc)

    return out


# --- helpers -------------------------------------------------------------


def _daily_risk_free(risk_free: pd.Series | None, index: pd.Index) -> pd.Series:
    """De-annualize the risk-free rate and align it to a return index.

    FRED quotes an annual rate; daily excess returns need a daily one. The
    conversion is geometric ((1+r)^(1/252) - 1), not r/252, to stay consistent
    with `finance.risk.sharpe_ratio`, which does the same.

    Reindexed with forward-fill: the rate is quoted on business days and the
    return index may include days FRED does not cover.
    """
    if risk_free is None or risk_free.empty:
        return pd.Series(0.0, index=index)

    annual = risk_free.reindex(index, method="ffill").fillna(0.0)
    return (1.0 + annual) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0


def _rsi(prices: pd.Series, period: int = 14) -> float:
    """Wilder's Relative Strength Index, read at the last bar.

    Included because it is bounded in [0, 100] and mean-reverting, which makes
    it a genuinely different kind of feature from the unbounded return and
    volatility columns around it -- linear models in particular benefit from
    having at least one such input.
    """
    if len(prices) < period + 1:
        return float("nan")
    delta = prices.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    last_loss = _last(loss)
    if last_loss == 0:
        return 100.0
    rs = _last(gain) / last_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _pct_from_extreme(prices: pd.Series, lookback: int, high: bool) -> float:
    """Distance from the rolling high or low, as a fraction.

    Scale-free, so it is comparable across a $12 stock and a $900 one -- which
    a raw high or low would not be.
    """
    window = prices.tail(lookback)
    if len(window) < 2:
        return float("nan")
    extreme = window.max() if high else window.min()
    return float(prices.iloc[-1] / extreme - 1.0) if extreme > 0 else float("nan")
