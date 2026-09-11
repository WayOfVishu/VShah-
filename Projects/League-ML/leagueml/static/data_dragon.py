"""
Client for Riot's Data Dragon CDN -- static champion/item/patch metadata.

No API key, no rate limit, no rate-limit-window math: this is the "uber
simple" end of the ingestion work, so it's fully implemented. Use it as a
worked example of what a clean, docstring'd requests-based client looks like
before you write the much trickier authenticated + rate-limited one in
leagueml/ingestion/riot_client.py.

Version strings here are the *client* numbering ("16.18.1"), not the patch
notes' year numbering ("26.18") -- see config.py's patch section for why the
difference matters.
"""

import json
from pathlib import Path
from typing import Any

import requests

from leagueml.config import STATIC_DIR, ensure_data_dirs

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"


def get_latest_version() -> str:
    """Return the most recent version string Data Dragon knows about, e.g. "16.18.1".

    Note: this is Data Dragon's own latest version, which may be ahead of or
    behind config.DDRAGON_VERSION. For this project you almost always want to
    pass DDRAGON_VERSION explicitly to the functions below rather than relying
    on "latest", so your dataset stays pinned to one patch.
    """
    resp = requests.get(f"{DDRAGON_BASE}/api/versions.json", timeout=10)
    resp.raise_for_status()
    versions: list[str] = resp.json()
    return versions[0]


def get_champions(version: str, locale: str = "en_US") -> dict[str, Any]:
    """Fetch the full champion.json payload for a given version."""
    url = f"{DDRAGON_BASE}/cdn/{version}/data/{locale}/champion.json"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_items(version: str, locale: str = "en_US") -> dict[str, Any]:
    """Fetch the full item.json payload for a given version."""
    url = f"{DDRAGON_BASE}/cdn/{version}/data/{locale}/item.json"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def save_static_data(version: str, out_dir: Path = STATIC_DIR) -> None:
    """Download champions + items for `version` and cache them to disk as JSON.

    Re-running this is cheap and safe (Data Dragon has no rate limit), so
    `py run.py pipeline` just calls it every time rather than trying to be
    clever about staleness checks.
    """
    ensure_data_dirs()
    champions = get_champions(version)
    items = get_items(version)

    (out_dir / f"champions_{version}.json").write_text(
        json.dumps(champions, indent=2), encoding="utf-8"
    )
    (out_dir / f"items_{version}.json").write_text(
        json.dumps(items, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    # Quick manual smoke test: `python -m leagueml.static.data_dragon`
    latest = get_latest_version()
    print(f"Latest Data Dragon version: {latest}")
    save_static_data(latest)
    print(f"Saved champions_{latest}.json and items_{latest}.json to {STATIC_DIR}")
