"""Tabular features from DS1 (equity prices) and DS2 (index and factor prices).

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

    ret_*     returns over various lookbacks
    vol_*     realised volatility, at several horizons
    risk_*    Chapter 5/6 risk measures: Sharpe, VaR, drawdown, moments
    scl_*     Chapter 8 single-index regression against each index
    capm_*    Chapter 9 SML fair return and the gap to realised return
    ff_*      Chapter 10 joint multifactor loadings against market/SMB/HML
    evt_*     Chapter 11 abnormal returns, CAR, momentum and reversal
    tech_*    Chapter 12 technicals: RSI, MA distance, crossovers, relative strength
    vol_liq_* volume and liquidity

**On the Chapter 11 features specifically.** `evt_momentum_12_1` and
`evt_reversal_24_36m` are not redundant with `eq_ret_252d` and `eq_ret_504d`,
even though they read the same price series. The raw lookbacks are total
returns over a span; the anomaly features are the *published specifications* of
two documented effects, which deliberately exclude the most recent month
(because one-month reversal points the opposite way to twelve-month momentum
and mixing them attenuates both). Emitting both lets the ablation say whether
the specification mattered or whether the model could find it either way.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import DEFAULT_FACTOR_TICKERS, DEFAULT_MARKET_RISK_PREMIUM
from ..finance import (
    capm,
    event_study,
    index_model,
    multifactor,
    returns as ret,
    risk,
    technical,
)
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
                   prefix: str = "eq", *, anomalies: bool = True) -> dict[str, float]:
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

    # Chapter 12's actual moving-average signal. The `sma_dist` features above
    # give the distance; these give the crossing, which is the event a
    # technician acts on. A stock that has sat above its 50-day average for
    # eight months is not a breakout, and distance alone cannot say so.
    f[f"{prefix}_tech_ma_cross_50d"] = technical.ma_crossover_state(px, 50)
    f[f"{prefix}_tech_ma_cross_200d"] = technical.ma_crossover_state(px, 200)
    f[f"{prefix}_tech_ma_cross_age_50d"] = technical.ma_crossover_age(px, 50)

    # --- Chapter 11 anomalies ---------------------------------------------
    # The published specifications, not raw lookbacks. See the module docstring
    # on why these are not duplicates of `ret_252d` and `ret_504d`.
    #
    # Stocks only. LO4 is explicit that broad market indexes show only weak
    # serial correlation while individual stocks and sectors show pronounced
    # momentum and reversal -- these are cross-sectional equity anomalies, and
    # an index's own momentum is not the thing the literature documents.
    #
    # There is a mechanical reason too: DS2 index frames span two years
    # (`WindowSpec.index_years`) and `long_horizon_reversal` needs three, so
    # emitting it here produced a column that was NaN in every row of every
    # panel. An all-NaN feature is not missing data, it is a dead column that
    # the imputer then warns about once per fit.
    if anomalies:
        f[f"{prefix}_evt_momentum_12_1"] = event_study.momentum_12_1(px)
        f[f"{prefix}_evt_reversal_24_36m"] = event_study.long_horizon_reversal(px)

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
    """Reduce DS2 to a feature row: one block per index.

    The same `price_features` treatment applied to each index, prefixed by a
    cleaned ticker. `^VIX` gets included and is worth keeping even though it is
    not really a price series -- its *level* is a direct measure of expected
    market volatility over the next 30 days, which is precisely this project's
    forecast horizon.
    """
    out: dict[str, float] = {}
    for ticker, frame in indices.items():
        key = ticker.lstrip("^").lower()
        # `anomalies=False`: momentum and reversal are stock-level effects, and
        # index frames span only two years anyway -- see `price_features`.
        out.update(price_features(frame, risk_free, prefix=f"idx_{key}", anomalies=False))
    return out


def relative_features(
    equity: pd.DataFrame,
    indices: dict[str, pd.DataFrame],
    risk_free: pd.Series | None = None,
    *,
    benchmark: str = "^GSPC",
    factor_tickers: tuple[str, ...] = DEFAULT_FACTOR_TICKERS,
) -> dict[str, float]:
    """Chapters 8-12: the stock measured against the indices. The core of DS1 x DS2.

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

    Four chapters now land in this one function, because all four are
    statements about a stock relative to a market and they share the same
    aligned excess-return series -- computing that series once and reusing it
    is both cheaper and safer than four call sites each doing their own join.

        Ch 8   `scl_*`   one univariate SCL per index
        Ch 9   `capm_*`  the SML fair return implied by the fitted beta, and
                         the gap between it and what the stock actually did
        Ch 10  `ff_*`    one *joint* regression on market + SMB + HML proxies
        Ch 11  `evt_*`   abnormal returns and CAR against the market model
        Ch 12  `tech_rs_*` relative strength against the benchmark

    **The Chapter 9 features are the subtle ones.** `capm_alpha_realised` is
    not the same object as `scl_gspc_alpha`, even though both are called alpha.
    The SCL alpha is a regression intercept -- the average daily excess return
    unexplained by the market, over five years. `capm_alpha_realised` compares
    the stock's *trailing annual return* against the SML's fair return for its
    beta, using a market risk premium estimated from the index itself. The
    first is an average of residuals; the second is a single statement about
    whether the last year over- or under-delivered against what the beta
    entitled it to. They correlate but answer different questions, and the
    second is the one that has a forward analogue -- which is what
    `/api/predict` reports once the model produces a forecast.
    """
    out: dict[str, float] = {}
    if equity.empty or "adj_close" not in equity:
        return out

    stock_ret = ret.log_returns(equity["adj_close"]).dropna()
    if len(stock_ret) < 30:
        return out

    rf_daily = _daily_risk_free(risk_free, stock_ret.index)
    stock_excess = (stock_ret - rf_daily).dropna()

    # Log returns per index, computed once. Four chapters read these, and each
    # recomputing them would be both slower and a chance for two blocks to
    # disagree about which days were dropped.
    index_returns: dict[str, pd.Series] = {}
    for ticker, frame in indices.items():
        if not frame.empty and "adj_close" in frame:
            index_returns[ticker] = ret.log_returns(frame["adj_close"]).dropna()

    for ticker, frame in indices.items():
        if frame.empty or "adj_close" not in frame:
            continue
        # The VIX is a volatility index, not an investable asset; regressing a
        # stock on it produces a "beta" with no Chapter 8 interpretation. Its
        # level is used as a feature in index_features instead.
        if ticker == "^VIX":
            continue
        # The factor-proxy ETFs are regressed jointly below, not one at a time.
        # A univariate SCL against a value ETF would report a beta near 1 for
        # almost any large-cap name and say nothing.
        if ticker in factor_tickers:
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

        # --- Chapter 9: the SML, per index ---------------------------------
        out.update(_capm_features(equity, frame, scl.beta, risk_free, key))

        # --- Chapter 11: abnormal returns against this index ---------------
        out.update(_event_features(stock_ret, mkt_ret, key))

        # --- Chapter 12: relative strength ---------------------------------
        if ticker == benchmark:
            bench_px = frame["adj_close"].dropna()
            equity_px = equity["adj_close"].dropna()
            out["tech_rs_63d"] = technical.relative_strength(equity_px, bench_px, 63)
            out["tech_rs_252d"] = technical.relative_strength(equity_px, bench_px, 252)
            out["tech_rs_trend_63d"] = technical.relative_strength_trend(
                equity_px, bench_px, 63)

    # --- Chapter 10: one joint multifactor regression ----------------------
    out.update(_multifactor_features(stock_excess, index_returns, risk_free,
                                     benchmark, factor_tickers))

    return out


def _capm_features(
    equity: pd.DataFrame,
    index_frame: pd.DataFrame,
    beta: float,
    risk_free: pd.Series | None,
    key: str,
) -> dict[str, float]:
    """Chapter 9: the SML fair return, and how far the stock sat from it.

    Every rate here is annual, which is the trap this function exists to close.
    `capm.sml_alpha` cannot detect a caller mixing an annualised return with a
    daily risk-free rate -- it returns a number that is wrong by two orders of
    magnitude and looks entirely plausible. Doing the annualisation in one
    place means no other call site has to get it right.
    """
    out: dict[str, float] = {}
    if not np.isfinite(beta):
        return out

    idx_px = index_frame["adj_close"].dropna()
    px = equity["adj_close"].dropna()
    if len(idx_px) < 253 or len(px) < 253:
        return out

    rf_annual = _last(risk_free) / 100.0 if risk_free is not None and len(risk_free) else 0.04
    if not np.isfinite(rf_annual):
        rf_annual = 0.04

    # The premium estimated from this index's *full* available history, not
    # just the trailing year, and shrunk toward the textbook 8%. Chapter 9 is
    # explicit that the MRP is not observable, and the sample mean of one year
    # of index returns has a standard error several times the premium it is
    # estimating -- see `capm.realised_market_risk_premium`. Using every bar on
    # hand and shrinking is what keeps this from being a noise generator that
    # occasionally inverts the SML.
    mrp = capm.realised_market_risk_premium(
        ret.log_returns(idx_px).dropna(), rf_annual)
    used_default = not np.isfinite(mrp)
    if used_default:
        mrp = DEFAULT_MARKET_RISK_PREMIUM

    fair = capm.sml_expected_return(beta, rf_annual, mrp)
    realised = float(np.expm1(np.log(px.iloc[-1] / px.iloc[-253])))

    out[f"capm_{key}_fair_return"] = fair
    out[f"capm_{key}_market_risk_premium"] = mrp
    # Realised annual return minus the SML's fair return. Positive means the
    # stock over-delivered against what its beta entitled it to over the past
    # year. This is backward-looking; the forward version is what
    # `/api/predict` computes from the model's forecast.
    out[f"capm_{key}_alpha_realised"] = capm.sml_alpha(realised, beta, rf_annual, mrp)
    out[f"capm_{key}_mrp_is_default"] = 1.0 if used_default else 0.0
    return out


def _event_features(stock_ret: pd.Series, mkt_ret: pd.Series, key: str) -> dict[str, float]:
    """Chapter 11: cumulative abnormal return over the most recent month.

    Follows LO3's methodological rule literally. The market model's alpha and
    beta are fitted on an **estimation window that ends before the event window
    begins**, so the benchmark cannot be contaminated by the abnormal
    performance it is meant to measure. Fitting on the whole series and then
    measuring its tail -- the obvious shortcut -- biases every CAR toward zero,
    because the residuals it measures are the same residuals it minimised.

    Note this fits on **total** returns, not excess: Chapter 11's market model
    is `r = alpha + beta*r_M + e`, where Chapter 8's SCL is the excess-return
    form. See `event_study.abnormal_return` on why the two alphas differ.
    """
    out: dict[str, float] = {}
    joined = pd.concat({"stock": stock_ret, "market": mkt_ret}, axis=1, join="inner").dropna()

    event_days = 21
    estimation_days = 252
    if len(joined) < estimation_days + event_days + 10:
        return out

    estimation = joined.iloc[-(estimation_days + event_days):-event_days]
    event = joined.iloc[-event_days:]

    try:
        # `fit_scl` is an OLS of one series on another; passing total returns
        # gives the Chapter 11 market model rather than the Chapter 8 SCL. Same
        # arithmetic, different convention, and the docstring above says which.
        market_model = index_model.fit_scl(estimation["stock"], estimation["market"])
    except ValueError as exc:
        log.debug("market model fit failed for %s: %s", key, exc)
        return out

    window = event_study.cumulative_abnormal_return(
        event["stock"], event["market"], market_model.alpha, market_model.beta)

    out[f"evt_{key}_car_21d"] = window.car
    out[f"evt_{key}_car_tstat"] = window.tstat
    out[f"evt_{key}_abnormal_std"] = window.std_abnormal
    return out


def _multifactor_features(
    stock_excess: pd.Series,
    index_returns: dict[str, pd.Series],
    risk_free: pd.Series | None,
    benchmark: str,
    factor_tickers: tuple[str, ...],
) -> dict[str, float]:
    """Chapter 10: one joint regression on market, SMB proxy, and HML proxy.

    Emitted only when every factor is available. Partial factor sets are
    deliberately not backfilled with a two-factor fit, because a loading from a
    two-factor model is not comparable to the same-named loading from a
    three-factor one -- and a panel where `ff_beta_market` silently means
    different things on different rows is worse than one where it is absent.
    """
    out: dict[str, float] = {}

    market = index_returns.get(benchmark)
    small = index_returns.get("^RUT")
    value_ticker, growth_ticker = (tuple(factor_tickers) + ("", ""))[:2]
    value, growth = index_returns.get(value_ticker), index_returns.get(growth_ticker)

    if market is None or small is None or value is None or growth is None:
        return out

    rf_daily = _daily_risk_free(risk_free, market.index)
    factors = {
        "market": (market - rf_daily).dropna(),
        # SMB and HML are already long-short spreads: self-financing, so
        # subtracting r_f from them would be a genuine error rather than a
        # harmless one. See `multifactor.fit_multifactor`.
        "smb": multifactor.smb_proxy(small, market),
        "hml": multifactor.hml_proxy(value, growth),
    }

    try:
        fit = multifactor.fit_multifactor(stock_excess, factors)
    except (ValueError, np.linalg.LinAlgError) as exc:
        log.debug("multifactor fit failed: %s", exc)
        return out

    for name, beta in fit.betas.items():
        out[f"ff_beta_{name}"] = beta
        out[f"ff_tstat_{name}"] = fit.tstat(name)

    out["ff_alpha"] = fit.alpha
    out["ff_alpha_annual"] = fit.annualized_alpha
    out["ff_r_squared"] = fit.r_squared
    out["ff_adj_r_squared"] = fit.adj_r_squared
    out["ff_residual_std"] = fit.residual_std
    # Compare against `scl_gspc_firm_specific_share`. If the multifactor model
    # explains much more, the single-index model was mislabelling systematic
    # variance as firm-specific -- meaning DS3 was being asked to explain moves
    # that were never company-specific to begin with.
    out["ff_firm_specific_share"] = fit.firm_specific_variance_share
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
