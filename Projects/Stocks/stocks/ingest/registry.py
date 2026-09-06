"""Provider selection and the one function the rest of the project calls.

`build_datasets(symbol, as_of)` returns all five datasets for one as-of date.
That is the entire public surface of the ingest layer -- features, pipeline,
CLI, and API all go through it, and none of them know which vendor answered.

Selection is a preference-ordered fallback per slot. For each dataset the
registry walks its candidate list, takes the first provider whose `available()`
is true, and drops to synthetic if none are. So:

    with no keys and internet   yfinance + GDELT      -- real data, free
    with no keys and no internet  synthetic           -- still runs
    with keys                   the keyed provider where it is better

Running with nothing configured is the intended first experience, not a
degraded one. `py run.py providers` prints the resolved table so you always
know which of those three worlds you are in -- a synthetic run that is mistaken
for a real one is the most expensive confusion this project can produce.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from ..config import DEFAULT_INDEX_TICKERS, Settings, get_settings
from ..windows import Dataset, WindowSpec
from .base import DiskCache, Document, ProviderError
from .macro import (
    FredProvider,
    MacroTextProvider,
    SyntheticMacroProvider,
    constant_risk_free,
)
from .news import GdeltProvider, NewsApiProvider, RedditProvider, SyntheticTextProvider
from .prices import AlphaVantageProvider, SyntheticPriceProvider, YFinanceProvider

log = logging.getLogger(__name__)

__all__ = ["Registry", "DatasetBundle", "build_datasets"]


@dataclass(slots=True)
class DatasetBundle:
    """All five datasets for one (symbol, as_of), plus the provenance to read them.

    `sources` and `synthetic` are not bookkeeping. A bundle whose prices are
    real and whose news is synthetic will train and will score, and the score
    will be meaningless. Carrying provenance in the bundle means `evaluate.py`
    can refuse to report a result built on fabricated inputs, rather than
    leaving that to whoever reads the number.
    """

    symbol: str
    as_of: date
    spec: WindowSpec

    prices_equity: pd.DataFrame
    prices_index: dict[str, pd.DataFrame]
    news_baseline: list[Document]
    news_recent: list[Document]
    macro_text: list[Document]
    macro_panel: pd.DataFrame
    risk_free: pd.Series

    sources: dict[str, str] = field(default_factory=dict)
    synthetic: set[str] = field(default_factory=set)

    @property
    def is_fully_synthetic(self) -> bool:
        return len(self.synthetic) == len(Dataset)

    @property
    def has_synthetic(self) -> bool:
        return bool(self.synthetic)

    def summary(self) -> str:
        rows = [f"{self.symbol} as of {self.as_of.isoformat()}"]
        counts = {
            "prices_equity": f"{len(self.prices_equity):>5} bars",
            "prices_index": f"{sum(len(f) for f in self.prices_index.values()):>5} bars "
                            f"over {len(self.prices_index)} indices",
            "news_baseline": f"{len(self.news_baseline):>5} docs",
            "news_recent": f"{len(self.news_recent):>5} docs",
            "macro": f"{len(self.macro_text):>5} docs + {self.macro_panel.shape[1]} series",
        }
        for key, count in counts.items():
            flag = "  [SYNTHETIC]" if key in self.synthetic else ""
            rows.append(f"  {key:<14} {count:<32} via {self.sources.get(key, '?')}{flag}")
        return "\n".join(rows)


class Registry:
    """Resolves each dataset slot to a provider, once, at construction."""

    def __init__(self, settings: Settings | None = None, *, force_synthetic: bool = False) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()
        self.cache = DiskCache(self.settings.raw_dir, self.settings.cache_ttl_hours)
        # STOCKS_FORCE_SYNTHETIC lets the whole app -- including the web
        # frontend, which constructs its own Registry per request -- run
        # offline. Useful for demos and for developing the UI without waiting
        # on rate-limited providers. It logs a warning every time, because a
        # synthetic run mistaken for a real one is the most expensive
        # confusion this project can produce.
        self.force_synthetic = force_synthetic or self.settings.force_synthetic
        if self.force_synthetic:
            # Name the actual source: "STOCKS_FORCE_SYNTHETIC is on" is
            # confusing when the caller passed the flag instead, and sends
            # people hunting through .env for a variable that is not set.
            source = "--synthetic" if force_synthetic else "STOCKS_FORCE_SYNTHETIC"
            log.warning("%s is set -- all data is generated, not real", source)

        self._synthetic_prices = SyntheticPriceProvider(self.cache)
        self._synthetic_text = SyntheticTextProvider(self.cache)
        self._synthetic_macro = SyntheticMacroProvider(self.cache)

        self.prices = self._pick([
            YFinanceProvider(self.cache),
            AlphaVantageProvider(self.settings.alphavantage_key, self.cache),
        ], self._synthetic_prices)

        # GDELT first for news: it is the only free source that reaches back
        # far enough to build DS2 at all. See ingest/news.py.
        self.news = self._pick([
            GdeltProvider(self.cache),
            NewsApiProvider(self.settings.newsapi_key, self.cache,
                            self.settings.newsapi_allow_nonproduction),
        ], self._synthetic_text)

        # Community is genuinely optional -- there is no keyless substitute for
        # Reddit, so this stays None rather than silently faking forum posts.
        reddit = RedditProvider(
            self.settings.reddit_client_id, self.settings.reddit_client_secret,
            self.settings.reddit_user_agent, self.cache,
        )
        self.community = reddit if (reddit.available() and not force_synthetic) else None

        self.macro_text = self._pick([MacroTextProvider(cache=self.cache)], self._synthetic_macro)
        self.macro_numeric = self._pick([FredProvider(self.settings.fred_key, self.cache)],
                                        self._synthetic_macro)

    def _pick(self, candidates: list[Any], fallback: Any) -> Any:
        if self.force_synthetic:
            return fallback
        for provider in candidates:
            if provider.available():
                return provider
            log.debug("provider %s unavailable, trying next", provider.name)
        log.warning("no live provider available; falling back to %s", fallback.name)
        return fallback

    def describe(self) -> str:
        rows = ["resolved providers:"]
        for slot, provider in [
            ("prices (DS1, DS4)", self.prices),
            ("news (DS2, DS3)", self.news),
            ("community (DS3)", self.community),
            ("macro text (DS5)", self.macro_text),
            ("macro numeric (DS5)", self.macro_numeric),
        ]:
            name = provider.name if provider is not None else "-- none (optional) --"
            flag = "  [SYNTHETIC]" if name == "synthetic" else ""
            rows.append(f"  {slot:<22} {name}{flag}")
        return "\n".join(rows)

    # --- per-dataset fetches ---------------------------------------------

    def _fetch_prices(self, symbol: str, window, bundle_key: str,
                      sources: dict, synthetic: set) -> pd.DataFrame:
        try:
            frame = self.prices.fetch_prices(symbol, window)
            sources[bundle_key] = self.prices.name
            if self.prices.name == "synthetic":
                synthetic.add(bundle_key)
            return frame
        except ProviderError as exc:
            log.warning("%s failed for %s (%s); using synthetic", self.prices.name, symbol, exc)
            sources[bundle_key] = "synthetic (fallback)"
            synthetic.add(bundle_key)
            return self._synthetic_prices.fetch_prices(symbol, window)

    def _fetch_text(self, query: str, window, bundle_key: str,
                    sources: dict, synthetic: set, limit: int = 500) -> list[Document]:
        try:
            docs = self.news.fetch_documents(query, window, limit)
            source = self.news.name
        except ProviderError as exc:
            log.warning("%s failed for %r (%s); using synthetic", self.news.name, query, exc)
            docs, source = self._synthetic_text.fetch_documents(query, window, limit), "synthetic (fallback)"
            synthetic.add(bundle_key)

        if source == "synthetic":
            synthetic.add(bundle_key)

        # Community posts only join the recent window -- Reddit's search API
        # cannot reach back a year, so asking it to fill DS2 returns a handful
        # of unrepresentative posts. See RedditProvider's docstring.
        if self.community is not None and bundle_key == "news_recent":
            try:
                community = self.community.fetch_documents(query, window, limit // 2)
                docs = docs + community
                source = f"{source} + reddit"
            except Exception as exc:
                log.warning("reddit fetch failed (%s); continuing with news only", exc)

        sources[bundle_key] = source
        return docs


def build_datasets(
    symbol: str,
    as_of: date | None = None,
    *,
    registry: Registry | None = None,
    spec: WindowSpec | None = None,
    index_tickers: tuple[str, ...] = DEFAULT_INDEX_TICKERS,
    news_limit: int = 500,
) -> DatasetBundle:
    """Build all five datasets for one symbol at one as-of date.

    The unit of work for both training (called once per as-of in the sweep) and
    inference (called once, with as_of = today). Everything is fetched through
    the cache, so the second call for an overlapping window is nearly free --
    which is what makes the training sweep tractable.

    Failures degrade rather than raise. A dead news provider yields an empty
    DS2 and a recorded source of "synthetic (fallback)"; it does not abort a
    sweep two hours in. The provenance lands in `bundle.synthetic` so the
    degradation is visible downstream instead of being inferred from a
    suspiciously round score.
    """
    registry = registry or Registry()
    spec = spec or WindowSpec.for_as_of(as_of)
    symbol = symbol.upper()

    sources: dict[str, str] = {}
    synthetic: set[str] = set()

    equity = registry._fetch_prices(symbol, spec.prices_equity, "prices_equity", sources, synthetic)

    indices: dict[str, pd.DataFrame] = {}
    for ticker in index_tickers:
        try:
            indices[ticker] = registry._fetch_prices(
                ticker, spec.prices_index, "prices_index", sources, synthetic
            )
        except Exception as exc:
            log.warning("index %s failed: %s", ticker, exc)

    baseline = registry._fetch_text(symbol, spec.news_baseline, "news_baseline",
                                    sources, synthetic, news_limit)
    recent = registry._fetch_text(symbol, spec.news_recent, "news_recent",
                                  sources, synthetic, news_limit)

    try:
        macro_docs = registry.macro_text.fetch_documents(symbol, spec.macro, news_limit)
        sources["macro"] = registry.macro_text.name
        if registry.macro_text.name == "synthetic":
            synthetic.add("macro")
    except Exception as exc:
        log.warning("macro text failed (%s); using synthetic", exc)
        macro_docs = registry._synthetic_macro.fetch_documents(symbol, spec.macro, news_limit)
        sources["macro"] = "synthetic (fallback)"
        synthetic.add("macro")

    # The risk-free rate spans the widest window, since excess returns are
    # needed across all of DS1, not just the 6-month macro window.
    rf_window = spec.prices_equity
    try:
        macro_panel = registry.macro_numeric.fetch_panel(spec.macro)
        risk_free = registry.macro_numeric.risk_free_series(rf_window)
    except Exception as exc:
        log.warning("FRED unavailable (%s); risk-free rate falls back to a flat 4%%", exc)
        macro_panel = registry._synthetic_macro.fetch_panel(spec.macro)
        risk_free = constant_risk_free(rf_window)

    return DatasetBundle(
        symbol=symbol,
        as_of=spec.as_of,
        spec=spec,
        prices_equity=equity,
        prices_index=indices,
        news_baseline=baseline,
        news_recent=recent,
        macro_text=macro_docs,
        macro_panel=macro_panel,
        risk_free=risk_free,
        sources=sources,
        synthetic=synthetic,
    )
