"""GET /api/resolve -- free text to ticker candidates.

The first call the web app makes. The user types "apple" or "AAPL" or "Apple
Inc." and gets back ranked candidates.

Returns a *list*, not a single answer, and the UI should show a picker when
there is more than one plausible match. "Delta" is Delta Air Lines, an options
Greek, and a generic word; guessing silently and being wrong is worse than
asking, because the user has no way to tell a wrong resolution from a wrong
forecast further down the line.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from stocks.resolve import resolve

router = APIRouter(prefix="/api", tags=["resolve"])


class CandidateOut(BaseModel):
    symbol: str = Field(..., examples=["AAPL"])
    name: str = Field(..., examples=["Apple Inc."])
    exchange: str | None = None
    kind: str = Field("equity", description="equity | index | etf | crypto")
    confidence: float = Field(..., ge=0, le=1)
    source: str = Field(..., description="literal | alias | alias-partial | yahoo")


class ResolveResponse(BaseModel):
    query: str
    candidates: list[CandidateOut]
    unambiguous: bool = Field(
        ..., description="true when the UI can safely skip the picker"
    )


@router.get("/resolve", response_model=ResolveResponse)
def resolve_symbol(
    q: str = Query(..., min_length=1, max_length=100, description="ticker or company name"),
    limit: int = Query(5, ge=1, le=10),
) -> ResolveResponse:
    candidates = resolve(q, limit)
    if not candidates:
        raise HTTPException(404, f"could not resolve {q!r} to a ticker")

    # "Unambiguous" gates whether the UI can skip the picker. Decided on the
    # *kind* of match rather than a margin between hand-assigned confidence
    # scores, because the scores are ordinal at best and a margin rule gets the
    # obvious cases wrong -- "apple" scores 0.90 against a 0.70 substring hit,
    # a 0.20 gap, which no threshold should read as genuine ambiguity.
    #
    # A literal ticker or an exact alias hit is definitive by construction.
    # Everything else (substring hits, Yahoo search) falls back to requiring a
    # clear leader, because that is where the real ambiguity lives -- "delta"
    # is an airline, an options Greek, and a generic word.
    top = candidates[0]
    unambiguous = (
        len(candidates) == 1
        or top.source in {"literal", "alias"}
        or top.confidence - candidates[1].confidence >= 0.25
    )

    return ResolveResponse(
        query=q,
        # asdict, not vars: Candidate is a slots dataclass and has no __dict__.
        candidates=[CandidateOut(**asdict(c)) for c in candidates],
        unambiguous=unambiguous,
    )
