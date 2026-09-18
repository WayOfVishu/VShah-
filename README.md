# VShah-

Personal monorepo: projects, tooling, and the source for my professional portfolio.

Everything here is mine unless it sits under `External Repos/` (git submodules,
third-party) or `References/` (reading material, not code).

## Projects

| Project | Stack | State |
|---|---|---|
| [Jobs-Web-App](Projects/Jobs-Web-App) | Node.js, Express, SQLite, vanilla JS | **Complete, in daily use** |
| [Portfolio](Projects/Portfolio) | FastAPI, Vite, vanilla JS, WebGL | **Complete** |
| [Stocks](Projects/Stocks) | Python, pandas, scikit-learn, FastAPI | Infrastructure complete; modelling in progress |
| [League-ML](Projects/League-ML) | Python, PyTorch, SQLite, FastAPI | Infrastructure complete; networks in progress |
| [Hardware-Check](Projects/Hardware-Check) | C++17, CMake, GoogleTest, Python | In progress |

### Jobs-Web-App — job discovery and application pipeline

Multi-source ingestion with per-platform connectors behind one normalized
schema, board discovery with negative-result caching, weighted relevance
scoring over location/title/keyword signals, cross-source deduplication, a
forward-only SQLite migration runner, and an explicit application-lifecycle
state machine. Dashboard renders pipeline flow, activity heatmap, and streaks.

Running in production against my own job search — 76 applications tracked.

### Portfolio — personal site

FastAPI backend, Vite frontend, hand-written WebGL hero field (no three.js).
Page content is inlined at build time, so the site paints complete on first
script evaluation and stays fully functional with the backend off, while the
same JSON is served at `/api/summary` as the single source of truth.

### Stocks — equity forecasting research pipeline

A five-window dataset specification anchored to a configurable as-of date
rather than "today", so the whole arrangement slides backward through history
to produce a labelled panel — which is what makes the problem trainable and
what structurally prevents lookahead leakage. Plus a valuation and risk
library built from Bodie/Kane/Marcus (CAPM, security characteristic line,
multifactor, event study, portfolio, risk, returns) with 94 tests against the
textbook's worked examples, a pluggable ingestion registry with disk caching
and offline synthetic data, and a purged walk-forward evaluation harness.

Modelling is the open work — see [`docs/TODO.md`](Projects/Stocks/docs/TODO.md).
The charter is explicit that 30-day equity returns are close to a random walk
and that a rigorous null result is the expected outcome; the methodology is
the point, not the prediction.

### League-ML — match outcome prediction and item recommendation

Ranked League of Legends matches to a participant-level table, fed to neural
networks that predict outcomes and rank item options for a matchup.

The interesting design decision is that every model trains on synthetic data
with a **planted, known answer** before real data exists: champion strength
that logistic regression can find, same-team synergy pairs that it cannot, and
items suited to each champion. That makes the evaluation harness testable on
its own terms. Ingestion, features, and the networks are the open work — see
[`docs/TODO.md`](Projects/League-ML/docs/TODO.md).

### Hardware-Check — system and network diagnostics toolkit

A C++17 engine reads live system and memory telemetry and hosts a deliberately
memory-unsafe sandbox; a Python layer runs network probes and orchestrates the
binary as a subprocess. The point of the project is the memory work: write the
raw-pointer version, prove it unsafe under ASan and Valgrind with GoogleTest
death tests, then refactor to `unique_ptr`/`shared_ptr` and document the diff.

The C++ core is the current open work — see
[`docs/TODO.md`](Projects/Hardware-Check/docs/TODO.md).

## Layout

```
Projects/              my work
Tools/                 repo tooling
External Repos/        third-party submodules — not mine
References/            reading material — not code
Virtual Environments/  local venvs and requirements files
```
