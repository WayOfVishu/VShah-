"""Macro providers -- DS5, the political and global-economic backdrop (6 months).

DS5 has two halves, and they are different in kind:

    text     political/economic news, from GDELT with macro queries
    numeric  interest rates, inflation, unemployment, VIX, from FRED

Both are here because the numeric half is not optional. `finance/` computes
excess returns throughout -- the Chapter 8 SCL regression is *defined* on
excess returns -- and excess returns need a risk-free rate. That rate is FRED's
DGS3MO. Without it, `fit_scl` would be regressing total returns on total
returns, which the chapter specifically warns produces a beta that confuses
market-level moves with market-surprise moves.

So `FredProvider.risk_free_series` is load-bearing, not a feature. When FRED is
unavailable, `constant_risk_free` supplies a flat fallback and the code that
uses it says so out loud rather than silently assuming zero.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from ..config import DEFAULT_FRED_SERIES
from ..windows import DateWindow
from .base import BaseProvider, DiskCache, Document, ProviderError, RateLimiter
from .news import GdeltProvider, SyntheticTextProvider

log = logging.getLogger(__name__)

__all__ = [
    "FredProvider",
    "MacroTextProvider",
    "SyntheticMacroProvider",
    "constant_risk_free",
    "MACRO_QUERIES",
]

# The DS5 text queries. Broad on purpose: DS5's job is the shared backdrop that
# moves every stock together (the Chapter 8 "common macro factor"), not
# anything specific to the ticker being forecast. Adding company-specific terms
# here would duplicate DS2/DS3 and blur the systematic/firm-specific split that
# `index_model.py` is built to preserve.
MACRO_QUERIES = (
    "federal reserve interest rates",
    "inflation consumer prices",
    "recession economic outlook",
    "trade tariffs policy",
    "geopolitical conflict markets",
    "unemployment labor market",
)


class FredProvider(BaseProvider):
    """Federal Reserve Economic Data. Keyed, free, no meaningful rate limit.

    Supplies the numeric half of DS5 and, critically, the risk-free rate.
    Register at https://fredaccount.stlouisfed.org/apikeys -- it takes a minute
    and the key is free.
    """

    name = "fred"
    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str | None, cache: DiskCache | None = None) -> None:
        super().__init__(cache)
        self.api_key = api_key
        self._limiter = RateLimiter(0.3)

    def available(self) -> bool:
        return bool(self.api_key)

    def fetch_series(self, series_id: str, window: DateWindow) -> pd.Series:
        """One FRED series over the window, forward-filled to daily.

        Forward-filling is right for these series and wrong for many others.
        CPI is published monthly; on 15 March the most recent *known* CPI is
        February's, and forward-filling reproduces exactly that. Interpolating
        instead would place a value between February and March readings on a
        date when March's number did not yet exist -- lookahead leakage,
        smuggled in as a convenience.
        """
        if self.cache is not None:
            hit = self.cache.get_frame(self.name, "series", series_id, window)
            if hit is not None:
                return hit.iloc[:, 0]
        if not self.api_key:
            raise ProviderError("FRED_API_KEY is not set")

        import requests

        self._limiter.wait()
        try:
            resp = requests.get(
                self.BASE_URL,
                params={
                    "series_id": series_id,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "observation_start": window.start.isoformat(),
                    "observation_end": window.end.isoformat(),
                },
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise ProviderError(f"fred request failed for {series_id}: {exc}") from exc

        obs = payload.get("observations", [])
        if not obs:
            raise ProviderError(f"fred returned no observations for {series_id}")

        frame = pd.DataFrame(obs)
        # FRED marks missing observations with a literal "." rather than null.
        frame["value"] = pd.to_numeric(frame["value"].replace(".", np.nan), errors="coerce")
        series = pd.Series(
            frame["value"].to_numpy(),
            index=pd.DatetimeIndex(pd.to_datetime(frame["date"]), name="date"),
            name=series_id,
        ).ffill()

        if self.cache is not None:
            self.cache.put_frame(self.name, "series", series_id, window, series.to_frame())
        return series

    def fetch_panel(self, window: DateWindow,
                    series_ids: tuple[str, ...] = DEFAULT_FRED_SERIES) -> pd.DataFrame:
        """All configured series as one daily frame. A failed series is skipped."""
        cols = {}
        for sid in series_ids:
            try:
                cols[sid] = self.fetch_series(sid, window)
            except ProviderError as exc:
                log.warning("skipping FRED series %s: %s", sid, exc)
        if not cols:
            raise ProviderError("no FRED series could be fetched")
        return pd.DataFrame(cols).ffill()

    def risk_free_series(self, window: DateWindow, series_id: str = "DGS3MO") -> pd.Series:
        """The annual risk-free rate as a decimal, daily.

        FRED quotes DGS3MO in percent (4.35 means 4.35%), and every function in
        `finance/` expects decimals. The /100 here is the single place that
        conversion happens, which is why it is a named method rather than left
        to callers to remember.
        """
        return (self.fetch_series(series_id, window) / 100.0).rename("risk_free")


class MacroTextProvider(BaseProvider):
    """The text half of DS5: political and economic news via GDELT.

    **Built to be cheap, because DS5 is where a naive implementation blows up
    the runtime budget.** The obvious approach -- run each of the six
    `MACRO_QUERIES` separately over 14-day chunks -- costs 6 x 13 = 78
    rate-limited calls for a single six-month window, which is several minutes
    for one bundle and makes a walk-forward sweep of a few hundred bundles
    completely infeasible.

    Two changes bring that down to about six calls:

    1. **One OR query instead of six.** GDELT accepts boolean queries, so the
       six macro topics go out as a single disjunction. The results are the
       union anyway -- they were being pooled and deduplicated on return.
    2. **Coarser chunks.** Chunking exists to stop GDELT's 250-record cap from
       concentrating results in a few days, and stock news needs fortnightly
       resolution for the DS2-vs-DS3 comparison to mean anything. DS5 does not:
       it is a slow-moving backdrop, and monthly slices sample it perfectly
       well.

    Results are still deduplicated by URL. A single Fed decision is covered by
    hundreds of outlets, and without dedup the corpus becomes a measure of how
    many wire services copied one story.
    """

    name = "macro_text"
    kind = "macro"
    CHUNK_DAYS = 30

    def __init__(self, gdelt: GdeltProvider | None = None, cache: DiskCache | None = None) -> None:
        super().__init__(cache)
        self.gdelt = gdelt or GdeltProvider(cache=cache, chunk_days=self.CHUNK_DAYS)

    def available(self) -> bool:
        return self.gdelt.available()

    @staticmethod
    def combined_query(queries: tuple[str, ...] = MACRO_QUERIES) -> str:
        """The six macro topics as one GDELT boolean disjunction.

        GDELT quotes phrases and ORs them inside parentheses. Built here rather
        than inlined so the query is testable without a network call.
        """
        return "(" + " OR ".join(f'"{q}"' for q in queries) + ")"

    def fetch_documents(self, query: str, window: DateWindow, limit: int = 500) -> list[Document]:
        """`query` is ignored -- DS5 is ticker-independent by design.

        The parameter is kept so this satisfies the same `TextProvider`
        protocol as the others and the registry can treat all text slots
        uniformly. See the module docstring for why DS5 must not be
        ticker-specific.

        Being ticker-independent is also what makes DS5 nearly free across a
        multi-symbol sweep: every symbol at a given as-of date requests the
        same window, so the first one pays for the call and the rest hit the
        disk cache.
        """
        if self.cache is not None:
            hit = self.cache.get_documents(self.name, self.kind, "macro", window)
            if hit is not None:
                return hit

        seen: set[str] = set()
        docs: list[Document] = []

        try:
            for doc in self.gdelt.fetch_documents(self.combined_query(), window, limit=limit):
                key = doc.url or doc.title
                if key in seen:
                    continue
                seen.add(key)
                doc.kind = "macro"
                docs.append(doc)
        except Exception as exc:
            log.warning("macro text fetch failed: %s", exc)

        docs.sort(key=lambda d: d.published)
        docs = self.clip_documents(docs, window)[:limit]
        if self.cache is not None:
            self.cache.put_documents(self.name, self.kind, "macro", window, docs)
        return docs


class SyntheticMacroProvider(BaseProvider):
    """Offline DS5 -- synthetic macro text plus a plausible numeric panel."""

    name = "synthetic"
    kind = "macro"

    def __init__(self, cache: DiskCache | None = None) -> None:
        super().__init__(cache)
        self._text = SyntheticTextProvider(cache)

    def available(self) -> bool:
        return True

    def fetch_documents(self, query: str, window: DateWindow, limit: int = 500) -> list[Document]:
        docs = self._text.fetch_documents("the economy", window, limit)
        for d in docs:
            d.kind = "macro"
        return docs

    def fetch_panel(self, window: DateWindow,
                    series_ids: tuple[str, ...] = DEFAULT_FRED_SERIES) -> pd.DataFrame:
        idx = pd.bdate_range(window.start, window.end - timedelta(days=1))
        rng = np.random.default_rng(20260905)
        # Random walks around plausible levels -- enough to exercise the
        # feature code's shape handling without pretending to be real macro.
        levels = {"DGS3MO": 4.5, "DGS10": 4.2, "T10Y2Y": -0.3,
                  "CPIAUCSL": 310.0, "UNRATE": 4.1, "VIXCLS": 16.0}
        return pd.DataFrame(
            {sid: levels.get(sid, 1.0) + np.cumsum(rng.normal(0, 0.02, len(idx)))
             for sid in series_ids},
            index=pd.DatetimeIndex(idx, name="date"),
        )

    def risk_free_series(self, window: DateWindow, series_id: str = "DGS3MO") -> pd.Series:
        return (self.fetch_panel(window)[series_id] / 100.0).rename("risk_free")


def constant_risk_free(window: DateWindow, annual_rate: float = 0.04) -> pd.Series:
    """A flat risk-free rate, for when FRED is unavailable.

    4% is roughly the 2024-2026 3-month T-bill level. A constant is wrong --
    the rate moved from near zero to over 5% inside the five-year DS1 window,
    and holding it flat distorts excess returns across that whole stretch --
    but it is wrong in a stable, documented way, whereas assuming zero silently
    turns every excess return into a total return and quietly breaks the
    Chapter 8 regression.

    Callers should log when they fall back to this. `pipeline.py` does.
    """
    idx = pd.bdate_range(window.start, window.end - timedelta(days=1))
    return pd.Series(annual_rate, index=pd.DatetimeIndex(idx, name="date"), name="risk_free")
