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
- [ ] **#MEM-T1** `cpp/tests/test_memory_sandbox.cpp` and
  `cpp/tests/test_system_info.cpp` — the assertions. The GoogleTest target is
  wired in `cpp/CMakeLists.txt` (behind `-DBUILD_TESTING=ON`) and both files
  exist with every test body empty: the harness is plumbing, the assertions are
  the exercise. Do these *alongside* #SYS-1/#MEM-1, not after — a test written
  afterwards tends to assert whatever the code already happens to do.
  **This is the TODO that turns Section 13 from a claim into evidence.** The
  acceptance criteria require the three buggy demos be "demonstrably *not*
  clean" before the Phase 2 refactor, and demonstrating that is genuinely hard:
  two of the four demos are undefined behavior, so the test binary may not
  survive its own subject. Read the header comment in
  `test_memory_sandbox.cpp` before starting — "how do you write a *passing*
  test that proves a demo is broken?" is the whole exercise, and gtest **death
  tests** are the tool worth discovering. `test_system_info.cpp` poses the
  opposite question (what do you assert when the expected value changes every
  run?) and is the easier of the two — start there if #MEM-1 is still in flight.

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
- [ ] **#AI-T1** The assertions in `python/tests/test_prompt_builder.py`,
  `test_gemini_client.py` and `test_response_parser.py` — scaffolded and
  skipped, same as the netdiag tests. Two of these three are more interesting
  than they look:
  *`test_gemini_client.py`* is really a test of **retry/backoff logic**, not of
  Gemini — it runs entirely against a fake client and must never touch the real
  API (Section 10's own mitigation says don't re-call the API on every test
  run). It covers the two bugs hand-written backoff always has: retrying
  forever, and retrying errors that will never succeed (a 401 is not a 429).
  *`test_response_parser.py`* is where the project meets the one input it
  cannot control — a model that returns something you did not ask for. Note the
  trap called out in that file: an analysis with an empty `causes` list is
  **valid**, not malformed. A healthy machine produces exactly that, and a
  parser that rejects it breaks the tool precisely when nothing is wrong.

## Phase 6 — Docs & polish (target: week 10)

- [ ] Fill in `README.md`'s "Results / known limitations" section with
  real numbers and real ASan/Valgrind output — no placeholders in the
  version anyone else reads.
- [ ] Confirm `python hwcheck.py` runs end-to-end on a clean checkout
  (fresh venv + fresh `cpp/build/`).
- [ ] Confirm both suites pass from that same clean checkout — `pytest` for the
  Python side, and `ctest --test-dir cpp/build --output-on-failure` after a
  `-DBUILD_TESTING=ON` configure. Run the C++ suite twice, once with
  `-DENABLE_ASAN=ON` and once without, and note in the README if the results
  differ: given #MEM-T1's subject matter, a difference between those two runs
  is a *finding*, not a flake.
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
- [ ] **Dangling cross-references to `league-ml`.** Four files point at a
  sibling project that does not exist in this workspace: `README.md` (line
  ~134), `hwcheck.py` (line 5), `python/ai_analyzer/gemini_client.py` (design
  question 2, pointing at `riot_client.py`'s `#ING-2` retry TODO) and
  `python/netdiag/config.py` (line 6). They were written assuming a
  League-of-Legends ML repo alongside this one. Two honest resolutions: build
  that project under the name `league-ml` and the references become real, or
  strip them so nobody (including you in week 9) goes looking for a file that
  was never written. Do not leave them as-is — a reference to a nonexistent
  file is worse than no reference, and `gemini_client.py`'s is load-bearing
  enough to matter: it offers a second worked example of the exact retry
  problem #AI-2 asks you to solve.
