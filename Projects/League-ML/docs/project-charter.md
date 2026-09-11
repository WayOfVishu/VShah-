# Project Charter: LoL Match Analytics & Build Recommendation Engine

**Type:** Solo portfolio project
**Purpose:** Build genuine, hands-on Python and deep-learning engineering skill and produce a public repo to support CS MSc (ML-focus) applications
**Status:** Scaffolded — plumbing, synthetic data, the training loop and the evaluation harness are built; ingestion, features and the networks are the open work
**Last updated:** 2026-09-10 (v3 — see Section 0)

---

## 0. Document History

- **v1 (original draft):** Initial charter — scope, BOM, timeline, data model.
- **v2 (2026-08-25):** The draft repo existed on disk. Recorded the split between what was built and what was left as `#TODO` (Section 18), replaced the phase table with a 12-week calendar, added `ingestion_checkpoints` to the data model, and added two risks.
- **v3 (this revision, 2026-09-10):** Moved into this repo as `Projects/League-ML`, and **the primary models became neural networks instead of XGBoost.** Everything else in v2's scope — the Riot ingestion, the feature pipeline, the item-recommendation CLI — stands. Specifically:
  - **Modelling (Sections 2, 3, 4, 10).** PyTorch moves from stretch goal to the point of the project. XGBoost leaves scope. Logistic regression stays, as the floor every network is measured against. Section 10 is rewritten to say when a network is actually justified on this data, rather than pretending the v2 argument for trees went away.
  - **Structure (Sections 5, 17).** Reshaped after `Projects/Stocks`: a named package (`leagueml/`) instead of `src/`, `py run.py <command>` instead of `run_pipeline.py`, a FastAPI backend under `backend/app/`, and an offline synthetic `demo`. `Instructions.md` is dropped — this file is the only copy, same as Hardware-Check.
  - **Synthetic data (new).** A generator with a planted, known answer lets every model run before real data exists, and doubles as a leakage canary. Real data arrives only after ingestion and features, months in; the networks no longer wait for it.
  - **Two factual fixes to the draft.** Riot removed its summonerId endpoints on 2025-06-20, so match discovery is PUUID-first. And Data Dragon versions use client numbering (`16.18.1`) while patch notes use year numbering (`26.18`) — the draft passed `"26.16"` to Data Dragon, which returns HTTP 403.
  - **Data model (Section 12).** Added `matches.game_version`, `participants.riot_participant_num` (the join key the timeline needs, which v2 flagged but never stored) and a `participant_frames` table.
  - **Tags.** The draft's IDs are remapped; the table below is the record.

| draft tag | v3 | why |
|---|---|---|
| `#ING-1..4` | `#ING-1..4` | unchanged; `#ING-4` updated for PUUID discovery |
| `#FEAT-1`, `#FEAT-3` | `#FEAT-1`, `#FEAT-3` | unchanged; `#FEAT-3` gains enemy/ally columns and a materialise step |
| `#FEAT-2` | `#FEAT-2` | rethought — integer ids for embeddings as well as multi-hot for the floor |
| — | `#FEAT-4` | new: per-minute frames, for the confounder and the sequence model |
| `#MOD-1` (baselines) | built | the floor is evaluation infrastructure now (Section 18) |
| `#MOD-2` (XGBoost) | dropped | out of scope in v3 |
| `#MOD-3` (evaluation) | built + `#EVAL-1..4` | harness built; the experiments are yours |
| `#MOD-4` (recommendations) | `#REC-1` | now against a network |
| `#STRETCH-1` (PyTorch) | `#DL-1` | the first deep-learning task, not a stretch |
| `#STRETCH-2` (FastAPI) | `#REC-2` | skeleton built after Stocks; the handler is yours |
| `#STRETCH-3` (Streamlit) | `#REC-3` | a three-file frontend, Stocks' shape |
| housekeeping (untagged) | `#LML-1..4` | tagged, so Jira-Sync can match them |

