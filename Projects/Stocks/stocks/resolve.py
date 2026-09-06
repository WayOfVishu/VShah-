"""Free-text to ticker: "apple", "AAPL", "Apple Inc." all resolve to AAPL.

The web app lets the user type whatever they want, so something has to turn
that into a symbol a price API will accept. Three strategies, tried in order:

    1. exact ticker      the input already is a symbol -- cheap, tried first
    2. local alias table a few hundred well-known names, offline, instant
    3. Yahoo search      the general case, network, handles everything else

The local table exists because it covers most of what anyone actually types
into a stock app, and it means the common case never touches the network. It
is not meant to be exhaustive -- strategy 3 is the real answer for the long
tail.

Ambiguity is surfaced, not resolved silently. "Apple" is unambiguous; "delta"
is Delta Air Lines, a hedging term, and a Greek letter. `resolve()` returns
ranked candidates and lets the caller decide, which for the web app means
showing a picker rather than guessing and being confidently wrong.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache

log = logging.getLogger(__name__)

__all__ = ["Candidate", "resolve", "resolve_one", "looks_like_ticker"]

# Exchange suffixes: BRK.B, RY.TO, SHOP.TO, VOD.L. Indices lead with ^.
TICKER_RE = re.compile(r"^\^?[A-Z]{1,6}(?:[.\-][A-Z]{1,4})?$")

# Deliberately partial. Enough to make the common path offline and instant;
# anything not here falls through to Yahoo search.
ALIASES: dict[str, str] = {
    "apple": "AAPL", "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL",
    "amazon": "AMZN", "meta": "META", "facebook": "META", "tesla": "TSLA",
    "nvidia": "NVDA", "netflix": "NFLX", "intel": "INTC", "amd": "AMD",
    "advanced micro devices": "AMD", "ibm": "IBM", "oracle": "ORCL",
    "salesforce": "CRM", "adobe": "ADBE", "cisco": "CSCO", "qualcomm": "QCOM",
    "broadcom": "AVGO", "palantir": "PLTR", "uber": "UBER", "airbnb": "ABNB",
    "spotify": "SPOT", "shopify": "SHOP", "paypal": "PYPL", "block": "SQ",
    "square": "SQ", "coinbase": "COIN", "robinhood": "HOOD", "snowflake": "SNOW",
    "berkshire": "BRK-B", "berkshire hathaway": "BRK-B",
    "jpmorgan": "JPM", "jp morgan": "JPM", "goldman sachs": "GS", "goldman": "GS",
    "bank of america": "BAC", "wells fargo": "WFC", "morgan stanley": "MS",
    "visa": "V", "mastercard": "MA", "american express": "AXP",
    "walmart": "WMT", "costco": "COST", "target": "TGT", "home depot": "HD",
    "nike": "NKE", "starbucks": "SBUX", "mcdonalds": "MCD", "mcdonald's": "MCD",
    "coca cola": "KO", "coke": "KO", "pepsi": "PEP", "pepsico": "PEP",
    "disney": "DIS", "walt disney": "DIS", "comcast": "CMCSA",
    "exxon": "XOM", "exxonmobil": "XOM", "chevron": "CVX", "shell": "SHEL",
    "suncor": "SU", "enbridge": "ENB", "canadian national railway": "CNI",
    "royal bank": "RY", "royal bank of canada": "RY", "td bank": "TD",
    "toronto dominion": "TD", "bank of montreal": "BMO", "scotiabank": "BNS",
    "pfizer": "PFE", "johnson & johnson": "JNJ", "johnson and johnson": "JNJ",
    "moderna": "MRNA", "eli lilly": "LLY", "merck": "MRK", "abbvie": "ABBV",
    "unitedhealth": "UNH", "boeing": "BA", "lockheed martin": "LMT",
    "caterpillar": "CAT", "general electric": "GE", "ford": "F",
    "general motors": "GM", "rivian": "RIVN", "lucid": "LCID",
    # Index shorthands, so "sp500" resolves rather than 404ing on a price API.
    "sp500": "^GSPC", "s&p 500": "^GSPC", "s&p500": "^GSPC", "spx": "^GSPC",
    "nasdaq": "^IXIC", "dow": "^DJI", "dow jones": "^DJI",
    "russell 2000": "^RUT", "vix": "^VIX", "tsx": "^GSPTSE",
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """One possible interpretation of the user's input."""

    symbol: str
    name: str
    exchange: str | None = None
    kind: str = "equity"          # equity | index | etf | crypto
    confidence: float = 1.0       # 1.0 exact, 0.9 alias, 0.3-0.8 search
    source: str = "unknown"

    def __str__(self) -> str:
        venue = f" ({self.exchange})" if self.exchange else ""
        return f"{self.symbol} - {self.name}{venue}"


