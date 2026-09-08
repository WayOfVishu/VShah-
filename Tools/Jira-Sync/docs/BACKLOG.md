# Consolidated backlog — every open TODO in the repo

One row per Jira task. Everything below is already written down somewhere in
the repo; this file is the flat index so you can work through it creating
issues without hopping between three documents.

**61 tasks: 6 setup, 21 Hardware-Check, 23 Stocks, 11 jira-sync.**

Source of truth stays in each project's own `docs/TODO.md` — that is where the
design questions, hints and reasoning live, and none of it is duplicated here.
Every row carries a `where` column pointing at the file and line so the Jira
description can just link there rather than copying prose that will drift.

Once `#JIRA-9` works, this file becomes redundant and the tool generates the
board instead. Until then it is done by hand, which is also the honest way to
find out whether the tool is worth building.

---

## Suggested Jira structure

| Jira concept | use it for | values |
|---|---|---|
| **Epic** | phase | `HW Phase 1`, `Stocks Phase 0`, … |
| **Label** | project | `hardware-check`, `stocks`, `jira-sync`, `setup` |
| **Label** | tag | the `#TAG`, lowercased — e.g. `mem-t1` |

That tag label is the one that matters: it is what `#JIRA-8` will match on to
avoid creating duplicates. Adding it by hand now means the tool has something
to find later, instead of you re-tagging 55 issues after the fact. If you skip
it, pick your idempotency strategy first and make sure it works with whatever
you did instead.

Issue type `Task` throughout, except where noted. Nothing here is a `Bug` —
none of it is broken, it is unbuilt.

---

## Setup — connect to Jira at all

Do these first; six tasks, most of them minutes. `#SETUP-5` and `#SETUP-6` are
the only ones with a real decision in them.

