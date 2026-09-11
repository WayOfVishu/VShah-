# TODO

What was built for you, and what is deliberately left open. Tags match the
`#ING-n` / `#FEAT-n` / `#DL-n` / `#EVAL-n` / `#REC-n` comments in `leagueml/`.
Each module's docstring holds the actual design questions — work from those,
not from the one-liners here.

Ported from the 2026-08-25 draft (`school stuff/league-ml`) with one change of
direction: **the models are neural networks now, not XGBoost.** Charter
Section 0 maps every draft tag to where it went. Phases are ordered by what
unblocks what, not by tag number — `#FEAT-2` comes before `#FEAT-1` on
purpose, because it can be built on synthetic data months before real data
exists.

Items use Stocks' `**#TAG · Title.**` form, so Jira-Sync's parser (`#JIRA-10`)
needs no third format. Every item is tagged — no untagged rows for `#JIRA-8`
to fail to match.

Check items off as you go (`- [x]`).

---

## Status

| area | state |
|---|---|
| config, Data Dragon client, SQLite helpers, schema | **done** — plumbing, from the draft (schema extended for v3) |
| synthetic matches with a planted answer | **done** — every model runs before real data exists |
| training loop + reference MLP | **done** — the worked example; read it, then break it (`#DL-1`) |
| match-grouped splits, metrics, the canary | **done** — `py run.py demo` |
| logistic-regression floor | **done** — evaluation infrastructure now, not the lesson |
| CLI + FastAPI skeleton | **done** — `/api/recommend` answers 501 until `#REC-2` |
| experiment log | **yours** — nothing persists results today, `#EVAL-1` |
| ingestion | **yours** — `#ING-1..4` |
| features | **yours** — `#FEAT-1..4` |
| **the networks** | **yours** — `#DL-1..8` |
| recommender, endpoint, frontend | **yours** — `#REC-1..3` |

---

## Phase 0 — somewhere to put the answers

- [ ] **#EVAL-1 · An experiment log.** `evaluate.py` computes scores and
      prints them. Nothing persists. Almost every item below is a
      *comparison* — network vs floor, grouped split vs naive, 2,000 matches
      vs 4,000 — and right now each one scrolls off the terminal and is gone.
      Same problem as Stocks' `#ML-LOG`, and worth solving the same way:
      append-only, one row per run, before anything else.
      **The schema is the exercise.** What has to be in a row for a future you
      to trust it next to a row from a month later? The test: *if two rows
      disagree, can you tell whether the model changed or the data did?* At
      least: model name and its dims, the data (synthetic spec, or patch and
      match count), the split kind, the seed, epochs and learning rate, the
      best epoch if `#DL-3` exists, and every metric in the table. Where it
      lives matters less — JSONL or CSV under `data/processed/`, or a markdown
      table in `docs/RESULTS.md`. `.gitignore` ignores `data/`, so decide
      deliberately whether the log is an artifact that gets committed (it is
      the output of the project, so probably yes).

## Phase 1 — Ingestion

The hardest phase for Python, per the draft. Unchanged in substance; updated
for Riot's 2025 PUUID migration. Kick off the long pull at the end of it and
let it run in the background while Phase 2 happens.

- [ ] **#ING-1 · The rate limiter.** `leagueml/ingestion/rate_limiter.py`. Two
      windows at once — 20/1s and 100/120s — and the long one is the real
      constraint. Do this first; everything else in ingestion depends on it.
      Tests waiting in `tests/test_rate_limiter.py`, no network needed.
- [ ] **#ING-2 · The retry loop.** `RiotClient._request()` in
      `riot_client.py` — 200 / 404 / 429 / 5xx handled distinctly, backoff
      with jitter, and a decision about `Retry-After`. The same problem as
      Hardware-Check's `#AI-2` and Jira-Sync's `#JIRA-4`; whichever you write
      second, compare them.
- [ ] **#ING-3 · Checkpointing.** All four functions in `checkpoint.py`,
      against the `ingestion_checkpoints` table. Decide pending-vs-done timing
      and what a failure does on the next run — don't leave it implicit.
- [ ] **#ING-4 · The ingestion run.** `fetch_matches.run()`. PUUID-first
      discovery (no Summoner-V4 hop — Riot removed it on 2025-06-20; confirm a
      league entry carries `puuid` on your first real call). Raw match *and*
      timeline JSON to `data/raw/` — v3 needs the timeline for `#FEAT-4`.
      Store `riot_participant_num`, `game_version` and the patch, and decide
      what remakes and wrong-patch matches do. Pilot on dozens of matches
      before thousands.

## Phase 2 — Networks on synthetic data

