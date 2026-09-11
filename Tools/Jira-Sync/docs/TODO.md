# TODO — Jira sync

What was built for you, and what is deliberately left open. Tags match the
`#JIRA-n` comments in `jira_sync/`.

> **Looking for the whole repo's backlog?** [`BACKLOG.md`](BACKLOG.md) is the
> flat index of all 88 tasks across Hardware-Check, Stocks, League-ML and this
> tool, one row per Jira issue, plus the six `#SETUP-*` account tasks. This
> file stays the build plan for the tool itself.

This is a **tool**, not a project — deliberately small, and scoped to teach one
thing: talking to a REST API by hand. It has no charter and no phase plan
because it should be finished in days, not weeks. If it starts growing a
roadmap, that is a signal to stop, not to write one.

---

## Status

| area | state |
|---|---|
| config / env loading | **done** — mechanical, no REST concept in it |
| the HTTP client | **yours** — `#JIRA-1..5`, the whole point |
| ADF + issue operations | **yours** — `#JIRA-6..9` |
| TODO.md parsing | **yours** — `#JIRA-10..11`, no network, start here |
| tests | scaffolded and skipped — assertions yours |
| CLI entry point | not scaffolded, not needed until the rest works |

---

## What it will actually sync, today

Measured from the three source files as they stand:

| source | tagged items | total items |
|---|---|---|
| Hardware-Check | 13 | 21 |
| Stocks | 15 | 23 |
| League-ML | 27 | 27 |
| **total** | **55** | **71** |

Tag prefixes in use: `#ML` (15), `#DL` (8), `#AI` (4), `#MEM` (4), `#NET` (4),
`#ING` (4), `#FEAT` (4), `#EVAL` (4), `#LML` (4), `#REC` (3), `#SYS` (1).

League-ML was added 2026-09-10. It uses Stocks' `**#TAG · Title.**` format and
tags every item, so it adds rows without adding a parsing case.

Things fall out of that table, and they are design decisions, not bugs:

- **16 items have no tag** — Hardware-Check's Phase 6/7 entries, Stocks'
  frontend and "non-ML work" items. They cannot be matched idempotently, which
  is why `#JIRA-10` design question 3 asks whether to skip them. 23% of the
  backlog is a big enough share that "skip silently" is the wrong answer;
  skip-and-report is probably right.
- **Not every tag ends in a number.** `#ML-LOG` and `#ML-LOG-b` are real tags in
  Stocks. The obvious regex — `#[A-Z]+-\d+` — silently drops both, and drops
  them *quietly*, because a parser that finds 26 of 28 items looks like it
  works. Whatever pattern you write, run it against the real files and check
  the count against this table before trusting it.
- **Continuation-line indentation differs between the two files.**
  Hardware-Check wraps with 2 spaces, Stocks with 6. Both start their items at
  column 0, so anchoring on `^- \[` is fine — but any logic that decides "this
  line continues the previous item" by matching a specific indent width will
  work on one file and fail on the other.

## Order

Not by difficulty — by how much each one de-risks the next.

### Phase 1 — no network yet

- [ ] **#JIRA-10 · Parse one TODO.md.** Pure function, fully testable, zero
      credentials. Doing this first means that when the HTTP layer misbehaves
      you are debugging one new thing instead of two.
      Three traps are documented in `todo_parser.py` and each has a test
      waiting in `tests/test_todo_parser.py`: cross-references that look like
      tags, multi-line items, and `- [x]`.
- [ ] **#JIRA-11 · Parse every source.** Thin wrapper. Read its note on tag
      collisions across projects before assuming it is trivial.
- [ ] **#JIRA-6 · `to_adf()`.** The other pure function. Write the test first —
      the correct output is fully specified, so there is no excuse not to.

### Phase 2 — the actual exercise

- [ ] **#JIRA-5 · `whoami()`.** Out of order on purpose. Thirty seconds of work,
      hits `/rest/api/3/myself`, and becomes the first thing you run every time
      something is "not working". Usually the answer is the token, the `.env`,
      or the site URL — and finding that out in five seconds beats reasoning
      carefully about the wrong endpoint.
- [ ] **#JIRA-1 · Auth + one working GET.** Basic auth: base64 of
      `email:api_token` in an `Authorization: Basic` header. Decide whether to
      hand-roll the encoding once or use `requests`' `auth=` from the start —
      and note the timeout question, which is the one that bites in production.
- [ ] **#JIRA-2 · One request helper, status codes handled.** The full mapping
      is in `client.py`. The portable knowledge in this whole tool is mostly
      here: which codes are retryable, which are permanent, and why Jira
      returns 404 for issues you lack permission on.
      Includes the security assertion — no `Authorization` value in any error
      message or log line.
- [ ] **#JIRA-3 · Pagination.** **Read `client.py`'s trap section first.**
      `/rest/api/3/search` was removed after 1 Aug 2025; the replacement is
      `/rest/api/3/search/jql` paginating on an opaque `nextPageToken`, not
      `startAt`. Most tutorials and older library code you find are wrong now.
      The test that matters is `test_short_page_with_a_token_still_continues` —
      the failure it catches otherwise shows up as "the sync only created half
      my issues", weeks later.
- [ ] **#JIRA-4 · Retry and backoff on 429.** The third time you have written
      this in this repo (see below). Jira sends `Retry-After`, so this one can
      be better than a blind exponential guess.

### Phase 3 — make it do something

- [ ] **#JIRA-7 · `create_issue()`.** Everything nests under `fields`.
      `summary` is a plain string and `description` is ADF, in the same object.
- [ ] **#JIRA-8 · `find_issue_for_tag()`.** The read half of idempotency.
      Four matching strategies are laid out in `issues.py`; pick one and write
      down what happens when the mapping is wrong.
- [ ] **#JIRA-9 · `sync_todos()`.** Dry-run by default. Read its open question
      about checked-off items before deciding this should be bidirectional —
      there is a real argument that create-only is the correct scope.

---

## The through-line worth noticing

`#JIRA-4` is the **third** instance of one problem in this repo:

| where | API | status |
|---|---|---|
| `Hardware-Check/python/ai_analyzer/gemini_client.py` `#AI-2` | Gemini | open |
| `Projects/League-ML/leagueml/ingestion/riot_client.py` `#ING-2` | Riot | open (scaffolded 2026-09-10) |
| `Tools/Jira-Sync/jira_sync/client.py` `#JIRA-4` | Jira | open |

Three vendors, one problem. That repetition is what "I know REST" actually
means — rate limiting, pagination and status-code semantics are the portable
part; endpoint names are disposable.

Worth doing at least twice before deciding whether a shared helper is
appropriate. Extracting a common retry utility after one instance is guessing;
after two you know which parts genuinely differ. (Jira's `Retry-After` versus
Gemini's blind backoff is exactly such a difference, and it is the reason a
naive shared abstraction would be worse than two separate implementations.)

---

## Deliberately not done, and why

- **A CLI entry point.** Nothing to drive until `sync_todos()` works. Add it
  when the tool does something, not before.
- **OAuth 3LO.** Correct for an app acting on behalf of other users; pure
  overhead for a single-user script against your own site. API token over
  Basic is the right tool here, not a shortcut.
- **Writing back to TODO.md.** Editing source files from a sync tool is a
  bigger commitment than it looks — it means the tool can corrupt the thing it
  reads. One-way is the safe default and possibly the correct permanent scope.
- **Caching issue lookups.** Premature. Revisit if a sync takes long enough to
  annoy you, which at ~40 items it will not.
