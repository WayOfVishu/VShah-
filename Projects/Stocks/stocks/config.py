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

# The market proxies for DS4. The S&P 500 is the index the SCL regression uses
# by default (Chapter 8 wants a broad-market proxy); NASDAQ and the Russell are
# carried as extra features because a tech name's systematic risk is much
# better described by the NASDAQ than by the S&P.
DEFAULT_INDEX_TICKERS = ("^GSPC", "^IXIC", "^RUT", "^VIX")

# FRED series for the macro side of DS5. DGS3MO is the risk-free rate every
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
        force_synthetic=(_env("STOCKS_FORCE_SYNTHETIC") or "").lower() in {"1", "true", "yes"},
        origins=tuple(o.strip() for o in (_env("STOCKS_ORIGINS") or "").split(",") if o.strip()),
    )
