"""Provider protocol, disk cache, and the shared record types.

Two provider shapes, one for each kind of dataset:

    PriceProvider  -> a DataFrame indexed by date  (DS1, DS2)
    TextProvider   -> a list of Document           (DS2, DS3, DS5)

Everything downstream is written against these two protocols and never against
a specific vendor, so swapping Yahoo for Alpha Vantage or GDELT for NewsAPI is
a registry edit rather than a rewrite of the feature code.

**The cache is not an optimisation.** A walk-forward sweep over four years of
weekly as-of dates asks for the same underlying price history two hundred
times. Without a cache you would be rate-limited into uselessness within
minutes, and every provider here is either free-tier-capped or an unofficial
endpoint that will start refusing you if hammered. The cache is what makes the
training sweep possible at all, which is why it lives in the base class rather
than being left to each provider.

Cache keys deliberately include the *window*, not the as-of date. Two as-of
dates a week apart request overlapping price ranges, and keying on the window
means the second request is a hit whenever the range is genuinely identical and
a miss when it is not -- rather than caching per-as-of and storing near-duplicate
copies of the same five years of bars.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable

import pandas as pd

from ..windows import DateWindow

log = logging.getLogger(__name__)

__all__ = [
    "Document",
    "PriceProvider",
    "TextProvider",
    "DiskCache",
    "ProviderError",
    "RateLimiter",
    "OHLCV_COLUMNS",
]

# The canonical price schema. Every PriceProvider returns exactly these columns
# in this order, whatever the vendor calls them, so `features/tabular.py` never
# has to branch on which provider produced a frame.
OHLCV_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


class ProviderError(RuntimeError):
    """A provider could not serve a request. Registry catches this and falls back."""


@dataclass(slots=True)
class Document:
    """One piece of text: a news article, a forum post, a macro brief.

    `published` is a date, not a datetime, because window membership is decided
    at day resolution and carrying timezone-aware timestamps through the
    pipeline invites the class of bug where an article published at 23:00 UTC
    on the as-of date lands inside a window it should not be in.

    `source` and `kind` are kept because DS3 pools professional news with
    community chatter, and those two have very different reliability. Keeping
    the provenance means `features/text.py` can weight them differently -- or
    you can discover they should not be pooled at all.
    """

    doc_id: str
    published: date
    title: str
    text: str
    source: str
    kind: str = "news"            # news | community | macro
    url: str | None = None
    score: float | None = None    # upvotes, engagement, or provider relevance
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def combined_text(self) -> str:
        """Title plus body.

        Titles are short and dense with sentiment -- headlines are written to
        carry the take -- so dropping them in favour of body text loses signal.
        Repeating the title once weights it slightly, which is the intent.
        """
        return f"{self.title}\n\n{self.text}".strip()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["published"] = self.published.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Document":
        d = dict(d)
        d["published"] = date.fromisoformat(d["published"])
        return cls(**d)


@runtime_checkable
class PriceProvider(Protocol):
    """Tabular market data. Serves DS1 (equity, 5y) and DS4 (index, 2y)."""

    name: str

    def available(self) -> bool:
        """Whether this provider can run -- keys present, package importable."""

    def fetch_prices(self, symbol: str, window: DateWindow) -> pd.DataFrame:
        """Daily OHLCV over `window`, indexed by date, columns == OHLCV_COLUMNS."""


@runtime_checkable
class TextProvider(Protocol):
    """Text data. Serves DS2, DS3 (stock news + community) and DS5 (macro)."""

    name: str
    kind: str

    def available(self) -> bool: ...

    def fetch_documents(self, query: str, window: DateWindow, limit: int = 500) -> list[Document]:
        """Documents matching `query` published within `window`."""


class RateLimiter:
    """Minimum spacing between calls, enforced by sleeping.

    Crude on purpose. Every provider here is free-tier or unofficial, and the
    failure mode for going too fast is a soft ban that costs a day, not an
    error you can retry past. A blocking sleep is the right trade when the
    alternative is losing access mid-sweep.
    """

    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval = min_interval_seconds
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


class DiskCache:
    """A TTL'd, content-addressed cache under `data/raw/`.

    Frames go to Parquet, documents to JSON. Parquet rather than CSV because it
    round-trips dtypes and a DatetimeIndex without a schema declaration -- a
    CSV cache silently turns your date index into strings and the bug surfaces
    a long way downstream.

    TTL semantics differ by how old the data is, which matters more than it
    looks. Historical windows that ended months ago are immutable: those get an
    effectively infinite TTL. Only windows touching the present expire, because
    only they can change.
    """

    def __init__(self, root: Path, ttl_hours: int = 12) -> None:
        self.root = Path(root)
        self.ttl = timedelta(hours=ttl_hours)
        self.root.mkdir(parents=True, exist_ok=True)

    def _key(self, provider: str, kind: str, subject: str, window: DateWindow) -> str:
        raw = f"{provider}|{kind}|{subject.upper()}|{window.start}|{window.end}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        # Human-readable prefix so `ls data/raw/` is inspectable rather than a
        # wall of hashes -- you will want to know what is cached.
        safe = "".join(c if c.isalnum() else "_" for c in subject)[:24]
        return f"{provider}__{kind}__{safe}__{digest}"

    def _is_fresh(self, path: Path, window: DateWindow) -> bool:
        if not path.exists():
            return False
        # A window that closed before today can never gain new data.
        if window.end < date.today():
            return True
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        return age < self.ttl

    # --- frames ----------------------------------------------------------

    def get_frame(self, provider: str, kind: str, subject: str,
                  window: DateWindow) -> pd.DataFrame | None:
        path = self.root / f"{self._key(provider, kind, subject, window)}.parquet"
        if not self._is_fresh(path, window):
            return None
        try:
            return pd.read_parquet(path)
        except Exception as exc:  # a corrupt cache entry must not be fatal
            log.warning("cache read failed for %s (%s); refetching", path.name, exc)
            return None

    def put_frame(self, provider: str, kind: str, subject: str,
                  window: DateWindow, frame: pd.DataFrame) -> None:
        path = self.root / f"{self._key(provider, kind, subject, window)}.parquet"
        try:
            frame.to_parquet(path)
        except Exception as exc:
            # pyarrow is optional. Losing the cache degrades speed, not
            # correctness, so this is a warning rather than a raise.
            log.warning("cache write failed for %s (%s); continuing uncached", path.name, exc)

    # --- documents -------------------------------------------------------

    def get_documents(self, provider: str, kind: str, subject: str,
                      window: DateWindow) -> list[Document] | None:
        path = self.root / f"{self._key(provider, kind, subject, window)}.json"
        if not self._is_fresh(path, window):
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [Document.from_dict(d) for d in payload]
        except Exception as exc:
            log.warning("cache read failed for %s (%s); refetching", path.name, exc)
            return None

    def put_documents(self, provider: str, kind: str, subject: str,
                      window: DateWindow, docs: Iterable[Document]) -> None:
        path = self.root / f"{self._key(provider, kind, subject, window)}.json"
        payload = [d.to_dict() for d in docs]
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


class BaseProvider(ABC):
    """Shared plumbing: naming, cache handle, and the window filter.

    Concrete providers implement `_fetch_*` and inherit caching. Not required by
    the Protocols above -- a provider can be any object with the right methods --
    but every provider in this package uses it.
    """

    name: str = "base"

    def __init__(self, cache: DiskCache | None = None) -> None:
        self.cache = cache

    @abstractmethod
    def available(self) -> bool: ...

    @staticmethod
    def clip_frame(frame: pd.DataFrame, window: DateWindow) -> pd.DataFrame:
        """Trim a frame to the half-open window.

        Providers routinely return a few extra bars on either side -- a request
        for a date that fell on a weekend gets served from the nearest trading
        day. Clipping here rather than trusting the vendor is what enforces the
        leakage rule from `windows.py`: no row at or after `as_of` survives.
        """
        if frame.empty:
            return frame
        idx = pd.to_datetime(frame.index).date
        mask = [window.start <= d < window.end for d in idx]
        return frame.loc[mask]

    @staticmethod
    def clip_documents(docs: list[Document], window: DateWindow) -> list[Document]:
        """Same rule for text. Applied unconditionally, however good the provider."""
        return [d for d in docs if window.contains(d.published)]
