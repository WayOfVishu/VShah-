"""
Authenticated, rate-limited client for the Riot Games Match-V5 / League-V4 APIs.

# TODO (Phase 1 -- see docs/TODO.md #ING-2)
#
# The URL-building constants and endpoint paths below are just string
# formatting (mechanical), so they're written out for you. What's left is the
# actual request lifecycle: calling your RiotRateLimiter, handling non-200
# responses, and retrying with backoff. That's the Functional Requirement in
# project-charter.md Section 8:
#   "Ingestion must handle HTTP 429 responses with exponential backoff, not
#    crash or silently drop matches"
#
# Status codes worth handling deliberately (not just "if not 200: raise"):
#   200  -> success
#   404  -> not found (e.g. a match got deleted server-side) -- is this a
#           crash, a skip, or something else?
#   429  -> you got rate-limited anyway. Riot sends a `Retry-After` header --
#           should you trust your own rate limiter's math, or trust that
#           header when it's present? Why might they disagree?
#   5xx  -> Riot's problem, not yours. Worth retrying a few times with
#           backoff before giving up on a single match.
#
# "Exponential backoff" means: on retry N, wait roughly base * 2**N seconds
# (plus usually a little random jitter, to avoid many clients retrying in
# lockstep). Decide your own base and max-retries.
#
# This is the same problem as Hardware-Check's #AI-2 (gemini_client.py) and
# Jira-Sync's #JIRA-4 (client.py) -- three vendors, one pattern. Jira and Riot
# both send `Retry-After`; Gemini gives you less to go on. Whichever of the
# three you write second, compare them before extracting anything shared --
# see the through-line note in Tools/Jira-Sync/docs/TODO.md.
"""

import requests

from leagueml.config import RIOT_PLATFORM, RIOT_REGION, require_api_key
from leagueml.ingestion.rate_limiter import RiotRateLimiter

MATCH_V5_BASE = "https://{region}.api.riotgames.com/lol/match/v5"
LEAGUE_V4_BASE = "https://{platform}.api.riotgames.com/lol/league/v4"


class RiotClient:
    """Wraps the handful of Riot endpoints this project needs.

    match_id discovery in this project goes:
        League-V4 /challengerleagues/by-queue/{queue}  (or /entries/{queue}/{tier}/{division})
            -> entries, each carrying a puuid
        Match-V5 /matches/by-puuid/{puuid}/ids
            -> match_id list
        Match-V5 /matches/{matchId}
            -> full match detail JSON
        Match-V5 /matches/{matchId}/timeline
            -> per-minute frames + events (items, gold -- #FEAT-1, #FEAT-4)

    (v3) The draft had a Summoner-V4 hop in the middle -- summonerId -> puuid.
    Riot removed its summonerId/accountId endpoints on 2025-06-20 in favour of
    the PUUID equivalents, so that hop is gone and discovery is PUUID-first.
    Confirm on your first real call that a league entry actually carries a
    `puuid` key before building on it; if it doesn't, stop and re-read the
    League-V4 docs rather than reaching for the old endpoint.
    """

    def __init__(self, region: str = RIOT_REGION, platform: str = RIOT_PLATFORM) -> None:
        self.api_key = require_api_key()
        self.region = region
        self.platform = platform
        self.rate_limiter = RiotRateLimiter()

    def _headers(self) -> dict[str, str]:
        return {"X-Riot-Token": self.api_key}

    def _request(self, url: str, params: dict | None = None) -> dict | list:
        """Perform one rate-limited GET with retry/backoff on 429 and 5xx.

        TODO: this is the core of #ING-2 -- implement the retry loop here.
        Everything above (headers, URL building) is done for you; this
        method is the piece that actually satisfies Functional Requirement
        Section 8.
        """
        raise NotImplementedError("RiotClient._request() is not implemented yet -- see docs/TODO.md #ING-2")

    # --- match discovery -------------------------------------------------

    def get_league_entries(self, queue: str = "RANKED_SOLO_5x5", tier: str = "CHALLENGER") -> dict:
        """Fetch one apex league (CHALLENGER / GRANDMASTER / MASTER) -- a decent,
        if biased, seed pool of active accounts to pull matches from. See
        docs/TODO.md #ING-4 and #LML-2 for the seed-selection tradeoff."""
        url = f"{LEAGUE_V4_BASE.format(platform=self.platform)}/{tier.lower()}leagues/by-queue/{queue}"
        return self._request(url)

    def get_entries_by_division(
        self, queue: str = "RANKED_SOLO_5x5", tier: str = "GOLD", division: str = "I", page: int = 1
    ) -> list[dict]:
        """(v3) One page of entries below the apex tiers. The tool for not
        seeding from Challenger alone -- sample a few pages from several tiers
        and the dataset stops describing only the top 0.1% of players."""
        url = f"{LEAGUE_V4_BASE.format(platform=self.platform)}/entries/{queue}/{tier}/{division}"
        return self._request(url, params={"page": page})

    def get_match_ids_by_puuid(self, puuid: str, count: int = 100, start: int = 0, queue: int = 420) -> list[str]:
        url = f"{MATCH_V5_BASE.format(region=self.region)}/matches/by-puuid/{puuid}/ids"
        params = {"count": count, "start": start, "queue": queue}
        return self._request(url, params=params)

    # --- match detail ------------------------------------------------------

    def get_match(self, match_id: str) -> dict:
        """Full match detail (participants, final item slots, etc.)."""
        url = f"{MATCH_V5_BASE.format(region=self.region)}/matches/{match_id}"
        return self._request(url)

    def get_match_timeline(self, match_id: str) -> dict:
        """Minute-by-minute timeline (ITEM_PURCHASED events, participantFrames, etc.).

        Needed for leagueml/features/item_timing.py and frames.py -- the
        match-detail endpoint above only has *final* item slots and no gold
        curve at all. See those modules' docstrings for why this matters.
        """
        url = f"{MATCH_V5_BASE.format(region=self.region)}/matches/{match_id}/timeline"
        return self._request(url)
