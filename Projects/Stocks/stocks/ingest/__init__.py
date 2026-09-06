"""Data acquisition -- the five datasets, behind one function.

    from stocks.ingest import build_datasets
    bundle = build_datasets("AAPL")          # as_of defaults to today

Everything else in this package is implementation detail. Provider choice,
caching, rate limiting, and fallback all happen inside `Registry`, and the rest
of the project never imports a vendor by name.

    base.py      Document, the two provider protocols, the disk cache
    prices.py    DS1 + DS4  -- yfinance, Alpha Vantage, synthetic
    news.py      DS2 + DS3  -- GDELT, NewsAPI, Reddit, synthetic
    macro.py     DS5        -- FRED numeric, GDELT macro text, synthetic
    registry.py  selection, fallback, and build_datasets()
"""

from __future__ import annotations

from .base import Document, DiskCache, ProviderError
from .registry import DatasetBundle, Registry, build_datasets

__all__ = [
    "Document",
    "DiskCache",
    "ProviderError",
    "DatasetBundle",
    "Registry",
    "build_datasets",
]
