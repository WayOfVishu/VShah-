"""Text providers -- DS2 (news baseline), DS3 (recent news + community).

    GdeltProvider      no key, the default. Worldwide news index, 2015-present.
    NewsApiProvider    keyed. DS3 only -- the free tier caps at 30 days back.
    RedditProvider     keyed. Community sentiment for DS3.
    SyntheticTextProvider  offline fallback.

**The archive problem, which shapes every choice here.** DS2 needs articles
from 12 to 2 months ago. Almost every consumer news API refuses to serve that:
NewsAPI's free tier stops at 30 days, most others at 7. An API that cannot
reach back a year cannot build DS2 at all, so provider selection is not a
preference here, it is a constraint. GDELT is the default because it is the one
free source that indexes back to 2015, which is what makes the historical
walk-forward sweep possible.

**What GDELT does and does not give you.** It returns article *metadata* --
URL, title, publication date, source, tone -- not article *bodies*. Fetching
the bodies means going to each URL and scraping it, which is slow, frequently
blocked by paywalls, and legally murkier than using the metadata. So the
default here is metadata-only, and `fetch_full_text=True` is opt-in with the
tradeoffs written at the call site.

That is less limiting than it sounds. Headlines are dense with sentiment by
construction, and GDELT ships its own tone score per article. A
title-plus-tone corpus is a perfectly reasonable DS2/DS3 and it is what
`features/text.py` is built to consume.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np

from ..windows import DateWindow
from .base import BaseProvider, DiskCache, Document, ProviderError, RateLimiter

log = logging.getLogger(__name__)

__all__ = ["GdeltProvider", "NewsApiProvider", "RedditProvider", "SyntheticTextProvider"]

# GDELT publishes no rate limit and sends no Retry-After header -- it simply
# starts returning 429, and keeps doing so for some minutes after you stop.
# Five seconds is the interval that empirically survives a sustained sweep;
# 1.2s did not, and the failure was quiet (every chunk 429s, each one logged
# and skipped, and the bundle completes with zero documents).
MIN_INTERVAL = 5.0


def _doc_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _gdelt_query(term: str) -> str:
    """Quote a bare search term; pass a formed boolean expression through.

    A bare ticker has to be quoted, or GDELT tokenises it. But
    `MacroTextProvider.combined_query()` already returns a quoted disjunction,
    and wrapping *that* in another pair of quotes produces
    `"("federal reserve" OR ...)"`, which GDELT parses as a literal phrase and
    matches nothing. That failure is silent -- a 200 response with an empty
    article list -- so it is worth a named function and a test rather than an
    inline f-string.
    """
    t = term.strip()
    return t if t.startswith("(") or '"' in t else f'"{t}"'


class GdeltProvider(BaseProvider):
    """GDELT DOC 2.0 API. Default provider for DS2, DS3, and DS5.

    Free, keyless, no registration, and it indexes worldwide news every 15
    minutes back to 2015 -- the only free source in this file that can cover
    DS2's 12-months-ago window.

    Two API quirks worth knowing, since both produce silent wrong answers:

    1. A single query is capped at 250 records regardless of `maxrecords`, and
       the cap is applied *after* sorting. Requesting three months in one call
       gets you 250 articles concentrated in whichever days GDELT ranked
       highest, not a representative sample. `fetch_documents` therefore
       chunks the window into `chunk_days` slices and requests each
       separately, which costs more calls but yields even coverage across the
       window -- and even coverage is what DS2-versus-DS3 comparisons depend
       on. Since each call is rate-limited, `chunk_days` is the main control
       on how long a bundle takes; see `__init__`.

    2. `tone` is GDELT's own sentiment score, roughly -100 to +100 and in
       practice mostly within -10 to +10. It is carried through into
       `Document.score` because it is a free, independently-computed sentiment
       signal, and a useful sanity check against whatever `features/text.py`
       derives on its own.
    """

    name = "gdelt"
    kind = "news"
    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
    CHUNK_DAYS = 21

    def __init__(self, cache: DiskCache | None = None, fetch_full_text: bool = False,
                 chunk_days: int | None = None, min_interval: float = MIN_INTERVAL,
                 max_retries: int = 3) -> None:
        super().__init__(cache)
        self.fetch_full_text = fetch_full_text
        # Chunking trades calls against coverage evenness. 21 days is the
        # default compromise for stock news; DS5 overrides it upward because
        # macro coverage does not need fortnightly resolution. Every call costs
        # at least `min_interval` seconds, and a bundle makes ~20, so this is
        # the main lever on how long a walk-forward sweep takes.
        self.chunk_days = chunk_days or self.CHUNK_DAYS
        self.max_retries = max_retries
        self._limiter = RateLimiter(min_interval)

    def _get(self, params: dict):
        """One GDELT call, with backoff on 429.

        GDELT does not document its limit and does not send Retry-After; it
        just starts returning 429, and it keeps returning them for a while
        after you stop. Backing off properly matters more than it usually
        would, because the alternative is not a slow sweep but a sweep that
        silently produces empty text datasets -- `fetch_documents` logs each
        failed chunk and continues, so a rate-limited run still "succeeds"
        with zero documents.
        """
        import requests

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self._limiter.wait()
            try:
                resp = requests.get(self.BASE_URL, params=params, timeout=30,
                                    headers={"User-Agent": "stocks-research/0.1"})
                if resp.status_code == 429:
                    backoff = MIN_INTERVAL * (2 ** attempt)
                    log.debug("gdelt 429; backing off %.0fs", backoff)
                    time.sleep(backoff)
                    last_exc = ProviderError("429 Too Many Requests")
                    continue
                resp.raise_for_status()
                # GDELT serves HTML error pages with a 200 status when a query
                # is malformed, so .json() must be guarded rather than trusted.
                return resp.json()
            except Exception as exc:
                last_exc = exc
                time.sleep(MIN_INTERVAL * (2 ** attempt))

        raise ProviderError(f"gdelt request failed after {self.max_retries} attempts: {last_exc}")

    def available(self) -> bool:
        try:
            import requests  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch_documents(self, query: str, window: DateWindow, limit: int = 500) -> list[Document]:
        if self.cache is not None:
            hit = self.cache.get_documents(self.name, self.kind, query, window)
            if hit is not None:
                return hit

        docs: list[Document] = []
        cursor = window.start
        per_chunk = max(20, min(250, limit // max(1, window.days // self.chunk_days)))
        failures = 0
        chunks = 0

        while cursor < window.end and len(docs) < limit:
            chunk_end = min(cursor + timedelta(days=self.chunk_days), window.end)
            chunks += 1
            try:
                payload = self._get({
                    "query": f"{_gdelt_query(query)} sourcelang:english",
                    "mode": "artlist",
                    "format": "json",
                    "maxrecords": per_chunk,
                    "startdatetime": cursor.strftime("%Y%m%d000000"),
                    "enddatetime": chunk_end.strftime("%Y%m%d000000"),
                    "sort": "hybridrel",
                })
            except ProviderError as exc:
                log.warning("gdelt chunk %s..%s failed: %s", cursor, chunk_end, exc)
                failures += 1
                cursor = chunk_end
                continue

            for art in payload.get("articles", []):
                published = _parse_gdelt_date(art.get("seendate", ""))
                if published is None or not window.contains(published):
                    continue
                title = (art.get("title") or "").strip()
                if not title:
                    continue
                docs.append(Document(
                    doc_id=_doc_id(art.get("url", ""), title),
                    published=published,
                    title=title,
                    # Metadata-only by default; see the module docstring.
                    text=_fetch_article_text(art.get("url")) if self.fetch_full_text else "",
                    source=art.get("domain", "unknown"),
                    kind="news",
                    url=art.get("url"),
                    score=_safe_float(art.get("tone")),
                    metadata={"language": art.get("language"), "country": art.get("sourcecountry")},
                ))
            cursor = chunk_end

        # A wholly failed pull must not be cached, or a rate-limited run
        # poisons the cache with an empty corpus that later runs treat as a
        # legitimate hit -- and DS2 having zero documents is indistinguishable
        # downstream from a stock nobody wrote about.
        if failures == chunks and chunks:
            raise ProviderError(
                f"every one of {chunks} gdelt chunks failed for {query!r} over {window} "
                "(usually rate limiting -- wait a few minutes and retry)"
            )
        if failures:
            log.warning("gdelt: %d of %d chunks failed for %r; coverage is uneven",
                        failures, chunks, query)

        docs = self.clip_documents(docs, window)[:limit]
        if self.cache is not None:
            self.cache.put_documents(self.name, self.kind, query, window, docs)
        return docs


class NewsApiProvider(BaseProvider):
    """NewsAPI.org. Keyed, **DS3 only**, and **off unless explicitly allowed**.

    Two independent reasons this cannot be a default, one technical and one
    contractual.

    *Technical.* The free tier serves the last 30 days. That covers DS3's
    two-month window partially and DS2's twelve-month window not at all, so
    `fetch_documents` refuses a window starting more than 30 days back rather
    than quietly returning a truncated corpus. A silently short DS2 would make
    the baseline-versus-recent comparison meaningless while still producing
    numbers, which is the worst kind of failure.

    *Contractual, and the reason for the second flag.* NewsAPI's Developer plan

        "may be used for development and testing in a development environment
         only, and cannot be used in a staging or production environment
         (including internally)."

    A hosted web app is a production environment, so serving it from a free
    NewsAPI key would breach their terms. Because that is a licence question
    rather than a technical one, no amount of caching or care makes it
    permissible -- the only correct handling is not to enable it by accident.

    Hence `available()` requires **both** a key and
    `NEWSAPI_ALLOW_NONPRODUCTION=true`. Pasting a key into `.env` is something
    people do while exploring; setting a second flag whose name states the
    restriction is a deliberate act. See `docs/api-terms.md`.
    """

    name = "newsapi"
    kind = "news"
    BASE_URL = "https://newsapi.org/v2/everything"
    FREE_TIER_DAYS = 30

    def __init__(self, api_key: str | None, cache: DiskCache | None = None,
                 allow_nonproduction: bool = False) -> None:
        super().__init__(cache)
        self.api_key = api_key
        self.allow_nonproduction = allow_nonproduction
        self._limiter = RateLimiter(1.0)

    def available(self) -> bool:
        if self.api_key and not self.allow_nonproduction:
            log.info(
                "NEWSAPI_API_KEY is set but NewsAPI stays disabled: its free plan is "
                "development-only and forbids production use. Set "
                "NEWSAPI_ALLOW_NONPRODUCTION=true if this is a dev environment. "
                "See docs/api-terms.md."
            )
        return bool(self.api_key and self.allow_nonproduction)

    def fetch_documents(self, query: str, window: DateWindow, limit: int = 500) -> list[Document]:
        oldest = date.today() - timedelta(days=self.FREE_TIER_DAYS)
        if window.start < oldest:
            raise ProviderError(
                f"newsapi free tier reaches back to {oldest}, window starts {window.start}; "
                "use the GDELT provider for anything older than 30 days"
            )
        if self.cache is not None:
            hit = self.cache.get_documents(self.name, self.kind, query, window)
            if hit is not None:
                return hit
        if not self.api_key:
            raise ProviderError("NEWSAPI_API_KEY is not set")

        import requests

        self._limiter.wait()
        try:
            resp = requests.get(
                self.BASE_URL,
                params={
                    "q": query,
                    "from": window.start.isoformat(),
                    "to": window.end.isoformat(),
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": min(100, limit),
                },
                headers={"X-Api-Key": self.api_key},
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise ProviderError(f"newsapi request failed: {exc}") from exc

        docs = []
        for art in payload.get("articles", []):
            published = _parse_iso_date(art.get("publishedAt"))
            if published is None:
                continue
            docs.append(Document(
                doc_id=_doc_id(art.get("url", ""), art.get("title", "")),
                published=published,
                title=(art.get("title") or "").strip(),
                # NewsAPI truncates `content` at 200 chars on the free tier;
                # description is usually the more complete of the two.
                text=(art.get("description") or art.get("content") or "").strip(),
                source=(art.get("source") or {}).get("name", "unknown"),
                kind="news",
                url=art.get("url"),
            ))

        docs = self.clip_documents(docs, window)[:limit]
        if self.cache is not None:
            self.cache.put_documents(self.name, self.kind, query, window, docs)
        return docs


class RedditProvider(BaseProvider):
    """Reddit via PRAW -- the "community perspective" half of DS3.

    Searches the investing subreddits for the ticker and returns submissions
    plus their top comments.

    **A hard limitation you should design around rather than fight.** Reddit's
    search API cannot filter by date range; it returns the top ~1000 results for
    a query sorted by relevance or recency, and that is all. Documents outside
    the requested window get filtered client-side by `clip_documents`, which
    means a request for a window twelve months back will usually return very
    little. Pushshift used to solve this and its public API closed in 2023.

    Practical consequence: Reddit realistically serves **DS3 only**, and DS2's
    community half will be thin or empty. That is an acceptable asymmetry as
    long as `features/text.py` knows about it -- which is why `Document.kind`
    exists, so the feature code can count news and community separately instead
    of reading a shrinking corpus as falling interest.

    `score` carries upvotes, which is a crude but real proxy for how much a view
    was shared rather than merely posted.
    """

    name = "reddit"
    kind = "community"
    SUBREDDITS = ("stocks", "investing", "wallstreetbets", "StockMarket", "SecurityAnalysis")

    def __init__(self, client_id: str | None, client_secret: str | None,
                 user_agent: str, cache: DiskCache | None = None) -> None:
        super().__init__(cache)
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent

    def available(self) -> bool:
        if not (self.client_id and self.client_secret):
            return False
        try:
            import praw  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch_documents(self, query: str, window: DateWindow, limit: int = 500) -> list[Document]:
        if self.cache is not None:
            hit = self.cache.get_documents(self.name, self.kind, query, window)
            if hit is not None:
                return hit
        if not self.available():
            raise ProviderError("reddit credentials missing or praw not installed")

        import praw

        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
            check_for_async=False,
        )

        docs: list[Document] = []
        for sub in self.SUBREDDITS:
            if len(docs) >= limit:
                break
            try:
                results = reddit.subreddit(sub).search(
                    query, sort="new", time_filter="year", limit=limit // len(self.SUBREDDITS)
                )
                for post in results:
                    published = datetime.fromtimestamp(post.created_utc, tz=timezone.utc).date()
                    if not window.contains(published):
                        continue
                    docs.append(Document(
                        doc_id=_doc_id(sub, post.id),
                        published=published,
                        title=post.title,
                        text=(post.selftext or "")[:20_000],
                        source=f"r/{sub}",
                        kind="community",
                        url=f"https://reddit.com{post.permalink}",
                        score=float(post.score),
                        metadata={"num_comments": post.num_comments, "subreddit": sub},
                    ))
            except Exception as exc:
                # One dead subreddit must not take down the whole DS3 pull.
                log.warning("reddit search failed on r/%s: %s", sub, exc)

        docs = self.clip_documents(docs, window)[:limit]
        if self.cache is not None:
            self.cache.put_documents(self.name, self.kind, query, window, docs)
        return docs


class SyntheticTextProvider(BaseProvider):
    """Deterministic fake documents. No network, always available.

    Assembled from sentence templates with a per-(query, window) seed. As with
    `SyntheticPriceProvider`, the sentiment here is **uncorrelated with the
    synthetic price series on purpose**: an end-to-end run on synthetic data
    should score at chance. A synthetic run that scores well is evidence of
    leakage in the pipeline, and finding that on fake data is much cheaper than
    finding it in a live backtest.
    """

    name = "synthetic"
    kind = "news"

    POSITIVE = [
        "{q} beat consensus estimates this quarter, with management raising full-year guidance.",
        "Analysts at three major banks upgraded {q} following stronger-than-expected margins.",
        "{q} announced a buyback programme, which the market read as a signal of confidence.",
        "Order backlog at {q} reached a multi-year high, easing concerns about demand.",
    ]
    NEGATIVE = [
        "{q} missed on revenue and withdrew its guidance for the second half.",
        "Regulatory scrutiny of {q} intensified after a filing disclosed an ongoing investigation.",
        "Two senior executives departed {q} this month, renewing questions about strategy.",
        "Margin compression at {q} continued as input costs outpaced pricing power.",
    ]
    NEUTRAL = [
        "{q} will report earnings later this month; consensus expects little change.",
        "Trading volume in {q} was in line with its three-month average.",
        "{q} confirmed the date of its annual shareholder meeting.",
        "Sector-wide moves accounted for most of the change in {q} this week.",
    ]

    def available(self) -> bool:
        return True

    def fetch_documents(self, query: str, window: DateWindow, limit: int = 500) -> list[Document]:
        seed = abs(hash((query.upper(), window.start, window.end))) % (2**32)
        rng = np.random.default_rng(seed)

        # Roughly two documents a day, capped, which is the right order of
        # magnitude for a mid-cap name's news flow.
        n = int(min(limit, max(10, window.days * 2)))
        offsets = rng.integers(0, max(1, window.days), n)

        docs = []
        for i, off in enumerate(sorted(offsets)):
            published = window.start + timedelta(days=int(off))
            if not window.contains(published):
                continue
            bucket = rng.choice([self.POSITIVE, self.NEGATIVE, self.NEUTRAL], p=[0.35, 0.25, 0.40])
            body = " ".join(str(rng.choice(bucket)).format(q=query) for _ in range(rng.integers(2, 6)))
            docs.append(Document(
                doc_id=_doc_id(query, str(i), published.isoformat()),
                published=published,
                title=str(rng.choice(bucket)).format(q=query),
                text=body,
                source="synthetic.example",
                kind="community" if i % 4 == 0 else "news",
                url=None,
                score=float(rng.normal(0, 3)),
                metadata={"synthetic": True},
            ))
        return docs


# --- helpers -------------------------------------------------------------


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_gdelt_date(raw: str) -> date | None:
    """GDELT stamps are `YYYYMMDDTHHMMSSZ`, occasionally `YYYYMMDDHHMMSS`."""
    cleaned = re.sub(r"[^0-9]", "", raw or "")
    if len(cleaned) < 8:
        return None
    try:
        return datetime.strptime(cleaned[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _fetch_article_text(url: str | None, timeout: int = 15) -> str:
    """Best-effort body scrape for `fetch_full_text=True`.

    Deliberately unambitious: fetch, strip tags, take the paragraph text. It
    will fail on paywalls, JS-rendered pages, and anything behind Cloudflare,
    and returns "" rather than raising when it does -- a missing body should
    degrade that one document to title-only, not abort a 500-document pull.

    If you decide you want real article bodies, replace this with `trafilatura`
    (`pip install trafilatura`), which does boilerplate removal properly. It is
    left out of the default requirements because the metadata-only path does
    not need it.
    """
    if not url:
        return ""
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "stocks-research/0.1"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        return "\n".join(p for p in paragraphs if len(p) > 40)[:50_000]
    except Exception as exc:
        log.debug("article scrape failed for %s: %s", url, exc)
        return ""
