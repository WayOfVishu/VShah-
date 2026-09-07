"""Runtime settings, read once from the environment.

Nothing here is required. Every provider key is optional and the registry
degrades to a keyless provider and then to the synthetic one, so a fresh clone
runs end-to-end with no `.env` at all. That is deliberate: the first thing you
should be able to do with this repo is watch the pipeline execute, not go and
register for four API accounts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The market proxies for DS2. The S&P 500 is the index the SCL regression uses
# by default (Chapter 8 wants a broad-market proxy); NASDAQ and the Russell are
# carried as extra features because a tech name's systematic risk is much
# better described by the NASDAQ than by the S&P.
DEFAULT_INDEX_TICKERS = ("^GSPC", "^IXIC", "^RUT", "^VIX")

# Chapter 10's factor proxies. SMB is built from ^RUT minus ^GSPC using tickers
# already in DEFAULT_INDEX_TICKERS; HML needs a value/growth pair, which no
# index in that tuple provides, so these two ETFs are fetched as well.
#
# IWD and IWF are the iShares Russell 1000 Value and Growth funds -- the same
# parent universe split on one vendor's book-to-market definition, which is the
# closest free approximation to a book-to-market sort. They are ETFs rather
# than indices because the free tickers for the underlying Russell indices are
# unreliable on Yahoo.
#
# These are proxies and `finance/multifactor.py` says so at length: a loading
# estimated against them is directional, not comparable to a published
# Fama-French loading. Set STOCKS_DISABLE_FACTORS=1 to skip the extra two price
# pulls per bundle if a sweep is provider-limited.
DEFAULT_FACTOR_TICKERS = ("IWD", "IWF")

# The Chapter 9 market risk premium used when no better estimate is available.
# `capm.realised_market_risk_premium` computes one from DS2 when there is
# enough index history, and this is the fallback; see the note in capm.py about
# why any alpha computed from a default MRP is a sketch.
DEFAULT_MARKET_RISK_PREMIUM = 0.08

# --- the Gemini synthesis dataset (DS3) ----------------------------------
# Model choice: flash rather than pro. The task is scoring a bounded corpus
# against a fixed schema, not reasoning, and a full panel sweep is thousands of
# calls -- pro would multiply the cost by more than an order of magnitude for
# an output that is constrained to a JSON schema either way.
#
# Pinned rather than aliased, deliberately: an unpinned "latest" would change
# the meaning of every cached brief the day Google ships a new revision, and a
# panel whose features shifted mid-sweep is worse than one built on an older
# model. Bump this on purpose, and clear the brief cache when you do.
#
# `gemini-2.5-flash` was retired for new API projects. Its suggested successor,
# `gemini-3.6-flash`, is currently so heavily contended that it returned 503
# through four retries over 57 seconds; `gemini-3.8-flash` did the same over 75.
# `gemini-3.5-flash` answered in 11 seconds. Newest is not most available, and a
# model that cannot complete a call is worth nothing to a sweep of thousands.
#
# Contention moves, so treat this as a measurement with a date on it rather than
# a ranking. `py run.py models` lists what your key can reach; GEMINI_MODEL in
# .env overrides. `gemini-flash-lite-latest` was faster still (9s) and is worth
# testing if cost or throughput binds -- for schema-constrained scoring the lite
# variant may well be enough.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"

# How many documents from each window reach the prompt. GDELT can return 500
# per window and a 12-month baseline plus a 2-month recent window would blow
# past a sane prompt size; these caps keep one call near 10k input tokens.
# Documents are sampled across the window rather than truncated to the head,
# so the cap does not silently turn a 12-month corpus into its first fortnight.
GEMINI_MAX_BASELINE_DOCS = 120
GEMINI_MAX_RECENT_DOCS = 80
GEMINI_MAX_MACRO_DOCS = 40

# FRED series for the macro backdrop. DGS3MO is the risk-free rate every
# excess-return calculation in `finance/` needs; the rest are the standard
# macro backdrop. Text macro comes from GDELT separately.
DEFAULT_FRED_SERIES = (
    "DGS3MO",    # 3-month Treasury -- the r_f used throughout
    "DGS10",     # 10-year Treasury
    "T10Y2Y",    # 10y-2y spread; the classic recession signal
    "CPIAUCSL",  # CPI, for the Fisher equation in returns.py
    "UNRATE",    # unemployment
    "VIXCLS",    # implied volatility
)


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    cache_ttl_hours: int
    alphavantage_key: str | None
    newsapi_key: str | None
    newsapi_allow_nonproduction: bool
    reddit_client_id: str | None
    reddit_client_secret: str | None
    reddit_user_agent: str
    fred_key: str | None
    gemini_key: str | None = None
    gemini_model: str = DEFAULT_GEMINI_MODEL
    gemini_strict_grounding: bool = True
    disable_factors: bool = False
    force_synthetic: bool = False
    origins: tuple[str, ...] = field(default=())

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def interim_dir(self) -> Path:
        return self.data_dir / "interim"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def has_reddit(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_key)

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.interim_dir, self.processed_dir):
            d.mkdir(parents=True, exist_ok=True)


def _env(name: str) -> str | None:
    """Read an env var, treating empty strings as absent.

    `.env.example` ships every key present-but-blank so you can see what exists
    without hunting through code. Without this, `KEY=` would read as the empty
    string and a provider would try to authenticate with it.
    """
    value = os.getenv(name, "").strip()
    return value or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process.

    `python-dotenv` is loaded if installed but is not a hard dependency -- in a
    deployed environment the variables are already in the process environment
    and there is no file to read.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    data_dir = Path(_env("STOCKS_DATA_DIR") or (PROJECT_ROOT / "data")).resolve()

    return Settings(
        data_dir=data_dir,
        cache_ttl_hours=int(_env("STOCKS_CACHE_TTL_HOURS") or 12),
        alphavantage_key=_env("ALPHAVANTAGE_API_KEY"),
        newsapi_key=_env("NEWSAPI_API_KEY"),
        newsapi_allow_nonproduction=(_env("NEWSAPI_ALLOW_NONPRODUCTION") or "").lower()
        in {"1", "true", "yes"},
        reddit_client_id=_env("REDDIT_CLIENT_ID"),
        reddit_client_secret=_env("REDDIT_CLIENT_SECRET"),
        reddit_user_agent=_env("REDDIT_USER_AGENT") or "stocks-research/0.1",
        fred_key=_env("FRED_API_KEY"),
        gemini_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
        # Defaults to on, and unsetting it is opt-in rather than opt-out. See
        # `ingest/gemini.py`: strict grounding is the only thing standing
        # between the panel and lookahead bias, so the safe value is the one
        # you get by doing nothing.
        gemini_strict_grounding=(_env("GEMINI_STRICT_GROUNDING") or "1").lower()
        not in {"0", "false", "no"},
        disable_factors=(_env("STOCKS_DISABLE_FACTORS") or "").lower() in {"1", "true", "yes"},
        force_synthetic=(_env("STOCKS_FORCE_SYNTHETIC") or "").lower() in {"1", "true", "yes"},
        origins=tuple(o.strip() for o in (_env("STOCKS_ORIGINS") or "").split(",") if o.strip()),
    )
