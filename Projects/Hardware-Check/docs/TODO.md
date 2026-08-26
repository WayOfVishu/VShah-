# TODO — consolidated task list

Everything below is a stub somewhere in the repo (`NotImplementedError` on
the Python side, `std::logic_error` on the C++ side — see
`docs/project-charter.md` Section 18 for why the split falls where it
does). This file is the index; each module's own docstring/header comment
has the actual design questions and hints — read those in place, this is
just the tracker. Mapped to `docs/working-plan.md`'s weeks.

Check items off as you go (`- [x]`).

## Phase 1 — C++ core (target: weeks 3-4)

- [ ] **#SYS-1** `cpp/src/system_info.cpp` — `collect_system_snapshot()`.
  CPU/memory/disk telemetry via `/proc` + `statvfs()`. Do this before
  #MEM-1 if you want an early "it prints real JSON" win, or after if you'd
  rather get the harder module out of the way first — order doesn't matter
  functionally, they're independent.
- [ ] **#MEM-1** `cpp/src/memory_sandbox.cpp` + the four `MemorySandbox`
  methods declared in `cpp/include/sysdiag/memory_sandbox.hpp`. **The
  primary point of this entire project.** Budget real time here — this is
  not a "middle of the pack" TODO in difficulty, it's the whole reason the
  project exists. Run every demo under ASan AND Valgrind as you go (see
  README's "Memory-safety verification" section), not just once at the end.

## Phase 2 — Refactor (target: week 5)

- [ ] **#MEM-2** Refactor the Phase 1 raw-pointer sandbox to
  `std::unique_ptr`/`std::shared_ptr`. Not scaffolded on purpose — by this
  point you've written the raw-pointer version yourself, so you're the one
  who knows what it actually needs to hold onto. Keep the original
  raw-pointer version around somewhere (a git branch, or a second file) —
  Acceptance Criteria (`docs/project-charter.md` Section 13) wants a
  before/after writeup in the README, which needs an actual "before" to
  diff against.
- [ ] **#MEM-3** Write that before/after comparison in `README.md`'s
  Results section: what changed, why, and what running ASan/Valgrind
  against each version showed.

## Phase 3 — Python networking (target: weeks 6-7)

- [ ] **#NET-1** `python/netdiag/ping_probe.py` — `measure_ping()`.
- [ ] **#NET-2** `python/netdiag/dns_probe.py` — `measure_dns()`.
- [ ] **#NET-3** `python/netdiag/port_scan.py` — `scan_ports()`. Get a
  correct sequential version working before considering concurrency (see
  its docstring's design question 2).

## Phase 4 — Integration (target: week 8)

- [ ] **#NET-4** `python/netdiag/engine_runner.py` — `run_engine()`.
  Depends on #SYS-1/#MEM-1 (the binary needs to produce real output for
  this to be testable end-to-end) but can be written and unit-tested
  against the fake-engine fixture in `python/tests/test_engine_runner.py`
  before that lands.

## Phase 5 — Gemini integration (target: week 9)

- [ ] **#AI-1** `python/ai_analyzer/prompt_builder.py` — `build_prompt()`
  and the response schema (see its docstring, point (b)).
- [ ] **#AI-2** `python/ai_analyzer/gemini_client.py` — `call_gemini()`.
  Retry/backoff on rate limits. You will hit 429s during real testing on
  the free tier — this isn't a hypothetical.
- [ ] **#AI-3** `python/ai_analyzer/response_parser.py` — `parse_analysis()`.

## Phase 6 — Docs & polish (target: week 10)

- [ ] Fill in `README.md`'s "Results / known limitations" section with
  real numbers and real ASan/Valgrind output — no placeholders in the
  version anyone else reads.
- [ ] Confirm `python hwcheck.py` runs end-to-end on a clean checkout
  (fresh venv + fresh `cpp/build/`).
- [ ] Re-read Acceptance Criteria (`docs/project-charter.md` Section 13)
  and check off each one honestly.

## Phase 7 (later, not optional — see Open Decisions) — Desktop GUI

- [ ] Not started, not scaffolded. Revisit once Phases 1-6 are solid — see
  `docs/project-charter.md` Section 14, Open Decision #1.

## Housekeeping (do throughout, not a separate phase)

- [ ] If you add a field to `SystemSnapshot`/`SandboxBugReport` on the C++
  side, update `python/netdiag/schema.py`'s comments to match — the two
  sides only agree on the JSON contract because someone keeps them in sync
  by hand.
- [ ] Decide whether `ai_analyzer`'s Gemini responses get cached locally
  during dev (`netdiag.config.CACHE_DIR` exists for this) — see
  `gemini_client.py`'s design question 3.
