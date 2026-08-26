# System & Network Diagnostics Toolkit

A modular diagnostics CLI: a **C++ engine** reads live system/memory
telemetry (and hosts a deliberately-instrumented memory-bug sandbox), a
**Python layer** runs network diagnostics and orchestrates the C++ binary
as a subprocess, and the combined telemetry is sent to the **Gemini API**
for a plain-language summary and recommendations.

This is a solo learning project first, a portfolio piece second — see
`docs/project-charter.md` (the original `Instructions.md`) for the full
scope, constraints, and the reasoning behind every scoping decision.
Status and detailed task tracking live in `docs/TODO.md` and
`docs/working-plan.md`.

**Working 3-4 hours/week?** [`WEEKLY_PLAN.md`](WEEKLY_PLAN.md) breaks the
whole project into session-sized steps at that pace — start there.

**Status: 🚧 in progress.** Repo scaffolding + the fully-built "trivial
plumbing" and "beyond current skill baseline" pieces are done (see
`docs/project-charter.md` Section 18); the core C++ memory-management and
networking modules are the current open work.

## Architecture

```
                 ┌──────────────────────────────┐
                 │  C++ Engine (libsysdiag)      │
                 │  /proc reads -> SystemSnapshot│
                 │  MemorySandbox (raw ptr demos)│
                 │  -> JSON on stdout             │
                 └───────────────┬────────────────┘
                                 │ subprocess (engine_runner.py)
                 ┌───────────────▼────────────────┐
                 │  Python Orchestrator (netdiag)  │
                 │  ping / DNS / port-scan probes  │
                 │  merge -> one telemetry payload │
                 └───────────────┬────────────────┘
                                 │
                 ┌───────────────▼────────────────┐
                 │  Gemini Analyzer (ai_analyzer)   │
                 │  structured prompt -> API call   │
                 │  -> summary / causes / fixes      │
                 └───────────────┬────────────────┘
                                 │
                          cli/main.py (CLI report)
```

## Repo layout

```
hardware-check/
├── hwcheck.py              # repo-root entry point
├── cpp/                    # C++20, CMake — the memory-management learning core
│   ├── CMakeLists.txt
│   ├── include/sysdiag/
│   └── src/
├── python/
│   ├── netdiag/            # config, JSON schema/merge, report writer (built);
│   │                       # ping/dns/port-scan probes + engine_runner (#TODO)
│   ├── ai_analyzer/        # Gemini client, prompt builder, response parser (#TODO)
│   ├── cli/                # argparse entry point (built)
│   └── tests/
├── data/
│   ├── reports/            # gitignored — exported reports
│   └── cache/              # gitignored — for a Gemini response cache, if you add one (#AI-2)
└── docs/
    ├── project-charter.md  # full spec — mirror of Instructions.md
    ├── working-plan.md     # 12-week schedule
    └── TODO.md             # detailed, checkable task list
```

## Setup

**C++ side (build inside WSL2 — see `docs/project-charter.md` Section 5
for why this project targets Linux even on a Windows dev machine):**

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Debug
cmake --build cpp/build
```

**Python side:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # fill in a free Gemini API key + engine path
```

## Running

```bash
python hwcheck.py                          # full pass: telemetry + Gemini analysis
python hwcheck.py --raw                     # also print raw merged telemetry JSON
python hwcheck.py --no-ai                   # skip the Gemini call (dev/rate-limit friendly)
python hwcheck.py --export json             # write a report under data/reports/
python hwcheck.py --memory-demo leak        # opt into one C++ memory-bug demo
```

Every module this calls that's still a `docs/TODO.md` stub raises
`NotImplementedError` with a pointer to the relevant task ID — that's
expected until each phase lands, not a bug in the scaffolding.

## Memory-safety verification

Both tools, not just one (they catch different bug classes and
occasionally disagree, which is itself instructive):

```bash
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Debug -DENABLE_ASAN=ON
cmake --build cpp/build
./cpp/build/sysdiag_engine --memory-demo=all

valgrind --leak-check=full ./cpp/build/sysdiag_engine --memory-demo=all
```

## Scope

- **In scope (v1):** CLI diagnostics — CPU/memory/disk telemetry, the raw-
  pointer memory sandbox (later refactored to smart pointers), ping/DNS/
  port-scan network checks, Gemini-generated summary.
- **Explicitly out of scope (v1):** desktop GUI (Phase 7+), full cross-
  platform support, raw packet capture, kernel-level anything.

See `docs/project-charter.md` Section 3 for the full list and reasoning.

## Results / known limitations

<!-- TODO: fill in once the pipeline runs end-to-end — e.g. real
     Valgrind/ASan output from the memory sandbox, real port-scan/ping
     numbers, how the smart-pointer refactor changed things. No inflated
     or placeholder claims in the final version — same rule as the
     league-ml repo's README in this workspace. -->

_Not yet available — see `docs/TODO.md` for current progress._