Companion living documents (not duplicated here — go read them directly):
- `docs/working-plan.md` — the phases in calendar form
- `docs/TODO.md` — the checkable, per-file task list with IDs referenced throughout this document
- `WEEKLY_PLAN.md` — the same phases, cut into 3-4 hour sessions

---

## 1. Project Overview

An end-to-end pipeline that pulls ranked League of Legends match data from the Riot Games API, turns it into a participant-level table of champions, matchups, items and gold, trains **neural networks** to predict who wins, and uses the best of them to rank the top-N item options for a given champion matchup — the same underlying idea as u.gg/op.gg, scoped down to something one developer can actually build and *understand every line of*.

**This is explicitly a learning project first, a portfolio piece second.** The scope below is sized to a realistic starting skill level (see Section 4), not to what an AI assistant could generate on your behalf. The value of this repo, for grad-school purposes, is that you can explain and defend every design decision in it — including, if it comes to that, why a network did *not* beat logistic regression.

---

## 2. Objectives

- Build real fluency in Python (not orchestration-of-an-AI-agent fluency): functions, classes, error handling, REST clients, file I/O
- Understand REST API constraints in practice — rate limiting, pagination, retries, backoff
- Practice feature engineering with pandas and SQL
- **(v3)** Define, train, debug and honestly evaluate neural networks in PyTorch: embeddings, attention, a recurrent model, the training loop around them, and the discipline that keeps them honest — early stopping, regularisation, calibration
- **(v3)** Be able to say, with evidence, when a network earns its complexity over logistic regression on this data and when it does not
- Produce a clean, documented, reproducible public GitHub repo

---

## 3. Scope

### In Scope (MVP)
- Riot API ingestion module with rate-limit handling for a **personal API key**
- Local structured storage (SQLite)
- Feature engineering: champion, role, lane opponent, teammates and opponents, items owned and team gold at a fixed timestamp (10-minute snapshot), win/loss
- **(v3)** Neural networks in PyTorch: a reference MLP, learned embeddings, attention over the ten champions — each compared against a logistic-regression floor
- **(v3)** Match-grouped evaluation, a leakage canary, calibration
- CLI inference tool: given champion + matchup context, output top-3 item recommendations ranked by predicted win-probability lift
- **(v3)** FastAPI endpoint for the same recommendation
- Single-patch dataset (see Section 13 — patch drift)

### Stretch Goals (only after MVP works end-to-end)
- **(v3)** A recurrent model over per-minute timeline frames (in-game win probability)
- **(v3)** A three-file frontend (replaces the v2 Streamlit idea)
- **(v3)** Visualising the learned champion embeddings

### Explicitly Out of Scope
- Production deployment / public-facing product (this determines the API key tier — see Section 6)
- Distributed computing (PySpark) — unjustified at this data scale
- **(v3)** Gradient-boosted trees (XGBoost and kin) as a project model — see Section 10 for why this is a real trade-off rather than an oversight
- Rune-page or champion-pick recommendations — item builds only, to keep the feature space tractable
- Real-time / live-game predictions (Live Client Data API integration)
- Multi-patch generalization

---

## 4. Skill Baseline & Learning Objectives

Being honest about the starting point up front, so the plan is actually achievable rather than aspirational. This is the *pre-project* baseline — the yardstick Section 18's "built for you vs. yours" decisions were made against — so the starting levels are left as originally recorded. Track actual progress in `docs/TODO.md`, not by editing this table. The deep-learning *target* was raised in v3, because the scope changed; the starting level was not.

| Area | Starting level (self-reported) | Target by end of project |
|---|---|---|
| SQL | Strong | (leveraged directly — feature engineering logic will map closely to SQL mental models) |
| Python | Basic | Comfortable writing/debugging scripts, functions, and simple classes unassisted |
| REST APIs | Prior exposure via Fivetran/Databricks pipelines, but largely orchestrated through an AI agent rather than hand-coded | Able to write and reason about a rate-limited REST client from scratch |
| ML | Minimal | Understands train/validation/test splits, grouped splits, ROC-AUC/log-loss/calibration, and can explain *why* the model does what it does — not just that it runs |
| Deep learning | None | **(v3)** Can define, train and debug a PyTorch model unassisted — embeddings, attention, a recurrent layer — read its training curves, and explain why it did or did not beat logistic regression |

