"""
Unit tests for leagueml/ingestion/rate_limiter.py.

# TODO (see docs/TODO.md #ING-1)
#
# These are skipped until RiotRateLimiter is implemented -- remove the
# pytest.mark.skip lines as you go, and add whatever additional cases your
# design needs. A no-network test is deliberately possible here: just call
# wait_if_needed()/record_request() in a tight loop and check elapsed time
# with time.monotonic(), no real HTTP requests required.
"""

import time

import pytest

from leagueml.ingestion.rate_limiter import RiotRateLimiter


@pytest.mark.skip(reason="TODO: implement RiotRateLimiter first -- see docs/TODO.md #ING-1")
def test_allows_requests_under_the_limit_without_blocking():
    limiter = RiotRateLimiter()
    start = time.monotonic()
    for _ in range(5):
        limiter.wait_if_needed()
        limiter.record_request()
    elapsed = time.monotonic() - start
    # TODO: assert elapsed is small (well under 1 second) -- 5 requests is
    # comfortably under both the short and long window limits.


@pytest.mark.skip(reason="TODO: implement RiotRateLimiter first -- see docs/TODO.md #ING-1")
def test_blocks_once_short_window_limit_is_hit():
    limiter = RiotRateLimiter()
    # TODO: send enough requests to exceed RATE_LIMIT_SHORT, then assert the
    # next wait_if_needed() call actually blocks for a meaningful amount of
    # time (use time.monotonic() before/after, not a hardcoded sleep count).
