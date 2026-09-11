"""
Configuration for the Jira sync tool — reads credentials and site details out
of the environment.

This module is **built for you**, on the same principle as
Hardware-Check's `python/netdiag/config.py`: pulling values out of `os.environ`
is mechanical, and there is no REST concept hiding in it. The learning is in
`client.py`. Read this once so you know what is available, then move on.

Copy `.env.example` to `.env` and fill it in. Same mechanism as every other
project in this repo — Hardware-Check hides `GEMINI_API_KEY` this way, Stocks
does the same. One familiar pattern beats a clever second one.

`.env` is gitignored repo-wide. Verify that yourself rather than taking this
comment's word for it, and use the **exit code**, not the output:

    git check-ignore -q Tools/Jira-Sync/.env && echo ignored

`-v` prints the matching rule even when that rule is a *negation*, so reading
its output as "there was a match, therefore ignored" gives you the wrong answer
on exactly the files you most want to be sure about.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Module-level, matching netdiag/config.py. Without this, os.environ.get()
# below only sees variables already exported into the shell — the .env file
# would sit there being ignored, which looks identical to a wrong token.
load_dotenv()

# --- Site -------------------------------------------------------------------

# Your Atlassian site, e.g. "https://vshah.atlassian.net" — no trailing slash,
# no "/rest/api/3" suffix. client.py is responsible for building full URLs from
# this; keeping the base bare means one place decides the API version.
JIRA_SITE = os.environ.get("JIRA_SITE", "").rstrip("/")

# The project key issues get created under, e.g. "HWCK" or "STK". Jira project
# keys are uppercase and short; find yours in the URL of any issue on the board
# (the part before the dash in "HWCK-42").
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "")

# --- Credentials ------------------------------------------------------------

# The Atlassian account email — this is the *username* half of Basic auth. It
# is not secret, unlike the token.
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")

# An API token from https://id.atlassian.com/manage-profile/security/api-tokens
#
# This is a password-equivalent secret. Two consequences worth internalising
# now rather than after an incident:
#   - it never goes in a URL (URLs land in logs, shell history and referrer
#     headers), only in a header
#   - it never gets printed, even in a debug branch. See client.py's design
#     question about redaction — this is the single easiest way to leak a
#     credential and the hardest to notice, because the leak looks like a log
#     line you wrote on purpose.
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")

# --- Local paths ------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]

# The TODO.md files todo_parser.py reads tags out of. Add to this list as more
# projects grow scaffolds worth tracking on the board.
TODO_SOURCES = [
    REPO_ROOT / "Projects" / "Hardware-Check" / "docs" / "TODO.md",
    REPO_ROOT / "Projects" / "Stocks" / "docs" / "TODO.md",
    REPO_ROOT / "Projects" / "League-ML" / "docs" / "TODO.md",
]


def require(name: str) -> str:
    """Return a required config value, or raise with a message that says how to
    fix it rather than just which key was missing.

    Called at use time rather than import time so this module (and the tests)
    can be imported with no `.env` present — same reason
    netdiag.config.require_gemini_key() works the way it does.
    """
    value = globals().get(name, "")
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy Tools/Jira-Sync/.env.example to .env and "
            f"fill in {name}. For JIRA_API_TOKEN, generate one at "
            f"https://id.atlassian.com/manage-profile/security/api-tokens"
        )
    return value