def looks_like_ticker(text: str) -> bool:
    """Whether the input is already a plausible symbol.

    Case-sensitive on purpose. "AAPL" is a ticker; "apple" is a company name
    that happens to be short. Lowercasing here would send every alias lookup
    down the ticker path and resolve "cost" to Costco when the user meant to
    type something else entirely.
    """
    return bool(TICKER_RE.match(text.strip()))


@lru_cache(maxsize=512)
def resolve(query: str, limit: int = 5) -> tuple[Candidate, ...]:
    """Ranked interpretations of `query`, best first.

    Cached because the web app will resolve the same handful of names
    repeatedly and strategy 3 is a network round trip.

    Returns a tuple rather than a list so it is hashable and `lru_cache` can
    hold it. An empty tuple means nothing matched -- the caller should say so
    rather than substituting a guess.
    """
    text = query.strip()
    if not text:
        return ()

    out: list[Candidate] = []
    seen: set[str] = set()

    def add(c: Candidate) -> None:
        if c.symbol.upper() not in seen:
            seen.add(c.symbol.upper())
            out.append(c)

    # 1. already a ticker
    if looks_like_ticker(text):
        add(Candidate(text.upper(), text.upper(), kind="index" if text.startswith("^") else "equity",
                      confidence=1.0, source="literal"))

    # 2. alias table
    normalized = re.sub(r"[^a-z0-9&' ]", "", text.lower()).strip()
    normalized = re.sub(r"\s+(inc|corp|corporation|company|co|ltd|plc|sa|nv|ag)\.?$", "", normalized)
    if normalized in ALIASES:
        symbol = ALIASES[normalized]
        add(Candidate(symbol, text.title(), kind="index" if symbol.startswith("^") else "equity",
                      confidence=0.9, source="alias"))

    # Substring matches, so "royal bank of can" still lands somewhere useful.
    if len(normalized) >= 4:
        for alias, symbol in ALIASES.items():
            if len(out) >= limit:
                break
            if normalized in alias or alias in normalized:
                add(Candidate(symbol, alias.title(), confidence=0.7, source="alias-partial"))

    # 3. Yahoo search for everything else
    if len(out) < limit:
        for c in _yahoo_search(text, limit - len(out)):
            add(c)

    out.sort(key=lambda c: -c.confidence)
    return tuple(out[:limit])


def resolve_one(query: str) -> Candidate:
    """The single best interpretation, or raise.

    For the CLI and for tests, where a picker is not available. The web app
    should call `resolve()` and show the alternatives instead -- see the module
    docstring on ambiguity.
    """
    candidates = resolve(query)
    if not candidates:
        raise ValueError(f"could not resolve {query!r} to a ticker")
    return candidates[0]


def _yahoo_search(query: str, limit: int) -> list[Candidate]:
    """Yahoo's autocomplete endpoint. Unofficial, keyless, and good at names.

    Same caveat as `YFinanceProvider`: not a contract, and it can change or
    start refusing. Failure returns an empty list rather than raising, because
    strategies 1 and 2 may already have produced a usable answer and losing the
    long tail is better than failing the request.
    """
    try:
        import requests

        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": limit, "newsCount": 0},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; stocks-research/0.1)"},
        )
        resp.raise_for_status()
        quotes = resp.json().get("quotes", [])
    except Exception as exc:
        log.debug("yahoo search failed for %r: %s", query, exc)
        return []

    out = []
    for i, q in enumerate(quotes[:limit]):
        symbol = q.get("symbol")
        if not symbol:
            continue
        out.append(Candidate(
            symbol=symbol,
            name=q.get("longname") or q.get("shortname") or symbol,
            exchange=q.get("exchDisp"),
            kind=(q.get("quoteType") or "equity").lower(),
            # Yahoo returns results already ranked; decay so the first is
            # preferred without ever outranking an exact ticker or alias hit.
            confidence=max(0.3, 0.8 - i * 0.1),
            source="yahoo",
        ))
    return out
