"""
Thin wrapper around the google-genai SDK.

Client setup is built for you (mechanical — reading a key out of config and
constructing the SDK's Client object isn't a concept worth spending time
on). The retry/rate-limit handling around the actual API call is
TODO — see call_gemini() below.
"""

from google import genai

from netdiag import config


def get_client() -> genai.Client:
    """Construct a configured genai.Client. Raises if GEMINI_API_KEY is unset
    (via config.require_gemini_key(), called here rather than at import time
    so this module can be imported without a .env file present)."""
    api_key = config.require_gemini_key()
    return genai.Client(api_key=api_key)


# ============================================================================
# TODO (Phase 5, week 9 — docs/TODO.md #AI-2). Secondary learning objective
# (project-charter.md Section 2: "talking to a real external API with rate
# limits, error handling"). Functional requirement 5.3: "Handle rate limits
# and API errors gracefully (this will happen on the free tier — see
# Section 9)."
#
# You will hit HTTP 429 (rate limited) during real testing on the free tier
# — project-charter.md Section 9 puts it at roughly 5-15 requests/minute
# depending on model. That's not a hypothetical to handle "just in case",
# it's an expected, reproducible condition during normal development.
#
# Design questions:
#   1. What does the google-genai SDK actually raise on a 429 — is it a
#      distinct exception type you can catch specifically, or a generic
#      HTTP error you need to inspect the status code on? Check the SDK's
#      exception hierarchy before assuming.
#   2. Retry with backoff — fixed delay, or exponential? How many attempts
#      before giving up and surfacing the failure to the caller? (There's a
#      real project precedent for this exact shape of problem: compare
#      against league-ml/src/ingestion/riot_client.py's #ING-2 TODO in the
#      other repo in this workspace, if you want a second example of the
#      same design problem in a different SDK.)
#   3. project-charter.md Section 10's mitigation for this risk says "cache
#      responses locally during dev so you're not re-calling the API on
#      every test run". Where would that caching live — inside this
#      function, or as a decision the CLI layer makes before ever calling
#      this module? (netdiag/config.py already gives you CACHE_DIR if you
#      want it.)
# ============================================================================
def call_gemini(prompt: str, response_schema) -> str:
    """Call the Gemini API with `prompt`, constrained to `response_schema`
    (see prompt_builder.py's TODO for what that schema should look like).

    Returns the raw response text/object for response_parser.py to turn
    into the final structured dict — this function's job is just "get a
    response back, retrying sanely on transient failures", not parsing.
    """
    raise NotImplementedError("call_gemini() is not implemented yet — see docs/TODO.md #AI-2")
