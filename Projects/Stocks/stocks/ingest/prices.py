"""Price providers -- DS1 (equity, 5 years) and DS4 (index, 2 years).

Three implementations behind one protocol:

    YFinanceProvider      no key, the default. Unofficial Yahoo endpoint.
    AlphaVantageProvider  keyed, 25 requests/day free. The fallback.
    SyntheticPriceProvider  no network. Always available, so the pipeline runs
                            on a fresh clone with nothing configured.

One substantive data decision, worth stating because it silently changes every
number downstream: **use adjusted close for returns, raw close for levels.**
Yahoo's `Adj Close` is back-adjusted for splits and dividends, so a return
computed from it is a total return and is continuous across a split. A return
computed from raw close shows a 3-for-1 split as a -67% day, which will be the
largest "move" in your five-year window and will dominate any volatility
feature that sees it. `features/tabular.py` therefore reads `adj_close` for
everything return-shaped, and `close` only where a price level is wanted.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from ..windows import DateWindow
from .base import OHLCV_COLUMNS, BaseProvider, DiskCache, ProviderError, RateLimiter

log = logging.getLogger(__name__)

__all__ = ["YFinanceProvider", "AlphaVantageProvider", "SyntheticPriceProvider"]


def _normalize(frame: pd.DataFrame, source_map: dict[str, str]) -> pd.DataFrame:
    """Coerce a vendor frame to the canonical OHLCV schema.

    Missing columns are filled rather than raised on -- indices have no volume,
    and some providers omit `adj_close` for instruments that never split. The
    adj_close fallback to close is the important one: without it every index in
    DS4 would come back with a NaN return column.
    """
    out = pd.DataFrame(index=pd.to_datetime(frame.index))
    for canonical, vendor in source_map.items():
        if vendor in frame.columns:
            out[canonical] = pd.to_numeric(frame[vendor], errors="coerce")

    if "adj_close" not in out.columns and "close" in out.columns:
        out["adj_close"] = out["close"]
    for col in OHLCV_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan

    out = out[OHLCV_COLUMNS].sort_index()
    out.index.name = "date"
    return out


class YFinanceProvider(BaseProvider):
    """Yahoo Finance via the `yfinance` package. Default for DS1 and DS4.

    No key, generous history, and it covers indices (`^GSPC`, `^IXIC`) with the
    same call as equities, which is why it serves both price datasets.

    It is an unofficial endpoint scraped from Yahoo's web API, so it is not a
    contract: it changes shape without notice and rate-limits aggressively when
    swept. Both are survivable because of the disk cache -- a training sweep
    hits Yahoo once per distinct window and reads Parquet thereafter.
    """

    name = "yfinance"

    def __init__(self, cache: DiskCache | None = None) -> None:
        super().__init__(cache)
        self._limiter = RateLimiter(0.6)

    def available(self) -> bool:
        try:
            import yfinance  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch_prices(self, symbol: str, window: DateWindow) -> pd.DataFrame:
        if self.cache is not None:
            hit = self.cache.get_frame(self.name, "prices", symbol, window)
            if hit is not None:
                return hit

        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderError("yfinance is not installed") from exc

        self._limiter.wait()
        try:
            raw = yf.Ticker(symbol).history(
                start=window.start.isoformat(),
                end=window.end.isoformat(),
                interval="1d",
                auto_adjust=False,   # we want BOTH close and adj_close; see module docstring
                actions=False,
            )
        except Exception as exc:
            raise ProviderError(f"yfinance failed for {symbol}: {exc}") from exc

        if raw is None or raw.empty:
            raise ProviderError(f"yfinance returned no rows for {symbol} over {window}")

        frame = _normalize(raw, {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "adj_close": "Adj Close", "volume": "Volume",
        })
        frame = self.clip_frame(frame, window)

        if self.cache is not None:
            self.cache.put_frame(self.name, "prices", symbol, window, frame)
        return frame


class AlphaVantageProvider(BaseProvider):
    """Alpha Vantage `TIME_SERIES_DAILY_ADJUSTED`. Keyed fallback.

    Free tier is 25 requests per day, which is not enough for a training sweep
    but is plenty for serving the web app, where one ticker is one request and
    the cache absorbs repeats. Positioned as the fallback for exactly that
    reason: it keeps the app alive when Yahoo rate-limits, without pretending
    it could carry the training load.
    """

    name = "alphavantage"
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None, cache: DiskCache | None = None) -> None:
        super().__init__(cache)
        self.api_key = api_key
        self._limiter = RateLimiter(12.0)  # 5 requests/minute on the free tier

    def available(self) -> bool:
        return bool(self.api_key)

    def fetch_prices(self, symbol: str, window: DateWindow) -> pd.DataFrame:
        if self.cache is not None:
            hit = self.cache.get_frame(self.name, "prices", symbol, window)
            if hit is not None:
                return hit
        if not self.api_key:
            raise ProviderError("ALPHAVANTAGE_API_KEY is not set")

        import requests

        self._limiter.wait()
        try:
            resp = requests.get(
                self.BASE_URL,
                params={
                    "function": "TIME_SERIES_DAILY_ADJUSTED",
                    "symbol": symbol,
                    # `full` returns 20+ years; `compact` only 100 bars, which
                    # is not enough for even the shortest window here.
                    "outputsize": "full",
                    "apikey": self.api_key,
                },
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise ProviderError(f"alphavantage request failed for {symbol}: {exc}") from exc

        # Alpha Vantage signals quota exhaustion with HTTP 200 and a "Note" or
        # "Information" key rather than an error status, so this has to be
        # checked explicitly or you get an empty frame and no explanation.
        if "Note" in payload or "Information" in payload:
            raise ProviderError(f"alphavantage rate limit: {payload.get('Note') or payload.get('Information')}")
        series = payload.get("Time Series (Daily)")
        if not series:
            raise ProviderError(f"alphavantage returned no series for {symbol}: {list(payload)[:3]}")

        raw = pd.DataFrame.from_dict(series, orient="index")
        frame = _normalize(raw, {
            "open": "1. open", "high": "2. high", "low": "3. low",
            "close": "4. close", "adj_close": "5. adjusted close", "volume": "6. volume",
        })
        frame = self.clip_frame(frame, window)

        if self.cache is not None:
            self.cache.put_frame(self.name, "prices", symbol, window, frame)
        return frame


class SyntheticPriceProvider(BaseProvider):
    """Deterministic fake prices. No network, always available.

    This is not a toy. It exists so that:

    - a fresh clone runs `py run.py demo` end to end with no keys and no
      internet, which is the difference between a repo you can evaluate in two
      minutes and one you cannot;
    - the test suite is fast and offline;
    - you can develop the ML side on a laptop with no connection.

    The generator is a geometric Brownian motion with a fixed per-symbol seed,
    so the same symbol always produces the same series. Volatility clustering is
    added via a slow-moving multiplier because constant-volatility GBM makes
    the risk features in `finance/risk.py` look far better behaved than real
    data ever is -- and a pipeline tuned against well-behaved noise will
    disappoint on the real thing.

    What it deliberately does NOT contain is any relationship between the price
    series and the synthetic text. A model trained on synthetic data should
    score near zero. If it scores well, your pipeline is leaking, and that is a
    useful thing for this provider to be able to tell you.
    """

    name = "synthetic"

    def __init__(self, cache: DiskCache | None = None, annual_drift: float = 0.08,
                 annual_vol: float = 0.28) -> None:
        super().__init__(cache)
        self.drift = annual_drift
        self.vol = annual_vol

    def available(self) -> bool:
        return True

    def fetch_prices(self, symbol: str, window: DateWindow) -> pd.DataFrame:
        # Business-day index, so the bar count matches a real series closely
        # enough that the 252-day annualisation constants stay honest.
        idx = pd.bdate_range(window.start, window.end - timedelta(days=1))
        n = len(idx)
        if n == 0:
            return pd.DataFrame(columns=OHLCV_COLUMNS, index=pd.DatetimeIndex([], name="date"))

        rng = np.random.default_rng(abs(hash(symbol.upper())) % (2**32))

        dt = 1.0 / 252.0
        # Slow sinusoidal volatility multiplier, phase-shifted per symbol.
        phase = rng.uniform(0, 2 * np.pi)
        vol_mult = 1.0 + 0.45 * np.sin(np.linspace(0, 6 * np.pi, n) + phase)
        sigma = self.vol * vol_mult

        shocks = rng.standard_normal(n) * sigma * np.sqrt(dt)
        log_path = np.cumsum((self.drift - 0.5 * sigma**2) * dt + shocks)

        start_price = float(rng.uniform(20, 400))
        close = start_price * np.exp(log_path)

        intraday = np.abs(rng.standard_normal(n)) * sigma * np.sqrt(dt) * close
        open_ = close - rng.standard_normal(n) * intraday * 0.5

        frame = pd.DataFrame(
            {
                "open": open_,
                "high": np.maximum(open_, close) + intraday * 0.5,
                "low": np.minimum(open_, close) - intraday * 0.5,
                "close": close,
                # No synthetic corporate actions, so adjusted == raw.
                "adj_close": close,
                "volume": rng.integers(5e5, 5e7, n).astype(float),
            },
            index=pd.DatetimeIndex(idx, name="date"),
        )[OHLCV_COLUMNS]

        return self.clip_frame(frame, window)
