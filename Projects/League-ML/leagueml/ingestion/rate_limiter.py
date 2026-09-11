"""
Rate limiter for the Riot API personal key.

# TODO (Phase 1 -- see docs/TODO.md #ING-1)
#
# This is the single most important piece of the ingestion module, and it's
# also a real, transferable software engineering skill (any API client you
# write in a job will need something like this) -- so it's left for you to
# build rather than handed to you.
#
# Constraints you must satisfy AT THE SAME TIME (leagueml/config.py has both):
#   - RATE_LIMIT_SHORT = 20 requests / 1 second
#   - RATE_LIMIT_LONG  = 100 requests / 120 seconds
#
# Note the long window is the tighter real constraint on sustained throughput
# (100 req / 2min = 50 req/min average), even though the short window looks
# scarier at a glance. Your design needs to satisfy both, not just whichever
# one you noticed first.
#
# Design questions worth sitting with before you write any code:
#   1. What do you need to remember about past requests to know whether a new
#      one is currently allowed? (Hint: think about what becomes irrelevant
#      once enough time has passed -- how do you get rid of it cheaply?)
#   2. Given "not allowed right now", how do you compute exactly how long to
#      sleep -- not too little (you'll get a 429 anyway), not too much
#      (you're wasting the ~40 min/1000-match budget from charter Section 6)?
#   3. Where does this object live relative to RiotClient? One rate limiter
#      shared across every request, or one per client instance? What breaks
#      if you get that wrong?
#   4. (v3) Riot's responses carry headers describing the limits and your
#      current usage of them -- look for `X-App-Rate-Limit` and
#      `X-App-Rate-Limit-Count` on a real response before designing around
#      them, and note there are per-endpoint *method* limits too. Hard-coded
#      config values, or trust the headers? The same question #ING-2 asks
#      about `Retry-After`.
#
# Suggested research terms (not a spec, just where to start reading):
#   "sliding window rate limiter", "token bucket algorithm"
#
# Once ingestion/riot_client.py exists, add a unit test in
# tests/test_rate_limiter.py that doesn't require real network calls -- e.g.
# assert that N+1 calls in a tight loop take at least the expected sleep time,
# using time.monotonic() before/after rather than mocking the clock (simpler
# to reason about correctly as a first test).
"""


class RiotRateLimiter:
    """Enforces Riot's personal-key rate limits before a request is sent.

    Expected usage from riot_client.py:

        limiter = RiotRateLimiter()
        ...
        limiter.wait_if_needed()   # blocks (time.sleep) if necessary
        response = requests.get(...)
        limiter.record_request()  # note that a request was just sent
    """

    def __init__(self) -> None:
        # TODO: what data structure do you want here? (see design question 1)
        raise NotImplementedError("RiotRateLimiter is not implemented yet -- see docs/TODO.md #ING-1")

    def wait_if_needed(self) -> None:
        """Block (via time.sleep) until a new request is safe to send."""
        raise NotImplementedError("see docs/TODO.md #ING-1")

    def record_request(self) -> None:
        """Record that a request was just made, for future rate calculations."""
        raise NotImplementedError("see docs/TODO.md #ING-1")
