# Weekly Plan (3–4 hrs/week pace)

## What this file is

`docs/working-plan.md` lays out a 14-week calendar that assumes 10-15 hours
a week. This file re-paces the same task list — `docs/TODO.md`'s `#ING-*` /
`#FEAT-*` / `#DL-*` / `#EVAL-*` / `#REC-*` IDs — into chunks that actually
fit **one 3-4 hour session a week**, with a concrete "done when" for each, so
a short session has a real stopping point. The goal is learning, not
throughput (charter Section 1 — "explicitly a learning project first").

This file **replaces nothing** — it is a pacing layer on top of:
- `docs/TODO.md` — the task index (read the linked docstring for the real
  design questions; don't work from this file's one-liners)
- `docs/working-plan.md` — the phase-level calendar
- `docs/project-charter.md` — why each scope decision was made, and Section
  18's split between what was built for you and what is yours

Carried over from the draft's weekly plan and re-cut for v3: Milestones 0 and
1 are nearly unchanged; the modelling milestones are new, because the models
are networks now and there is more to learn in them.

**Week 1 is whenever you start** — the repo's stated order is C++ refresher →
Hardware-Check → Stocks → this, so that may be a while. Nothing below is
calendar-locked; it is ordered, not dated. If a week gives you two sessions,
do the next two rows.

Expect slippage. Weeks touching the rate limiter, the retry loop, timeline
parsing or a network that won't train will run long before they run short.
Weeks marked **buffer** are there on purpose — use them, don't feel behind for
needing them.

**One thing that isn't "work hours":** once `#ING-4` runs, pulling thousands
of matches is rate-limited to ~50 requests a minute — hours of the *script*
running, not of you at the keyboard. Kick it off, let it run across several
days, and spend your sessions on Milestone 2, which needs no real data at all.

Check boxes off as you go — same convention as `docs/TODO.md`.

---

## Milestone 0 — Orientation (weeks 1–2)

- [ ] **Week 1** — Read, in this order: `README.md` → `docs/project-charter.md`
  → `docs/working-plan.md` → `docs/TODO.md` → this file. Then open the tree
  (`leagueml/`, `db/`, `tests/`) and match it to charter Sections 17-18: which
  files are built, which are `NotImplementedError` stubs, and *why* each landed
  on its side of the line.
  **Done when:** for any file in `leagueml/`, you can say "built for me" or
  "mine to write, because ___" without re-opening the charter.

- [ ] **Week 2** — Environment: create the `league` venv from
  `Virtual Environments/Requirements/league.txt` (the README has the two
  commands). Run `py run.py demo` and `pytest`. Copy `.env.example` → `.env`,
  register a **Personal** key at developer.riotgames.com, fill it in. Run
  `py run.py static` and read `data_dragon.py` top to bottom — the working
  example of the client you are about to build by hand. Then one throwaway
  script of your own: any free public API, `requests`, parse, write, read back.
  **Done when:** the demo prints two tables, `pytest` is green with the
  expected skips, and your throwaway script runs.

---

## Milestone 1 — Ingestion (`#ING-1`–`#ING-4`, weeks 3–10)

The hardest phase for Python — it gets the most weeks, deliberately.

- [ ] **Week 3 — the log, then design with no code.** First, thirty minutes on
  `#EVAL-1`: decide the experiment log's schema and write the function that
  appends one row. Then read `rate_limiter.py`'s docstring in full, look up
  "sliding window rate limiter" and "token bucket algorithm", and write
  answers to its design questions before writing `RiotRateLimiter.__init__`.
  **Done when:** the log has a row in it (log the demo), and you can say what
  data structure the limiter will use and why old entries are cheap to drop.

- [ ] **Week 4 — build the rate limiter.** `__init__`, `record_request()`,
  `wait_if_needed()`, against both windows. Unskip and finish the two tests in
  `tests/test_rate_limiter.py`. **Done when:** they pass. `#ING-1` complete.

- [ ] **Week 5 — retry/backoff.** `RiotClient._request()`: the rate limiter,
  then 200 / 404 / 429 / 5xx handled distinctly, exponential backoff with your
  own base and max-retries. Make a few *real* calls — `get_league_entries()`
  first, and **check that an entry has a `puuid` key** (the draft's discovery
  path died in Riot's June 2025 migration; this is where you confirm the new
  one). Look at the rate-limit headers on a real response while you're there.
  **Done when:** real calls succeed and you can explain what your code does on
  a 429 vs. a 404 vs. a 500. `#ING-2` complete.

