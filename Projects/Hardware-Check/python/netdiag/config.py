"""
Central configuration: paths and settings loaded from the environment.

Plumbing, not a learning exercise — written out in full so every other
module has one obvious place to pull settings from (mirrors the same
decision in league-ml/src/config.py, if you want a second example of the
pattern).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- paths ---------------------------------------------------------------
# REPO_ROOT = hardware-check/, regardless of where a script is invoked from.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

REPORTS_DIR = REPO_ROOT / "data" / "reports"
CACHE_DIR = REPO_ROOT / "data" / "cache"

# Where the compiled C++ binary lives. Overridable via .env because it
# differs depending on where you built it (native WSL2 path vs. anything
# else) — see .env.example.
SYSDIAG_ENGINE_PATH = REPO_ROOT / os.environ.get("SYSDIAG_ENGINE_PATH", "cpp/build/sysdiag_engine")

# --- Gemini ----------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")

# --- network probe defaults (project-charter.md Section 5.2) --------------
# Deliberately conservative default port range — "configurable, user-supplied
# range" per the spec, these are just what's used if the CLI caller doesn't
# override them. Keep in the unprivileged range (>1023) unless you have a
# specific reason to go lower and you've re-read Section 3's "no elevated
# privileges" boundary first.
DEFAULT_PORT_RANGE = (1024, 1124)
PING_COUNT = 4  # how many ICMP echoes to send per latency check


def require_gemini_key() -> str:
    """Return the Gemini API key, or raise a clear error if unset.

    Call this at the point a Gemini call is actually made — not at import
    time — so unrelated modules (e.g. the network probes) still work
    without a .env file.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and fill in "
            "a free key from https://aistudio.google.com/apikey"
        )
    return GEMINI_API_KEY


def ensure_data_dirs() -> None:
    """Create data/reports and data/cache if they don't exist yet (idempotent)."""
    for d in (REPORTS_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