**Working principle:** every deliverable should be something you could explain in a grad-school interview without notes. If a component is generated faster than you can understand it, slow down and rebuild it by hand before moving on.

---

## 5. System Architecture

```
Riot Match-V5 API ──┐
League-V4 (seeds)   ├──► Raw JSON (data/raw/) ──► SQLite ──► participant table (pandas)
Data Dragon CDN ────┘         │                                    │
(items, champions)            └── timeline frames ─────────────────┤
                                                                   ▼
            synthetic.py  ──── same columns, planted answer ──►  encode.py
            (offline, no key)                                       │
                                                  ┌─────────────────┴─────────────────┐
                                                  │  floor: majority, logistic reg.   │
                                                  │  networks (PyTorch):              │
                                                  │    MLP · embeddings · attention   │
                                                  │    (stretch) GRU over timeline    │
                                                  └─────────────────┬─────────────────┘
                                                                    ▼
                                           evaluate.py — match-grouped splits, canary
                                                                    │
                                                                    ▼
                                    recommend.py ──► `py run.py recommend` / POST /api/recommend
```

### Module Breakdown (as built — see Section 17 for the full tree)
- `leagueml/static/` — Data Dragon client — **built**
- `leagueml/storage/` — SQLite connection + generic insert/query helpers — **built**
- `leagueml/ingestion/` — rate limiter, Riot client, checkpointing, orchestrator — **scaffolded, logic is `#ING-1..4`**
- `leagueml/features/` — item timing, frames, participant table, encodings — **scaffolded, logic is `#FEAT-1..4`**
- `leagueml/synthetic.py` — offline matches with a planted answer — **built**
- `leagueml/datasets.py`, `leagueml/train.py` — tensor plumbing and the training loop — **built** (early stopping is `#DL-3`)
- `leagueml/models/` — the floor and the reference MLP **built**; embeddings, attention, timeline are **`#DL-2`, `#DL-5`, `#DL-7`**
- `leagueml/evaluate.py` — splits, metrics, canary — **built**; the experiments are `#EVAL-1..4`
- `leagueml/recommend.py` — **`#REC-1`**
- `leagueml/cli.py`, `run.py` — **built**
- `backend/app/` — FastAPI: health **built**, `/api/recommend` **`#REC-2`**
- `notebooks/` — **intentionally empty, yours to populate** (`#LML-4`)
- `tests/` — real tests for everything built; skipped `write me` tests waiting for each TODO

---

## 6. Data Sourcing Strategy

This is worth spelling out explicitly since it drives most of the architecture and timeline.