- [ ] **Week 6 — checkpointing.** All four functions in `checkpoint.py`. Work
  through its questions (pending-vs-done timing, retry vs. skip on failure)
  and decide — don't leave it implicit. **Done when:** you can insert and query
  a few rows through them and get the expected filtering back. `#ING-3`
  complete.

- [ ] **Week 7 — wire it together, small.** `#LML-3` first: set `PATCH_LABEL`
  and `TARGET_PATCH` to the live patch (config.py explains the two numbering
  schemes). Then `fetch_matches.run()` per its docstring, pointed at a tiny
  pilot: a few seed accounts, stop after a few dozen matches. Raw match *and*
  timeline JSON to disk; `riot_participant_num` stored. **Done when:** a few
  dozen matches' JSON land in `data/raw/` and rows appear in `matches` /
  `participants`.

- [ ] **Week 8 — buffer / debug the pilot.** Fix whatever week 7 broke on —
  auth edge cases, JSON shape surprises, remakes, a wrong-patch match. Don't
  move on until the pilot is clean.

- [ ] **Week 9 — start the real pull.** Kick off the full run toward
  `TARGET_MATCH_COUNT_MIN`–`MAX`. Let it run across sessions. Spend the rest
  of the session starting Milestone 2 — week 10 below is the same week.
  **Done when:** the pull is running and resuming cleanly after a restart.

