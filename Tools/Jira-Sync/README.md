# jira-sync

A small tool that reads the `#TAG` items out of this repo's `TODO.md` files and
creates matching issues on a Jira board — written against the Jira Cloud REST
API v3 **by hand**, with no Jira SDK.

That last part is the point. There are libraries that would do this in twenty
lines; using one would produce a working tool and teach nothing. The scaffold
here follows the same split as `Projects/Hardware-Check` and `Projects/Stocks`:
the mechanical parts are built, and the parts with a concept in them are stubs
with the design questions attached.

```
# venv lives with the others, per repo convention
cd "Virtual Environments"
py -m venv jira && ./jira/Scripts/python.exe -m pip install -r Requirements/jira.txt

cd ../Tools/Jira-Sync
pytest                        # 26 tests, all skipped until you write them
```

Get an API token from
<https://id.atlassian.com/manage-profile/security/api-tokens>.

### Credentials

`cp .env.example .env`, then fill it in. Four keys: `JIRA_SITE`,
`JIRA_PROJECT_KEY`, `JIRA_EMAIL`, `JIRA_API_TOKEN`.

Same mechanism as everywhere else in this repo — Hardware-Check hides
`GEMINI_API_KEY` in a `.env`, Stocks does the same. `config.py` calls
`load_dotenv()` at import, exactly like `netdiag/config.py`.

`.env` is covered by the repo-wide rule. Check it with the **exit code**, not
the output:

```
git check-ignore -q Tools/Jira-Sync/.env && echo ignored
```

`-v` prints the matching rule even when that rule is a negation, so its output
is not a reliable answer to "is this ignored?".

---

## What is built, and what is not

| file | state |
|---|---|
| `jira_sync/config.py` | **built** — env loading, no REST concept in it |
| `jira_sync/client.py` | **stub** — auth, requests, pagination, retry. The exercise. |
| `jira_sync/issues.py` | **stub** — ADF, issue creation, idempotency |
| `jira_sync/todo_parser.py` | **stub** — pure function, no network. Start here. |
| `tests/` | scaffolded, skipped, fixtures real |

Work order and reasoning: [`docs/TODO.md`](docs/TODO.md).

---

## Two things that will cost you an afternoon if nobody says them first

Both are verified against Atlassian's current documentation, and both are cases
where the answer you will find by searching is out of date or absent.

**1. The search endpoint changed.** `/rest/api/3/search` was deprecated and
stopped serving after **1 August 2025**. The replacement is
`/rest/api/3/search/jql`, and it paginates with an opaque **`nextPageToken`**
rather than a `startAt` offset. Most tutorials, most Stack Overflow answers,
and a good deal of older library code still use the old scheme.

The semantic difference is worth understanding rather than just patching
around: an offset asks the server to "skip N rows", so concurrent writes shift
the window and you can see a row twice or miss one. A token encodes a position
in a specific result set, so page boundaries stay stable.

**2. v3 requires ADF for rich text, and fails silently without it.**
`description` and `comment` expect an Atlassian Document Format JSON document,
not a string. Passing a plain string will *either* 400 *or* — the bad case —
succeed while saving an **empty** field. The issue gets created, your script
reports success, and the description is blank until you open the board.

v2 accepted plain text with wiki markup, which is why every older example
passes a string and why copying one produces a silent bug rather than an error.

---

## Why REST by hand rather than the Atlassian MCP server

Atlassian ships an official remote MCP server (`https://mcp.atlassian.com/v1/mcp/authv2`,
OAuth, free tier included) that would connect Jira to Claude directly with no
code. For *using* Jira from an assistant, that is the better tool and it is
worth setting up separately.

It is the wrong tool for this, because the goal is the REST experience, not the
Jira access. Authentication, status-code semantics, pagination and rate-limit
handling are the transferable skills; an MCP server exists precisely to hide
all four.

---

## The pattern this is the third instance of

`#JIRA-4` — retry and backoff on HTTP 429 — is the same problem as
`gemini_client.py`'s `#AI-2` and the `#ING-2` TODO referenced from it. Three
vendors, three SDK situations, one problem.

Jira differs from the other two in a way that matters: it sends a
**`Retry-After`** header, so the server tells you exactly how long to wait.
Exponential backoff is what you do with no information; honouring `Retry-After`
is what you do when you have some. A client that ignores it and backs off
exponentially anyway is both slower and ruder.

Worth writing at least twice before extracting anything shared — after one
instance you are guessing which parts generalise, after two you know.

---

## Results

<!-- Once #JIRA-9 runs for real: how many issues it created, what the matching
     strategy was, and what broke the first time. The "what broke" line is the
     one worth writing — it is the only part of this README that will not be
     obvious from the code. -->