None of this waits for real data. `synthetic.to_participant_rows()` produces
exactly the columns `#FEAT-3` will, so everything built here re-runs on real
matches unchanged once Phase 3 lands. Start while Phase 1's pull runs.

- [ ] **#DL-1 · Read, run, then break the reference loop.** Read `train.py`
      and `models/mlp.py` top to bottom, then run `py run.py demo`. Then break
      each of the five lines on purpose and write down the symptom: skip
      `zero_grad()`, multiply the learning rate by 100, drop `backward()`,
      forget `model.eval()` (why does nothing happen yet?). Then the real
      test of the loop: build logistic regression as one `nn.Linear(n, 1)`,
      train it through `train_model()`, and match sklearn's floor on the
      demo's planted data. Working out which `weight_decay` corresponds to
      sklearn's `C` is part of it — sklearn *sums* the loss over rows,
      PyTorch *averages* it. Add the overfit-a-tiny-batch test for it (the
      MLP's version is in `tests/test_models.py`). Replaces the draft's
      `#STRETCH-1`; it is the first deep-learning task now, not a stretch.
- [ ] **#FEAT-2 · Vocabularies and encodings.** `features/encode.py`. Integer
      ids for the embedding models, multi-hot for the floor and the MLP — the
      draft's question plus the networks' one. Reserve `PAD_ID` and `UNK_ID`,
      fit on train rows only, and remember the vocabulary is part of the
      model. Build and test it against synthetic participant rows; two tests
      are waiting in `tests/test_features.py`.
- [ ] **#EVAL-2 · Measure the leak.** Participant rows share a match, so a
      random row split puts each match's near-twins on both sides of it. Run
      `py run.py train --model mlp --participant --signal 0` with
      `--split naive-row`, then `--split match-grouped`. The canary has
      nothing to find, so any score the naive split earns above 0.5 is the
      leak, measured. Log both (`#EVAL-1`). This is the draft's "are a match's
      10 participants independent?" question, answered with a number.
- [ ] **#DL-2 · Learned embeddings.** `models/embedding.py`. The first model
      here that is deep learning for a reason: champions and items as learned
      vectors, item sets pooled with `EmbeddingBag`, allies pooled rather than
      concatenated. Five design questions in the docstring. Write the
      overfit-a-tiny-batch test before the model works.
- [ ] **#DL-3 · Early stopping and the best weights.** The TODO block in
      `train.py`. The demo already shows why: on the canary, `val_loss` climbs
      from 0.69 to 0.78 while `train_loss` falls — the network memorising coin
      flips — and the model you get back is the last epoch's. Patience, a
      *copy* of the best `state_dict` (a reference is not a copy), and a choice
      between best-by-loss and best-by-AUC.
- [ ] **#DL-4 · Regularisation, read off the curves.** Dropout in the models,
      `--weight-decay` in the optimiser. Plot `TrainHistory` for a few
      settings in a notebook and learn to read the gap between the curves —
      the single most useful picture in this project. Note that dropout is the
      first thing that makes forgetting `model.eval()` actually matter.
- [ ] **#EVAL-3 · Does any network beat logistic regression?** The single most
      important comparison in the project, same role as Stocks' `#ML-3`.
      Several seeds per model, the spread reported, not one lucky run. Then
      the controlled version: `--strength 0 --synergy 2` builds a world made
      only of same-team interactions, which the linear floor is nearly blind
      to. On the first run, the plain MLP did not beat the floor there either —
      it overfit 2,100 matches instead. Does early stopping change that? The
      embedding model? More matches (`#EVAL-4`)? If no network beats the
      floor on real data in the end, that is the draft's Section 10 argument
      confirmed, and the README says so.

## Phase 3 — Real features

Numbered in the order they were added, listed in the order to build them.

- [ ] **#FEAT-1 · Items owned at the snapshot minute.**
      `features/item_timing.py`. Timeline purchase / sell / undo events up to
      minute 10 → the set of items still owned. Look at one real timeline
      JSON before designing anything. Decide what happens to components and
      consumables — whatever you keep here is what `#REC-1` can recommend.
      Tests waiting in `tests/test_features.py`.
- [ ] **#FEAT-4 · Per-minute frames.** `features/frames.py`, new in v3. Gold,
      xp, level and creep score per participant per minute, from the same
      timeline. Two consumers: `gold_diff_at_snapshot` (the confounder
      `#REC-1` must hold fixed) and the sequence model (`#DL-7`). "Minute 10"
      must mean the same moment here and in `#FEAT-1`.
- [ ] **#FEAT-3 · The participant table.** `features/build_feature_table.py`.
      Two steps now: materialise `item_snapshots` and `participant_frames`
      from the raw timelines, then join into exactly `PARTICIPANT_COLUMNS` —
      with `enemy_laner`, `allies` and `enemies`, which the draft's table
      lacked even though its CLI took `--enemy`. Leans on your SQL. When it
      works, `py run.py build-dataset` writes `data/processed/participants.parquet`
      and every Phase 2 command takes `--data` instead of synthetic data.

## Phase 4 — Networks on real data

- [ ] **#EVAL-4 · How many matches does each model need?** Train the floor, the
      MLP and the embedding model on 25 / 50 / 75 / 100% of the training
      matches and plot test AUC against size — a learning curve. Networks are
      data-hungry; logistic regression usually isn't. If the embedding
      model's curve is still climbing at your current count, pull more
      matches before tuning anything. This, not the draft's 2,000–5,000
      guess, decides the target in `config.TARGET_MATCH_COUNT_*`.
- [ ] **#DL-5 · Attention over the ten champions.** `models/composition.py`.
      Pooling forgets pairs; synergy and counters *are* pairs. Champion tokens
      plus side and role embeddings through a small `nn.TransformerEncoder`.
      Two symmetries to think about — order within a team (free, if there is
      no positional encoding) and swapping the teams (exact only if you build
      it in) — and tests waiting for both.
- [ ] **#DL-6 · Calibration.** Networks trained on cross-entropy are often
      overconfident, and the recommender ranks items by *differences* in
      predicted probability, so a miscalibrated model ranks confidently and
      wrongly. Draw a reliability diagram (predicted vs observed win rate, in
      bins) on the validation split; then try temperature scaling — one scalar,
      fitted on val, dividing the logits. Does it fix the curve without
      changing AUC? (It shouldn't change AUC — work out why.)

## Phase 5 — Recommendations (the MVP)

- [ ] **#REC-1 · `recommend_items()`.** `leagueml/recommend.py` — the draft's
      `#MOD-4`, now against a network. The draft's "lift against which
      baseline?" question still comes first. Then the trap the draft's version
      hid: items at minute 10 track the gold lead, so a naive recommender
      tells everyone to be richer. The synthetic world plants exactly this —
      build it there first, where you know the real item fit, and check you
      recover it. Also: what to feed for the eight champions the CLI doesn't
      name, and loading the vocabulary from the checkpoint.
- [ ] **#REC-2 · The `/api/recommend` endpoint.**
      `backend/app/routers/recommend.py`. Request and response models are done;
      the handler is yours. Load the checkpoint once at startup, not per
      request, and answer 503 rather than 500 when there is none. Replaces the
      draft's `#STRETCH-2`.

## Phase 6 — later

Only once Phase 5 runs end to end. Not paced week by week.

- [ ] **#DL-7 · A sequence model over the timeline.** `models/timeline.py`. A
      GRU over per-minute frames — who is winning, minute by minute. Runs on
      synthetic gold curves today (`py run.py train --model timeline`); on real
      data it needs `#FEAT-4`. The floor is strong — gold difference at the
      last minute alone — so beating it means reading the curve's *shape*.
      The closest thing here to Stocks' `#ML-11`.
- [ ] **#REC-3 · A frontend.** Three files in `frontend/` — HTML, CSS, JS, no
      build step — served by the FastAPI app that already mounts the folder if
      it exists. Stocks' shape. Replaces the draft's Streamlit `#STRETCH-3`.
- [ ] **#DL-8 · Look inside the embeddings.** Nearest neighbours of a few
      champions in the `#DL-2` embedding table, or a 2-D projection. On
      synthetic data, check it against `SyntheticTruth` — do planted synergy
      partners end up close? On real data, do champions that play alike? The
      best single picture this project can put in a README, if it works.

## Housekeeping (throughout, tagged so they sync)

- [ ] **#LML-1 · Real numbers in the README.** Fill in the Results table and
      Known limitations once real models are trained. No placeholder numbers
      in a public repo, and report the unimpressive ones honestly.
- [ ] **#LML-2 · The seed-sampling paragraph.** Which tiers you seeded
      ingestion from, and the bias that leaves in the dataset (an
      all-Challenger seed describes the top 0.1% of players).
      `get_entries_by_division()` exists to make this better than Challenger.
- [ ] **#LML-3 · Pick the patch when ingestion starts.** `config.PATCH_LABEL`
      and `TARGET_PATCH` say 26.18 / 16.18 — live on 2026-09-10 and stale by
      the time you get here. Set them to the live patch before the `#ING-4`
      pilot, and remember the two numbering schemes (config.py explains).
- [ ] **#LML-4 · An EDA notebook.** `notebooks/`, deliberately unscaffolded.
      Win rate by champion and role, remake rate, how sparse items are at
      minute 10 — plus the training curves from `#DL-4`.