- [ ] **Week 10 — `#LML-2`, while the pull runs.** Write the README paragraph
  on seed sampling: which tiers, and the bias that leaves. Check the dataset
  has stayed on one patch. **Milestone 1 done** (the pull itself may still be
  going — that's fine).

---

## Milestone 2 — Networks on synthetic data (weeks 10–16)

None of this needs real matches. Everything you build here re-runs on real
data unchanged once Milestone 3 produces the same columns.

- [ ] **Week 10 (same week as above) — read the loop.** Read `train.py` and
  `models/mlp.py` top to bottom. Run `py run.py demo` again and actually read
  the output: why does the canary's `val_loss` climb while `train_loss` falls?

- [ ] **Week 11 — `#DL-1`: break it on purpose.** One change at a time, each
  run logged: skip `zero_grad()`; learning rate ×100; remove `backward()`;
  remove `model.eval()` (why does nothing happen yet?). Then logistic
  regression as one `nn.Linear(n, 1)` through `train_model()` — match
  sklearn's floor on the planted data. Work out the `weight_decay` ↔ `C`
  conversion. Add its overfit-a-tiny-batch test. **Done when:** your
  `nn.Linear` model lands within noise of sklearn's AUC. `#DL-1` complete.

- [ ] **Week 12 — `#FEAT-2`: the encoder.** Build `build_vocabularies`,
  `encode_ids`, `encode_multi_hot` against `synthetic.to_participant_rows()`.
  PAD and UNK first; fit on train rows only. Unskip the two tests in
  `tests/test_features.py`. **Done when:**
  `py run.py train --model mlp --participant` runs. `#FEAT-2` complete.

- [ ] **Week 13 — `#EVAL-2`: measure the leak.** The canary, twice:
  `--participant --signal 0 --split naive-row`, then `--split match-grouped`.
  Log both, and a few seeds of each. **Done when:** you can state, as a number,
  how much a random row split would have flattered the model.

- [ ] **Week 14 — `#DL-2`: embeddings.** Write the overfit test first, then
  `EmbeddingModel` until it passes, then train it on planted synthetic data.
  **Done when:** `py run.py train --model embedding` prints a table.

- [ ] **Week 15 — `#DL-3` and `#DL-4`.** Early stopping with a *copy* of the
  best weights; then dropout and weight decay. Start a notebook and plot
  `TrainHistory` curves for a few settings side by side (`#LML-4` begins
  here). **Done when:** the canary's val_loss no longer climbs for 20 epochs
  unchecked, and you can read an overfit off a plot.

- [ ] **Week 16 — `#EVAL-3`: does anything beat the floor?** Floor vs MLP vs
  embedding, several seeds each, spread reported. Then the controlled world:
  `--strength 0 --synergy 2`, where only interactions matter. **Done when:**
  your log holds the comparison and you can say, with numbers, whether any
  network beat logistic regression. **Milestone 2 done.**

---

## Milestone 3 — Real features (`#FEAT-1`, `#FEAT-4`, `#FEAT-3`, weeks 17–21)

- [ ] **Week 17 — look before designing.** Open one real timeline JSON from
  `data/raw/` in a scratch script. Find the purchase / sell / undo events and
  the per-minute participant frames; note the real key names. Sketch
  `#FEAT-1`'s algorithm and decide what "minute 10" means for both modules.

- [ ] **Week 18 — `#FEAT-1`.** `extract_item_snapshot()` and the
  `fake_timeline` fixture; both draft tests passing. **Done when:**
  `pytest tests/test_features.py -k item_snapshot` passes.

- [ ] **Week 19 — `#FEAT-4`.** `extract_participant_frames()` and its test.
  **Done when:** one real timeline gives you a sensible gold curve per player.

- [ ] **Week 20 — `#FEAT-3`.** Materialise `item_snapshots` and
  `participant_frames`, then the join into `PARTICIPANT_COLUMNS`. The SQL week.
  **Done when:** `py run.py build-dataset` writes a Parquet file whose columns
  match `synthetic.to_participant_rows()`'s exactly.

- [ ] **Week 21 — buffer + first real look.** Debug the chain end to end on
  the real pull. Then the first real EDA in your notebook — win rate by
  champion and role, remake rate, how sparse items are at minute 10.
  **Milestone 3 done.**

---

## Milestone 4 — Networks on real data (weeks 22–26)

- [ ] **Week 22 — re-run Milestone 2 on real data.** The floor, the MLP and the
  embedding model with `--data data/processed/participants.parquet` and
  `--split chronological`. If the feature contract held, this is zero code
  changes — and if it didn't, this is where you find out. Then `#EVAL-4`: the
  learning curve. **Done when:** you know whether you need more matches.

- [ ] **Weeks 23–24 — `#DL-5`: attention.** Two sessions. Week 23: tokens
  (champion + side + role embeddings) and the permutation test. Week 24: the
  team-swap symmetry, then train and compare against the floor and `#DL-2`.

- [ ] **Week 25 — `#DL-6`: calibration.** A reliability diagram on the
  validation split, then temperature scaling. **Done when:** you can show
  the before/after diagram and explain why AUC did not change.

- [ ] **Week 26 — buffer.** Whatever Milestone 4 left broken. **Milestone 4
  done.**

---

## Milestone 5 — Recommendations: the MVP (weeks 27–30)

- [ ] **Week 27 — design `#REC-1` on synthetic data.** Pick the lift
  baseline (the draft's a/b/c) and the confounding strategy. Synthetic data
  knows each champion's real item fit (`SyntheticTruth.fit_items`) and plants
  the gold confounder — so you can check whether your recommender finds the
  real fit or just recommends being rich.

- [ ] **Week 28 — build `#REC-1`.** One batched forward pass over candidate
  items, vocabulary from the checkpoint. **Done when:**
  `py run.py recommend ...` prints three items on synthetic and on real data.

- [ ] **Week 29 — `#REC-2`.** Load the checkpoint at startup; 503 without one.
  **Done when:** `POST /api/recommend` answers from `/docs`.

- [ ] **Week 30 — buffer + sanity check.** Run recommendations for a matchup
  you know well. Do they make sense? If they are all expensive items, re-read
  `#REC-1`'s confounding note. **This is your MVP.**

---

## Milestone 6 — Feedback & polish (weeks 31–33)

- [ ] **Week 31 — outside eyes.** Show it to someone who'll read it like an
  admissions committee. Ask specifically whether the comparison against the
  floor supports what the README claims, and whether the recommendation
  caveat is clear.
- [ ] **Week 32 — act on it.**
- [ ] **Week 33 — freeze & verify.** `py run.py pipeline` from a clean
  environment. Results table and Known limitations with real numbers
  (`#LML-1`). Final commit; tag a release if you want one.

---

## Optional stretch (weeks 34+)

Not paced week by week — only with real time to spare.

- [ ] **`#DL-7`** — the GRU over timeline frames. Runs on synthetic gold curves
  the moment the model exists; real data needs `#FEAT-4` (done in week 19).
- [ ] **`#REC-3`** — a three-file frontend, Stocks' shape.
- [ ] **`#DL-8`** — look inside the embeddings.

---

## Running total

- **Milestone 0:** 2 weeks
- **Milestone 1 (Ingestion):** 8 weeks
- **Milestone 2 (Networks, synthetic):** 7 weeks, overlapping Milestone 1 by one
- **Milestone 3 (Features):** 5 weeks
- **Milestone 4 (Networks, real):** 5 weeks
- **Milestone 5 (Recommendations):** 4 weeks
- **Milestone 6 (Polish):** 3 weeks
- **Core MVP total: ~33 weeks (~8 months) at 3-4 hrs/week.**

The draft's plan was ~24 weeks; the deep-learning scope adds about nine at
this pace. Revisit this file after Milestone 2 — by then you'll have real data
on how long a session of PyTorch actually takes *you*, which beats this
estimate for everything after it.
