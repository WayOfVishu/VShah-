"""
Central configuration: paths, constants, and secrets loaded from environment.

This file is plumbing, not a learning exercise -- it's written out in full so
every other module has one obvious place to pull settings from. Same decision
as Hardware-Check's `python/netdiag/config.py` and Jira-Sync's
`jira_sync/config.py`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a local .env file (gitignored) into the process environment.
# If .env doesn't exist yet, this is a no-op -- see .env.example for what to copy.
load_dotenv()

# --- paths -------------------------------------------------------------
# BASE_DIR = Projects/League-ML/, regardless of where a script is run from.
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STATIC_DIR = DATA_DIR / "static"
# Trained model weights (.pt) -- "checkpoint" in the deep-learning sense. The
# *ingestion* checkpoints from the draft live in the SQLite table
# `ingestion_checkpoints` instead (project-charter.md Section 12), so the
# directory name is free for the meaning PyTorch gives it.
CHECKPOINT_DIR = DATA_DIR / "checkpoints"

SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"

DB_PATH = BASE_DIR / os.environ.get("DB_PATH", "data/processed/league.db")

# --- Riot API ------------------------------------------------------------
RIOT_API_KEY = os.environ.get("RIOT_API_KEY")

# Regional routing (Match-V5, Account-V1) vs. platform routing (League-V4).
# See .env.example for the full explanation.
RIOT_REGION = os.environ.get("RIOT_REGION", "americas")
RIOT_PLATFORM = os.environ.get("RIOT_PLATFORM", "na1")

# Riot's official personal-key rate limits (project-charter.md Section 6).
# Your rate limiter (leagueml/ingestion/rate_limiter.py) must respect BOTH
# windows at once, not just the tighter-looking one.
RATE_LIMIT_SHORT = (20, 1)     # 20 requests per 1 second
RATE_LIMIT_LONG = (100, 120)   # 100 requests per 2 minutes (120s)

# --- patch (project-charter.md Section 13 -- patch drift) ---------------
# Two numbering schemes for the same patch, and the draft used the wrong one.
# Riot's patch notes call it "26.18" (year-based naming since 2025). Every
# technical surface this project touches -- Data Dragon's versions.json and
# Match-V5's info.gameVersion -- still uses the client numbering, "16.18.x".
# Asking Data Dragon for "26.16" returns HTTP 403 (checked 2026-09-10), so the
# draft's run_pipeline.py would have failed at step 2.
#
# 26.18 was live on 2026-09-10. It will be stale by the time ingestion starts;
# picking the patch then is docs/TODO.md #LML-3.
PATCH_LABEL = "26.18"                 # what the patch notes call it
TARGET_PATCH = "16.18"                # major.minor, as in info.gameVersion
DDRAGON_VERSION = f"{TARGET_PATCH}.1"  # Data Dragon's version string

SNAPSHOT_MINUTE = 10  # the item/gold snapshot the participant table is built at
FRAME_MINUTES = 15    # per-minute frames the sequence model sees (#FEAT-4, #DL-7)

# --- MVP data-size target (project-charter.md Section 13) ---
# A floor for the MVP, set before the models were networks. #EVAL-4's learning
# curve is what decides whether the networks need more.
TARGET_MATCH_COUNT_MIN = 2000
TARGET_MATCH_COUNT_MAX = 5000

# --- deep learning -------------------------------------------------------
# One seed for splits, weight initialisation and batch order. #EVAL-1's log
# needs it recorded: two runs differing by 0.01 AUC mean nothing if the seed
# differed too.
SEED = int(os.environ.get("LEAGUEML_SEED", "0"))

# "auto" picks CUDA when PyTorch can see a GPU, else CPU. CPU is fine at this
# scale -- thousands of matches, networks with thousands of parameters.
DEVICE = os.environ.get("LEAGUEML_DEVICE", "auto")


def require_api_key() -> str:
    """Return the Riot API key, or raise a clear error if it isn't configured.

    Call this at the point where you actually need to make a request -- not at
    import time -- so that unrelated modules (e.g. data_dragon, which needs no
    key) still work without a .env file.
    """
    if not RIOT_API_KEY:
        raise RuntimeError(
            "RIOT_API_KEY is not set. Copy .env.example to .env and fill in "
            "your personal key from https://developer.riotgames.com/"
        )
    return RIOT_API_KEY


def ensure_data_dirs() -> None:
    """Create the data/ subdirectories if they don't exist yet (idempotent)."""
    for d in (RAW_DIR, PROCESSED_DIR, STATIC_DIR, CHECKPOINT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def resolve_device() -> str:
    """Turn DEVICE ("auto" / "cpu" / "cuda") into a concrete torch device name.

    Imports torch lazily so modules that never touch a model -- the Data
    Dragon client, storage, ingestion -- import without PyTorch installed.
    """
    if DEVICE != "auto":
        return DEVICE
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"
