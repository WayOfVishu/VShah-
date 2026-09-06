"""GET /api/datasets/{symbol} -- the five datasets, summarised.

Returns what was gathered and where it came from, not the data itself. A year
of article text is megabytes; the app wants counts, date ranges, sentiment
summaries, and provenance.

The provenance is the reason this endpoint exists separately from `/predict`.
A forecast built on 400 real articles and one built on 12 synthetic ones look
identical in the predict response, and the difference matters more than the
forecast does. This endpoint makes it visible, and the UI should show it.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from stocks.features import text as text_features
from stocks.ingest.registry import build_datasets
from stocks.windows import Dataset, WindowSpec

router = APIRouter(prefix="/api", tags=["datasets"])


class WindowOut(BaseModel):
    start: date
    end: date
    days: int


class TextWindowOut(BaseModel):
    window: WindowOut
    n_documents: int
    documents_per_day: float
    n_sources: int
    sentiment_mean: float | None = None
    sentiment_net: float | None = None
    top_sources: list[str] = Field(default_factory=list)


class PriceWindowOut(BaseModel):
    window: WindowOut
    n_bars: int
    first_close: float | None = None
    last_close: float | None = None
    total_return: float | None = None


class DatasetsResponse(BaseModel):
    symbol: str
    as_of: date

    prices_equity: PriceWindowOut
    prices_index: dict[str, PriceWindowOut]
    news_baseline: TextWindowOut
    news_recent: TextWindowOut
    macro: TextWindowOut

    sources: dict[str, str] = Field(..., description="which provider served each dataset")
    synthetic: list[str] = Field(..., description="datasets served by the offline fallback")
    warning: str | None = None


def _window_out(w) -> WindowOut:
    return WindowOut(start=w.start, end=w.end, days=w.days)


def _price_out(frame, window) -> PriceWindowOut:
    out = PriceWindowOut(window=_window_out(window), n_bars=len(frame))
    if not frame.empty and "adj_close" in frame:
        px = frame["adj_close"].dropna()
        if len(px) >= 2:
            out.first_close = float(px.iloc[0])
            out.last_close = float(px.iloc[-1])
            out.total_return = float(px.iloc[-1] / px.iloc[0] - 1.0)
    return out


def _text_out(docs, window) -> TextWindowOut:
    from collections import Counter

    out = TextWindowOut(
        window=_window_out(window),
        n_documents=len(docs),
        documents_per_day=len(docs) / max(1, window.days),
        n_sources=len({d.source for d in docs}),
        top_sources=[s for s, _ in Counter(d.source for d in docs).most_common(5)],
    )
    if docs:
        summary = text_features.score_sentiment(docs)
        out.sentiment_mean = summary.mean
        out.sentiment_net = summary.net
    return out


@router.get("/datasets/{symbol}", response_model=DatasetsResponse)
def get_datasets(
    symbol: str,
    as_of: date | None = Query(None, description="defaults to today"),
) -> DatasetsResponse:
    spec = WindowSpec.for_as_of(as_of)

    try:
        bundle = build_datasets(symbol.upper(), spec.as_of, spec=spec)
    except Exception as exc:
        raise HTTPException(502, f"dataset build failed: {exc}") from exc

    warning = None
    if bundle.has_synthetic:
        warning = (
            f"{len(bundle.synthetic)} of 5 datasets came from the offline synthetic "
            "fallback. Any forecast built on this is not based on real data."
        )

    return DatasetsResponse(
        symbol=bundle.symbol,
        as_of=bundle.as_of,
        prices_equity=_price_out(bundle.prices_equity, spec.prices_equity),
        prices_index={
            t: _price_out(f, spec.prices_index) for t, f in bundle.prices_index.items()
        },
        news_baseline=_text_out(bundle.news_baseline, spec.news_baseline),
        news_recent=_text_out(bundle.news_recent, spec.news_recent),
        macro=_text_out(bundle.macro_text, spec.macro),
        sources=bundle.sources,
        synthetic=sorted(bundle.synthetic),
        warning=warning,
    )


@router.get("/windows", response_model=dict, tags=["datasets"])
def get_windows(as_of: date | None = Query(None)) -> dict:
    """The five window definitions for an as-of date. No data fetched.

    Cheap, and useful to the UI for drawing the timeline before any of the slow
    work starts.
    """
    spec = WindowSpec.for_as_of(as_of)
    return {
        "as_of": spec.as_of.isoformat(),
        "windows": {
            ds.value: {
                "start": spec.window(ds).start.isoformat(),
                "end": spec.window(ds).end.isoformat(),
                "days": spec.window(ds).days,
                "kind": "text" if ds.is_text else "tabular",
            }
            for ds in Dataset
        },
    }
