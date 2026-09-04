"""Content loader.

All site copy lives in ``app/data/*.json`` rather than in markup, so the
frontend has exactly one source of truth and editing the site does not mean
editing HTML. Files are read once and cached; set ``PORTFOLIO_RELOAD=1`` while
writing content to re-read on every request.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
RELOAD = os.getenv("PORTFOLIO_RELOAD", "").strip() in {"1", "true", "yes"}


def _read(name: str) -> Any:
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"content file missing: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _read_cached(name: str) -> Any:
    return _read(name)


def load(name: str) -> Any:
    return _read(name) if RELOAD else _read_cached(name)


def profile() -> dict:
    return load("profile")


def experience() -> list[dict]:
    return load("experience")


def skills() -> list[dict]:
    return load("skills")


def education() -> dict:
    return load("education")


def projects() -> list[dict]:
    items = load("projects")
    return sorted(items, key=lambda p: p.get("order", 999))


def project(slug: str) -> dict | None:
    return next((p for p in projects() if p["slug"] == slug), None)


def summary() -> dict:
    """Everything the landing page needs, in one round trip.

    Case studies are stripped here — they are large, and only the project
    detail view needs them. One request paints the whole page.
    """
    lite = []
    for p in projects():
        item = {k: v for k, v in p.items() if k != "caseStudy"}
        item["hasCaseStudy"] = bool(p.get("caseStudy", {}).get("approach"))
        lite.append(item)

    return {
        "profile": profile(),
        "projects": lite,
        "experience": experience(),
        "skills": skills(),
        **education(),
    }