| tag | summary | where |
|---|---|---|
| `#SETUP-1` | Create the Jira project and record its key | Jira UI → note the key, e.g. `VS` |
| `#SETUP-2` | Generate an Atlassian API token | [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `#SETUP-3` | Create the `jira` venv and install its requirements | `Virtual Environments/Requirements/jira.txt` |
| `#SETUP-4` | Fill in `.env` from `.env.example` | `Tools/Jira-Sync/.env` |
| `#SETUP-5` | Decide: one Jira project for everything, or one per repo project? | see below |
| `#SETUP-6` | Decide the epic/label scheme and create the epics | see the table above |

**`#SETUP-4` is mostly done.** `.env` exists with `JIRA_EMAIL` filled in;
`JIRA_SITE` and `JIRA_PROJECT_KEY` are `REPLACE-ME` and come from `#SETUP-1`,
and `JIRA_API_TOKEN` is blank waiting for `#SETUP-2`.

Deliberately the same mechanism as the rest of the repo — Hardware-Check hides
`GEMINI_API_KEY` in a `.env`, Stocks does the same, and `config.py` calls
`load_dotenv()` at import like `netdiag/config.py` does. A second credential
format for one tool would be a small thing to have to remember forever.

Verify the ignore rule with the **exit code**, not the output:
`git check-ignore -q Tools/Jira-Sync/.env && echo ignored`. With `-v` it prints
the matching rule even when that rule is a *negation*, so reading its output as
"there was a match, therefore ignored" gives the wrong answer — a mistake worth
making once, cheaply, here rather than expensively later.

**`#SETUP-5` is the one worth thinking about.** One project with labels keeps a
single backlog and one board, and means cross-project sequencing (C++ before
Stocks) is visible in one place — which matches how you actually plan to work.
Separate projects give each repo project its own board and clean per-project
velocity, at the cost of three places to look. For a solo backlog of 55 items,
one project is almost certainly right; `config.JIRA_PROJECT_KEY` is a single
value today, so multiple projects also means changing the tool.

---

## Hardware-Check — 21 tasks

`Projects/Hardware-Check/docs/TODO.md`. Weeks are from `docs/working-plan.md`.

### Epic: HW Phase 1 — C++ core (weeks 3-4)

| tag | summary | where | depends on |
|---|---|---|---|
| `#SYS-1` | Implement `collect_system_snapshot()` — /proc + statvfs telemetry | TODO.md:14 | — |
| `#MEM-1` | Implement the four `MemorySandbox` demos with raw pointers | TODO.md:19 | — |
| `#MEM-T1` | Write the GoogleTest assertions for the sandbox and system info | TODO.md:25 | alongside `#SYS-1`/`#MEM-1` |

`#MEM-1` is the project's stated primary objective — budget real time, and run
ASan and Valgrind continuously rather than once at the end. `#MEM-T1` is what
turns charter §13 from a claim into evidence; do it *with* the implementation,
not after.

### Epic: HW Phase 2 — Refactor (week 5)

| tag | summary | where | depends on |
|---|---|---|---|
| `#MEM-2` | Refactor the sandbox to `unique_ptr`/`shared_ptr`, keeping the raw version | TODO.md:44 | `#MEM-1` |
| `#MEM-3` | Write the before/after refactor comparison in the README | TODO.md:52 | `#MEM-2` |

`#MEM-2` requires keeping the raw-pointer version around — a branch or a second
file. `#MEM-3` needs an actual "before" to diff against, so do not delete it.

### Epic: HW Phase 3 — Python networking (weeks 6-7)

| tag | summary | where | depends on |
|---|---|---|---|
| `#NET-1` | Implement `measure_ping()` | TODO.md:58 | — |
| `#NET-2` | Implement `measure_dns()` | TODO.md:59 | — |
| `#NET-3` | Implement `scan_ports()` — sequential first, concurrency after | TODO.md:60 | — |

### Epic: HW Phase 4 — Integration (week 8)

| tag | summary | where | depends on |
|---|---|---|---|
| `#NET-4` | Implement `run_engine()` — subprocess the C++ binary, parse its JSON | TODO.md:66 | `#SYS-1`, `#MEM-1` |

Testable against the fake-engine fixture before the real binary works, so it
can start earlier than the dependency suggests.

### Epic: HW Phase 5 — Gemini integration (week 9)

| tag | summary | where | depends on |
|---|---|---|---|
| `#AI-1` | Build the prompt and define the response schema | TODO.md:74 | — |
| `#AI-2` | Implement `call_gemini()` with retry/backoff on 429 | TODO.md:76 | `#AI-1` |
| `#AI-3` | Implement `parse_analysis()` | TODO.md:79 | `#AI-1` |
| `#AI-T1` | Write the assertions for the three `ai_analyzer` test files | TODO.md:80 | `#AI-1`–`#AI-3` |

`#AI-2` is the same problem as `#JIRA-4`. Whichever you write second, compare
them — see the through-line note in `Tools/Jira-Sync/docs/TODO.md`.

### Epic: HW Phase 6 — Docs & polish (week 10)

| tag | summary | where |
|---|---|---|
| *(untagged)* | Fill in the README's Results / known-limitations with real numbers | TODO.md:97 |
| *(untagged)* | Confirm `hwcheck.py` runs end-to-end on a clean checkout | TODO.md:100 |
| *(untagged)* | Confirm both suites pass clean — pytest, and ctest with and without ASan | TODO.md:102 |
| *(untagged)* | Re-read charter §13 acceptance criteria and check each off honestly | TODO.md:108 |

### Epic: HW Phase 7 — Desktop GUI (later, not optional)

| tag | summary | where |
|---|---|---|
| *(untagged)* | Scaffold and build the desktop GUI — revisit after Phases 1-6 | TODO.md:113 |

Charter §14 Open Decision 1: confirmed as a real end goal, deferred past the
12-week window. Qt 6 is the default if you want to lock the framework early.
Worth creating as a single placeholder issue now and splitting when you reach
it — not breaking down further today.

### Epic: HW Housekeeping (throughout)

| tag | summary | where |
|---|---|---|
| *(untagged)* | Keep `schema.py`'s comments in sync when C++ struct fields change | TODO.md:118 |
| *(untagged)* | Decide whether Gemini responses get cached locally during dev | TODO.md:122 |
| *(untagged)* | Resolve the four dangling `league-ml` cross-references | TODO.md:125 |

The `league-ml` one has a decision attached: build that project under that name
and the references become real, or strip them. It connects to the LoL project
you have planned.

---

## Stocks — 23 tasks

`Projects/Stocks/docs/TODO.md`. Ordered by information gained per hour, not
difficulty — keep that ordering when you build the board.

### Epic: Stocks Phase 0 — somewhere to put the answers

| tag | summary | where |
|---|---|---|
| `#ML-LOG` | Build an experiment log — nothing currently persists results | TODO.md:33 |
| `#ML-LOG-b` | Log the leakage canary result on every run | TODO.md:78 |

Do these before Phase 1. Every Phase 1 item is a comparison, and right now
every result scrolls off the terminal and is gone.

### Epic: Stocks Phase 1 — before you model anything

| tag | summary | where | depends on |
|---|---|---|---|
| `#ML-3` | Add the zero baseline and trailing-return baseline | TODO.md:92 | `#ML-LOG` |
| `#ML-0` | Test whether Gemini sentiment beats the VADER lexicon | TODO.md:98 | `#ML-LOG` |
| `#ML-0b` | Measure whether strict grounding costs accuracy | TODO.md:107 | `#ML-LOG` |
| `#ML-6` | Run the numeric / text / both ablation | TODO.md:116 | `#ML-LOG` |
| *(untagged)* | Run the leakage canary — `py run.py demo`, expect R² ≈ 0 | TODO.md:121 | — |

`#ML-3` is the single most important comparison in the project: if nothing
beats predict-zero, no tuning will fix it. `#ML-0` decides whether the Gemini
API bill buys anything. On `#ML-0b`, a much better *ungrounded* score is
lookahead bias, not skill — do not read it as a reason to ship ungrounded.

### Epic: Stocks Phase 2 — make the pipeline fit the problem

| tag | summary | where |
|---|---|---|
| `#ML-1` | Turn on `sublinear_tf` for the TF-IDF vectorizers | TODO.md:128 |
| `#ML-2` | Tune `svd_components` from the explained-variance knee | TODO.md:131 |
| `#ML-4` | Try `SelectKBest` or raw sparse Ridge instead of SVD | TODO.md:134 |
| `#ML-5` | Add exponential-decay sample weights on `meta_as_of` | TODO.md:137 |

### Epic: Stocks Phase 3 — change the question

| tag | summary | where |
|---|---|---|
| `#ML-8` | Predict the Chapter 8 residual instead of the raw return | TODO.md:144 |
| `#ML-10` | Add quantile regression for an honest interval | TODO.md:150 |
| `#ML-9` | Fit separate models at 1/5/10/21-day horizons | TODO.md:155 |
| `#ML-7` | Try `target_kind="direction"` and compare against the regressor | TODO.md:159 |

`#ML-8` is flagged as the strongest single idea on the list.

### Epic: Stocks Phase 4 — the interesting version

| tag | summary | where | depends on |
|---|---|---|---|
| `#ML-11` | Build a sequence model (LSTM/GRU/temporal CNN) over raw bars | TODO.md:164 | solid tabular baseline |
| *(untagged)* | Switch sentiment to FinBERT | TODO.md:168 | `#ML-6` showing text signal |
| *(untagged)* | Train a cross-sectional model and rank a universe | TODO.md:171 | — |

`#ML-11` is only interesting once there is a number to beat — it is also the
closest thing in this repo to the LoL project's planned deep-learning work, so
doing it first gives you a baseline for that.

### Epic: Stocks — non-ML work

| tag | summary | where | depends on |
|---|---|---|---|
| *(untagged)* | Build the frontend — charter §8 | TODO.md:202 | — |
| *(untagged)* | Add a job queue for `/api/predict` | TODO.md:209 | a model worth serving |
| *(untagged)* | Harden `_name_variants` with a real entity list or NER | TODO.md:212 | `#ML-0b` showing a large spread |
| *(untagged)* | Extract article bodies properly with `trafilatura` | TODO.md:220 | `#ML-6` showing text signal |
| *(untagged)* | Expand `resolve.ALIASES` or lean on Yahoo search | TODO.md:223 | — |

Four of these five are explicitly conditional. Create them, but consider a
`blocked` or `conditional` label so they do not read as committed work — three
of them should be *cancelled* if the Phase 1 experiments come back negative,
and that is a good outcome, not a failure.

---

## jira-sync — 11 tasks

`Tools/Jira-Sync/docs/TODO.md`. Small and finishable; do not let it grow.

### Epic: Jira Phase 1 — no network yet

| tag | summary | where |
|---|---|---|
| `#JIRA-10` | Parse one TODO.md into tagged items | TODO.md:62 |
| `#JIRA-11` | Parse every configured source, handle tag collisions | TODO.md:68 |
| `#JIRA-6` | Implement `to_adf()` — write the test first | TODO.md:70 |

Start here — no credentials needed, so `#SETUP-1`–`#SETUP-4` are not blockers.

### Epic: Jira Phase 2 — the actual exercise

| tag | summary | where | depends on |
|---|---|---|---|
| `#JIRA-5` | Implement `whoami()` — the auth smoke test | TODO.md:75 | `#SETUP-2`, `#SETUP-4` |
| `#JIRA-1` | Basic auth and one working GET | TODO.md:80 | `#SETUP-4` |
| `#JIRA-2` | One request helper with status codes handled meaningfully | TODO.md:84 | `#JIRA-1` |
| `#JIRA-3` | Pagination via `nextPageToken` on `/search/jql` | TODO.md:90 | `#JIRA-2` |
| `#JIRA-4` | Retry and backoff on 429, honouring `Retry-After` | TODO.md:97 | `#JIRA-2` |

`#JIRA-3` is where the trap lives: `/rest/api/3/search` was removed after
1 Aug 2025 and most examples you will find are wrong.

### Epic: Jira Phase 3 — make it do something

| tag | summary | where | depends on |
|---|---|---|---|
| `#JIRA-7` | Implement `create_issue()` — fields nesting and ADF | TODO.md:103 | `#JIRA-6`, `#JIRA-2`, `#SETUP-1` |
| `#JIRA-8` | Implement `find_issue_for_tag()` and pick a matching strategy | TODO.md:105 | `#JIRA-3` |
| `#JIRA-9` | Implement `sync_todos()`, dry-run by default | TODO.md:108 | `#JIRA-7`, `#JIRA-8`, `#JIRA-11` |

---

## Cross-project sequencing

Your stated order is C++ refresher → Hardware-Check → Stocks, with the LoL
project after. Two things cut across it:

**jira-sync Phase 1 needs no credentials and no C++.** `#JIRA-10`, `#JIRA-11`
and `#JIRA-6` are pure functions with tests already scaffolded — a reasonable
warm-up on a day when the C++ refresher has not clicked yet.

**Stocks Phase 0 + `#ML-3` is an afternoon and gates 13,664 lines.** It does
not need the C++ work to finish and it answers whether Stocks is a portfolio
piece or a deletion. Running it before starting Hardware-Check's Phase 1 costs
one afternoon and could remove a whole project from this backlog — which is
worth more than the afternoon.

Everything else follows the phases as written.

---

## Counting note

55 of these 61 already existed and are reproduced here; the 6 `#SETUP-*` rows
are new and exist only in this file. If you want them tracked in the same place
as the rest, they belong in `Tools/Jira-Sync/docs/TODO.md` — but they are
one-time account setup rather than code, so leaving them here is defensible.

**16 of the 55 existing items are untagged** — 8 in Hardware-Check, 8 in
Stocks, 0 in jira-sync. They cannot be matched idempotently by `#JIRA-8`, so
either give them tags in the source TODO before syncing, or accept that those
issues get created once by hand and are never reconciled. Tagging them is maybe
twenty minutes and makes the tool's job simpler — worth doing before `#JIRA-9`
rather than after.

Line numbers are accurate as of writing and **will drift** the moment you edit
a TODO file. They are a convenience for finding the item today, not a
reference to encode into Jira — the tag is the durable identifier, which is the
whole reason `#JIRA-8` matches on it.