**API key tier:** Register a **Personal API Key** on the [Riot Developer Portal](https://developer.riotgames.com/) — not a Production key. Production keys exist for public-facing products with an approved live prototype and are not needed (or obtainable) for a local research project. Personal key limits:

| Key type | Rate limit | Expiry | Use case |
|---|---|---|---|
| Development (default) | 20 req/1s, 100 req/2min | 24 hours | Initial tinkering only |
| Personal (registered) | 20 req/1s, 100 req/2min | Long-lived | **This project** |
| Production (approved) | 500 req/10s, 30,000 req/10min (expandable) | Long-lived | Public products only (not applicable here) |

**(v3) Match discovery is PUUID-first.** Riot removed its summonerId/accountId endpoints on 2025-06-20 in favour of PUUID equivalents. Seeds come from League-V4 league entries straight to PUUIDs, then Match-V5 by PUUID — no Summoner-V4 hop. Confirm on the first real call that league entries carry `puuid`.

**Static data (items, champions):** Pulled from the **Data Dragon CDN** (`ddragon.leagueoflegends.com`) — free, no API key, no rate limit, versioned by patch. **(v3)** Versions use the client numbering: patch "26.18" in the patch notes is `16.18.1` on Data Dragon and `16.18.x` in a match's `info.gameVersion`. `config.py` holds both. The client is built: `leagueml/static/data_dragon.py`.

**Realistic throughput math:** Match ID list calls return up to 100 IDs per request, so ID discovery overhead is small; the bottleneck is one request per match for full match details, **plus one more request per match for the timeline endpoint** (needed for item timing and, in v3, per-minute frames). At a sustained ~50 req/min (leaving margin under the 100/2min cap), collecting **1,000 matches ≈ ~40 minutes of pure API time** with both endpoints, scaling roughly linearly. The bottleneck in practice still won't be the API — it'll be your own debugging time on the ETL and feature code.

**(v3) How many matches?** v2's target of 2,000–5,000 was set for tree models. Networks are data-hungrier, and `#EVAL-4`'s learning curve — not a guess — decides whether to pull more. At ~40 minutes per 1,000 matches, doubling the dataset costs a few more overnight runs, not a redesign.

---

## 7. Deliverables

Status tracked in detail in `docs/TODO.md`; summarized here.

### Core
| Deliverable | Description | Status |
|---|---|---|
| Ingestion module | Rate-limited Riot API client with retry/backoff on HTTP 429 | Scaffolded — `#ING-1..4` open |
| Feature pipeline | Raw match + timeline JSON → participant table → encodings | Scaffolded — `#FEAT-1..4` open |
| Synthetic data + canary | Offline matches with a planted answer | **Built** |
| Evaluation harness | Match-grouped / chronological splits, AUC, log-loss, Brier, canary | **Built** — experiments `#EVAL-1..4` open |
| Floor | Majority class + logistic regression | **Built** |
| Networks | Reference MLP; embeddings; attention | MLP **built** — `#DL-1..6` open |
| Inference CLI | `py run.py recommend --champion X --enemy Y --role Z` → top-3 items | Argparse built — `#REC-1` open |
| API | `POST /api/recommend` | Skeleton built — `#REC-2` open |
| Public GitHub repo | Modular package, README, requirements, tests | Structure in place |

### Stretch
| Deliverable | Description | Status |
|---|---|---|
| Sequence model | GRU over per-minute frames | Not started — `#DL-7` (runs on synthetic curves once written) |
| Frontend | Three files, no build step | Not started — `#REC-3` |
| Embedding visualisation | Nearest neighbours / projection of champion embeddings | Not started — `#DL-8` |

---

## 8. Functional Requirements

- Ingestion must handle HTTP 429 responses with exponential backoff, not crash or silently drop matches
- Ingestion must checkpoint progress (resumable if interrupted — keys/network will fail mid-run)
- Feature pipeline must extract item-purchase state and team gold at a fixed timestamp snapshot (10-min mark)
- Model training must use a train / validation / test split **grouped by match** (v3 — a match's ten participant rows must never straddle a split) and report at minimum ROC-AUC and log-loss
- **(v3)** Every network must be reported next to the logistic-regression floor on the same test set
- Inference must return top-3 items ranked by predicted win-probability lift, given champion + matchup context

## 9. Non-Functional Requirements

- Single-command reproducibility: install `Virtual Environments/Requirements/league.txt`, then `py run.py pipeline`
- **(v3)** An offline path that needs no key: `py run.py demo` runs end to end on synthetic data in under a minute
- PEP 8 compliance, docstrings on all public functions
- Modular separation between ingestion, feature engineering, and modeling (no monolithic scripts)
- **(v3)** Seeded, repeatable runs — the seed is part of every logged result (`#EVAL-1`)
- No fabricated/inflated claims in the README about scale or performance — this repo needs to hold up to direct questioning

---

## 10. ML Modeling Approach

**Primary approach (v3): neural networks in PyTorch.**

v2 argued, correctly, that on a flat tabular table — champion one-hot, role, items — gradient-boosted trees usually match or beat a neural network with far less data and far less tuning. That argument did not go away, and v3 does not pretend otherwise. What changed is which question the networks are asked. A network earns its place here only where the input has structure a flat one-hot table throws away:

| structure in the data | the network that fits it | TODO |
|---|---|---|
| ~170 champions and ~200 items are *entities*, not independent columns — some behave alike | learned embeddings (`nn.Embedding`, `nn.EmbeddingBag`) | `#DL-2` |
| a team is a *set* of five, and synergy and counters are *interactions* between members | attention over champion tokens (`nn.TransformerEncoder`), order-free by construction | `#DL-5` |
| a game is a *sequence* of per-minute states | a recurrent model (`nn.GRU`) over timeline frames | `#DL-7` |

A plain MLP over the flat one-hot table is included too — built, as the worked example — and it is **expected to roughly tie** logistic regression. If it does, that is v2's argument confirmed, not a failure, and the README says so.

**The floor stays.** Majority class and logistic regression, on the same rows and the same split, are the yardstick every network is measured against (`#EVAL-3`). A network that does not clearly beat logistic regression on held-out matches, across several seeds, is not earning its complexity. On real ranked data that is a live possibility, and "the attention model found nothing the linear floor didn't" is a finding worth writing up.

**Why PyTorch (kept from v2).** A research-leaning CS MSc will care about deep-learning framework familiarity, and current framework adoption data supports PyTorch specifically: as of 2026, PyTorch is used in roughly 85% of published deep learning research papers, versus TensorFlow's larger but declining share of enterprise/legacy production deployments. The stronger portfolio story is still the one v2 named — "I measured when a network beats a linear baseline on this data, and here is what I learned" — rather than "I used a neural net because it sounded more advanced."

**Why the evaluation is built rather than left as a TODO.** The easiest way for this project to produce an impressive, wrong number is to split participant rows at random: a match's ten rows share one outcome, so its near-twins land on both sides of the split. Stocks' equivalent is overlapping label windows; the fix has the same shape — move whole groups. `evaluate.py` does it, and `#EVAL-2` measures what skipping it would have cost.

**Explicitly not used:**
- **Gradient-boosted trees (XGBoost, LightGBM, sklearn's HistGradientBoosting)** — out of scope as a project model in v3. They remain the strongest *reference* on flat tabular data; if a reviewer asks "did you compare against XGBoost?", the honest answer is either "no — here is the linear floor instead, and why" or a one-off reference run, which costs an afternoon with sklearn and no new dependency. Decide which when `#EVAL-3` is done, not before.
- **TensorFlow / Keras** — no longer the default choice for new research-oriented work; would add ecosystem friction with no benefit here
- **PySpark** — built for datasets that don't fit in memory; this project's data (thousands to tens of thousands of matches) fits comfortably in pandas. Using it would demonstrate cargo-culting a "big data" tool, not competence.

---

## 11. Bill of Materials (BOM)

| Category | Component | Purpose | Cost |
|---|---|---|---|
| Language | Python 3.10+ | Core language | $0 |
| Data extraction | `requests` | Riot API polling, Data Dragon | $0 |
| Data wrangling | `pandas`, `numpy`, `pyarrow` | Feature engineering, Parquet | $0 |
| Deep learning | `torch` (PyTorch) | **(v3)** The networks — required, no longer stretch | $0 |
| Classical ML | `scikit-learn` | The logistic-regression floor, metrics | $0 |
| API | `fastapi`, `uvicorn`, `pydantic` | **(v3)** The recommendation endpoint | $0 |
| Config | `python-dotenv` | Loads `.env` (API key, etc.) into environment | $0 |
| Testing | `pytest`, `httpx` | Unit tests, API tests | $0 |
| Storage | SQLite (Python stdlib `sqlite3`) | Local structured storage — zero extra dependency at this data scale | $0 |
| Static data | Data Dragon CDN | Champion/item/patch metadata | $0 |
| Version control | Git + GitHub | Code hosting, portfolio | $0 (public repo) |
| API access | Riot Personal API Key | Match data access | $0 (registration only) |
| Compute | Local CPU | Enough for thousands of matches and networks with thousands of parameters — the demo trains in seconds | $0 |
| Compute (optional) | Google Colab free tier | GPU, only if `#DL-5`/`#DL-7` get slow — T4 GPU, 12-hour max session | $0 |
| Compute (optional, if needed) | Google Colab Pro | Faster GPU, longer runtime, more memory | ~$9.99–$11.99/month (verify current price before purchasing) |

**Total required spend: $0.** Dependencies live in `Virtual Environments/Requirements/league.txt`, per repo convention. The only optional paid item is Colab Pro, and at this data scale a GPU is a convenience, not a requirement.

---

## 12. Data Model

Implemented as-is in `db/schema.sql`, created via `leagueml/storage/db.py::init_db()`.

| Table | Key Fields | Notes |
|---|---|---|
| `matches` | `match_id` (PK), `patch`, `game_version`, `game_start_ts`, `duration_s`, `queue_id` | **(v3)** `game_version` is the raw `info.gameVersion`; `patch` is its major.minor, compared against `config.TARGET_PATCH` |
| `participants` | `participant_id` (PK), `match_id` (FK), `puuid`, `riot_participant_num`, `champion`, `role`, `team_id`, `win` | `participant_id` convention: `f"{match_id}_{puuid}"`. **(v3)** `riot_participant_num` (1-10) is how the timeline refers to a participant — the join key for the two tables below |
| `item_snapshots` | `participant_id` (FK), `snapshot_minute`, `item_slot`, `item_id` | Sourced from the Match-V5 **timeline** endpoint, not match detail — see Section 6 |
| `participant_frames` | `participant_id` (FK), `minute`, `total_gold`, `xp`, `level`, `minions_killed`, `jungle_minions_killed` | **(v3)** Per-minute state from the timeline; feeds `gold_diff_at_snapshot` and the sequence model |
| `items_static` | `item_id` + `patch` (PK), `name`, `gold_total` | From Data Dragon |
| `ingestion_checkpoints` | `match_id` (PK), `status` (`pending`/`done`/`failed`), `updated_at` | Added in v2 — needed for resumable ingestion (Section 8) |

The model-facing contract is not a table but a DataFrame: `PARTICIPANT_COLUMNS` in `leagueml/features/build_feature_table.py`. Both the real pipeline (`#FEAT-3`) and the synthetic generator produce exactly those columns.

---

## 13. Constraints & Risks

| Risk | Mitigation |
|---|---|
| Dev key expires every 24h during initial testing | Move to a registered Personal key as soon as ingestion logic is stable |
| Personal key rate limit (100 req/2min) | Checkpointed, resumable ingestion run over multiple sessions rather than one long pull |
| Patch drift — LoL patches roughly every 2 weeks (26.18 live as of 2026-09-10) | Lock the dataset to a single patch (`config.TARGET_PATCH`); pick it when ingestion starts (`#LML-3`); discard/re-pull if a boundary is crossed mid-collection |
| Skill-gap risk: underestimating the ingestion/ETL debugging time as a Python beginner | Timeline budgets real ramp-up time before pipeline work begins — don't compress it |
| ML underperformance | The floor — majority class, then logistic regression — is built and reported beside every network, so there is always a number to compare against |
| Overscoping the initial dataset | Pilot on dozens of matches, then thousands; scale further only on `#EVAL-4`'s evidence |
| **(v2)** Match-detail vs. timeline endpoint confusion | Match detail only has *final* items. Item timing and (v3) per-minute gold need the timeline — documented in `item_timing.py`, `frames.py` and `riot_client.get_match_timeline()` |
| **(v2)** Seed-account sampling bias | An all-Challenger seed skews the dataset toward one skill tier. `get_entries_by_division()` exists for sampling lower tiers; decide deliberately in `#ING-4` and document it (`#LML-2`) |
| **(v3)** Leakage through the split | A match's ten participant rows share one outcome. Splits are grouped by match (`evaluate.py`); `#EVAL-2` measures the cost of getting it wrong; the synthetic canary catches leaks of any origin |
| **(v3)** Overfitting | Networks with thousands of parameters on thousands of matches memorise readily — the demo shows it on the first run. Early stopping (`#DL-3`), regularisation (`#DL-4`), learning curves (`#EVAL-4`) |
| **(v3)** Confounding in item effects | Players who are ahead buy more items, so "items at 10 → win" is partly "already winning → win". `gold_diff_at_snapshot` is in the table so `#REC-1` can hold it fixed; the synthetic generator plants the effect so it can be seen |
| **(v3)** Miscalibration | Cross-entropy-trained networks are often overconfident, and the recommender ranks by probability differences. `#DL-6` |
| **(v3)** API and naming changes under you | Riot's June 2025 PUUID migration and the 26.x / 16.x patch numbering both broke the draft silently. Verify endpoints and version strings against a real response before building on them |

---

## 14. Development Timeline

Superseded in detail by `docs/working-plan.md` (phases in calendar form) and `WEEKLY_PLAN.md` (3-4 hour sessions). Reproduced here for the charter's own record.

| Weeks (at 10-15 h/week) | Focus | Status |
|---|---|---|
| 1–2 — Practice | Orientation, environment, `py run.py demo`, Riot key, experiment log (`#EVAL-1`) | Not started |
| 3–4 — Ingestion | `#ING-1..4`; start the long pull | Not started |
| 5–6 — Networks on synthetic data | `#DL-1`, `#FEAT-2`, `#EVAL-2`, `#DL-2..4`, `#EVAL-3` — while the pull runs | Not started |
| 7–8 — Real features | `#FEAT-1`, `#FEAT-4`, `#FEAT-3` | Not started |
| 9–10 — Networks on real data | `#EVAL-4`, `#DL-5`, `#DL-6` | Not started |
| 11 — Recommendations (MVP) | `#REC-1`, `#REC-2` | Not started |
| 12–13 — Improve with feedback | Outside eyes on the MVP; revise | Not started |
| 14 — Finish | Freeze scope, honest README numbers, clean-clone check | Not started |

v2's plan was 12 weeks; the deep-learning scope adds about two at this pace.

---

## 15. Success Criteria

- Pipeline runs end-to-end with a single command on a fresh clone, and `py run.py demo` runs with no key at all
- Every network is reported next to the logistic-regression floor, over several seeds, on a match-grouped test set — including the ones that lose
- The canary passes: on synthetic labels independent of every feature, every model scores AUC ≈ 0.5
- Model reports honest, reproducible metrics (no cherry-picked runs — `#EVAL-1`'s log is the evidence)
- You can explain every module in the repo without referring back to documentation
- README is clear enough that a stranger (or an admissions committee) understands what was built and why

---

## 16. References

- Riot Developer Portal: https://developer.riotgames.com/
- Riot API Rate Limiting docs: https://developer.riotgames.com/docs/portal
- League of Legends API docs: https://developer.riotgames.com/docs/lol
- Data Dragon: https://ddragon.leagueoflegends.com/ (versions: `/api/versions.json`)
- Match-V5 API reference: https://developer.riotgames.com/apis#match-v5
- LoL Patch Schedule: https://support-leagueoflegends.riotgames.com/hc/en-us/articles/360018987893-Patch-Schedule-League-of-Legends
- PyTorch docs and tutorials: https://pytorch.org/docs/ · https://pytorch.org/tutorials/
- *Dive into Deep Learning* (free, PyTorch edition): https://d2l.ai/
- scikit-learn docs: https://scikit-learn.org/stable/
- Background reading, one per `#DL` item — search by title:
  - Guo & Berkhahn, *Entity Embeddings of Categorical Variables* (2016) — `#DL-2`
  - Zaheer et al., *Deep Sets* (2017) — pooling allies, `#DL-2`/`#DL-5`
  - Vaswani et al., *Attention Is All You Need* (2017) — `#DL-5`
  - Jain & Wallace, *Attention is not Explanation* (2019) — before any attention heatmap goes in the README
  - Guo et al., *On Calibration of Modern Neural Networks* (2017) — temperature scaling, `#DL-6`
- `docs/working-plan.md`, `docs/TODO.md`, `WEEKLY_PLAN.md` (this repo)

---

## 17. Repository Structure (as built)

```
Projects/League-ML/
├── README.md
├── WEEKLY_PLAN.md               # the phases, in 3-4 hour sessions
├── run.py                       # py run.py <command>
├── pytest.ini
├── .env.example                 # copy to .env (gitignored), fill in your Riot key
├── db/
│   └── schema.sql
├── data/                        # gitignored — raw JSON, SQLite, participant table, checkpoints
│   ├── raw/  processed/  static/  checkpoints/
├── leagueml/
│   ├── config.py                # built
│   ├── cli.py                   # built — demo, train, static, init-db, ingest, build-dataset, recommend, serve, pipeline
│   ├── static/data_dragon.py    # built
│   ├── storage/db.py            # built
│   ├── ingestion/               # rate limiter, Riot client, checkpointing, orchestrator — #ING-1..4
│   ├── features/                # item timing, frames, participant table, encodings — #FEAT-1..4
│   ├── synthetic.py             # built — planted answer + canary
│   ├── datasets.py              # built — dict-of-tensors Dataset
│   ├── train.py                 # built — the training loop (early stopping is #DL-3)
│   ├── evaluate.py              # built — grouped splits, metrics, canary
│   ├── models/
│   │   ├── baselines.py         # built — the floor
│   │   ├── mlp.py               # built — the reference network
│   │   ├── embedding.py         # #DL-2
│   │   ├── composition.py       # #DL-5
│   │   └── timeline.py          # #DL-7
│   └── recommend.py             # #REC-1
├── backend/app/
│   ├── main.py                  # built — /api/health
│   └── routers/recommend.py     # #REC-2
├── notebooks/
│   └── README.md                # intentionally empty — #LML-4
├── tests/                       # real tests for what's built; skipped "write me" tests for each TODO
└── docs/
    ├── project-charter.md       # this document
    ├── working-plan.md
    └── TODO.md
```

---

## 18. Development & Learning Approach

This project is built under a deliberate rule, since it's explicitly a *learning* project (Section 1) and not just a deliverable to be produced as fast as possible:

- **Fully implemented for you:** components at either extreme of difficulty —
  - trivially mechanical plumbing with a low learning ceiling (config, the Data Dragon client, SQLite helpers, the schema, argparse, the FastAPI skeleton, the dict-of-tensors dataset), and
  - components that exist to keep everything else honest, where a mistake is invisible and costly: the match-grouped splits, the metrics, the leakage canary and the synthetic generator behind it. Stocks builds its purged walk-forward split for the same reason.
- **One worked example, built on purpose:** the training loop and the reference MLP. v2 built the PyTorch model because the deep-learning baseline was "None" and the goal was exposure. v3 keeps that reasoning for exactly one model — you need a working example to read before writing three of your own — and stops there.
- **Moved to built in v3:** the logistic-regression floor. With networks now the point, the floor is evaluation infrastructure, and you have already fit sklearn classifiers in the Group20 notebook that Stocks' `pipeline.py` is modelled on.
- **Left as `#TODO` for you to build:** everything in the middle of the difficulty curve and squarely inside the learning objectives (Sections 2 and 4) — the rate limiter, retry/backoff, checkpointing, timeline parsing, encoding decisions, **every network after the reference MLP, early stopping, regularisation, calibration**, the experiments that decide whether any of it worked, and the recommendation logic. These are stubbed with `NotImplementedError`, docstrings explaining the constraint and the design questions worth working through, and — deliberately — no code that would answer those questions for you.

Full task-by-task breakdown, with IDs referenced throughout this document, is `docs/TODO.md`. Don't treat that file's hints as a spec to satisfy minimally; treat the design questions in each stubbed module's docstring as the actual assignment.

---

**End of Document**
