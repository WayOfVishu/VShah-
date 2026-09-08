"""
Scaffolded test for ai_analyzer.gemini_client — skipped until #AI-2 lands
(see docs/TODO.md).

The rule this file exists to enforce: **these tests must never call the real
Gemini API.** Not once. A test suite that makes network calls is slow, fails on
a train, burns free-tier quota you need for actual development, and — worst —
becomes a test you stop running. project-charter.md Section 10's mitigation for
the rate-limit risk says to cache responses during dev precisely so you are not
re-calling the API on every test run; a unit test should not be calling it even
the first time.

So everything here is built on a fake client. That constraint is also the
reason this module is worth testing at all: #AI-2 is not about Gemini, it is
about **retry and backoff logic**, and retry logic is exactly the kind of code
that looks right and is wrong. The interesting cases are all failure cases, and
a fake lets you produce failures on demand that would be almost impossible to
trigger deliberately against the live API.

The design question the fixture below cannot answer for you: `call_gemini()`
currently constructs nothing — it is handed a prompt and a schema, and
`get_client()` is a separate function. So how does a test substitute a fake
client? monkeypatching `gemini_client.get_client`, or adding an optional
`client=None` parameter that defaults to `get_client()`? The second is
dependency injection and is generally the cleaner answer; it also means
changing the signature you were handed, which is allowed. Decide, and note it —
this is the same "is the seam in the right place?" question test_system_info.cpp
raises about /proc parsing.
"""

import pytest

from ai_analyzer import gemini_client


class FakeGeminiError(Exception):
    """Stand-in for whatever the SDK actually raises on a 429.

    Design question 1 in gemini_client.py asks what that type really is — a
    distinct rate-limit exception, or a generic HTTP error you inspect. Until
    you have looked it up, this placeholder keeps the tests writable; once you
    know, replace it with the real type. Leaving this class in place after you
    know the answer would mean testing your retry logic against an exception the
    SDK never throws, which is worse than not testing it.
    """


@pytest.fixture
def failing_then_succeeding_client():
    """A fake client that raises FakeGeminiError the first N times it is called,
    then returns a canned response — the shape you need to prove that retry
    actually retries, and that it eventually stops."""

    class _Fake:
        def __init__(self, failures_before_success: int):
            self.failures_before_success = failures_before_success
            self.call_count = 0

        def generate(self, *args, **kwargs):
            self.call_count += 1
            if self.call_count <= self.failures_before_success:
                raise FakeGeminiError("429 rate limited")
            return {"summary": "ok", "causes": [], "fixes": [], "severity": "low"}

    return _Fake


@pytest.mark.skip(reason="ai_analyzer.gemini_client.call_gemini is not implemented yet — see docs/TODO.md #AI-2")
def test_retries_then_succeeds(failing_then_succeeding_client):
    # TODO once #AI-2 lands: wire a client that fails twice then succeeds, and
    # assert (a) call_gemini returns the successful response, and (b) the fake
    # was called exactly 3 times.
    #
    # Assert the count, not just the return value. A retry loop that swallows
    # the exception and returns on the first attempt would pass a
    # return-value-only assertion on a client that never failed — the count is
    # what proves the retry path was actually taken.
    pytest.fail("write me")


@pytest.mark.skip(reason="ai_analyzer.gemini_client.call_gemini is not implemented yet — see docs/TODO.md #AI-2")
def test_gives_up_after_the_attempt_limit(failing_then_succeeding_client):
    # TODO: a client that always fails. Assert call_gemini eventually raises
    # (or returns your chosen failure shape — design question 2) rather than
    # retrying forever, and that it made exactly the number of attempts you
    # decided on.
    #
    # "Retries forever" is the single most common bug in hand-written backoff,
    # and it does not show up in manual testing because you kill the process
    # before you notice. This test is the one that catches it.
    pytest.fail("write me")


@pytest.mark.skip(reason="ai_analyzer.gemini_client.call_gemini is not implemented yet — see docs/TODO.md #AI-2")
def test_backoff_actually_waits_between_attempts(monkeypatch):
    # TODO: assert the delays grow (if you chose exponential) rather than that
    # they exist.
    #
    # The mechanical problem: a real backoff sleeps, and a test that sleeps for
    # 1s + 2s + 4s is a test nobody runs twice. Monkeypatch time.sleep with a
    # recorder that appends the requested duration to a list and returns
    # immediately, then assert on that list. The suite stays instant and you
    # still get to check the schedule.
    #
    # Worth deciding while you are here: does your backoff have jitter? If it
    # does, assert on bounds rather than exact values — and if asserting on
    # bounds feels awkward, that is a hint about how you have structured the
    # delay calculation, not about the test.
    pytest.fail("write me")


@pytest.mark.skip(reason="ai_analyzer.gemini_client.call_gemini is not implemented yet — see docs/TODO.md #AI-2")
def test_non_rate_limit_errors_are_not_retried():
    # TODO: the case that separates a real implementation from a `try/except
    # Exception` wrapper. A 429 is transient and worth retrying; a 401 (bad API
    # key) or a malformed-request error will fail identically every time, and
    # retrying it five times with backoff just makes the user wait longer for
    # the same failure.
    #
    # Assert that a non-transient error surfaces immediately, with call_count
    # == 1. If your current design cannot tell the two apart, this test is the
    # reason to go back and read design question 1 again.
    pytest.fail("write me")


@pytest.mark.skip(reason="Caching is an open decision — see docs/TODO.md housekeeping and gemini_client.py design question 3")
def test_cached_response_avoids_a_second_call(tmp_path, monkeypatch):
    # TODO, only if you decide caching belongs in this module rather than the
    # CLI layer (design question 3 — netdiag.config.CACHE_DIR exists either
    # way). Call twice with the same prompt, assert the fake client was hit
    # once.
    #
    # If you decide caching belongs in the CLI layer instead, delete this test
    # and say so in the TODO — a skipped test for a decision you have already
    # made against is just litter.
    pytest.fail("write me")
