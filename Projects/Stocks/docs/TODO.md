# TODO

What was built for you, and what is deliberately left open.

Tags match the `#ML-n` comments in `stocks/pipeline.py`. Work top-down within
each phase; the ordering is by information gained per hour, not by difficulty.

---

## Status

| area | state |
|---|---|
| window spec + leakage rule | **done**, 24 tests |
| finance math (BKM Ch 5–12) | **done**, 94 tests against the textbook's worked examples |
| ingest (5 retrieval windows → 3 datasets, 5 providers + synthetic) | **done** |
| sentiment synthesis (Gemini) | **done**, verified against the live API — needs `GEMINI_API_KEY`, degrades to a lexicon without one |
| feature engineering | **done**, ~400 numeric columns, no TF-IDF by default |
| sklearn pipeline scaffold | **done** — runs, but unmodelled |
| purged walk-forward evaluation | **done** |
| FastAPI backend | **done** — `/predict` serves a baseline until a model exists |
| **the model** | **yours** |
| **experiment log** | **yours** — nothing persists results today, see #ML-LOG |
| frontend | not started — see charter §8 |

---

## Phase 0 — somewhere to put the answers

Do this first. It is thirty minutes and it is the difference between this
project having findings and having anecdotes.

- [ ] **#ML-LOG · An experiment log.** `evaluate.py` computes scores and
      returns them. Nothing persists — there is no `to_csv`, no `to_json`, no
      write path anywhere in `stocks/`, and `data/processed/` holds a single
      `.gitkeep`. Every number in Phase 1 below is a *comparison*, and right
      now every one of them scrolls off your terminal and is gone.

      That matters more here than it would in most projects, because the
      headline results of this one are negative results. "Ridge did not beat
      predict-zero" and "Gemini did not beat the lexicon" are the findings —
      #ML-6 says so outright: *"that is a finding, not a failure. Report it
      either way."* A finding you cannot produce on demand three weeks later is
      not a finding. This is also the artifact that answers "what did your
      pipeline actually show?" in a way that 13,664 lines of code cannot.

      **The schema question — decide this before writing the writer.** What has
      to be in one row for a future you to trust it, and to compare it against a
      row logged a month later? Some of it is obvious (the metric, the model
      name, the date). The rest is the exercise, and the test is: *if these two
      rows disagree, can I tell whether the model changed or the data did?*
      Things worth arguing about:
        - the **window spec** the panel was built from — `windows.py` exists
          precisely because "which data existed as of when" is the whole game,
          and two scores from different as-of dates are not comparable
        - the **feature set** — numeric-only / text-only / both (#ML-6 turns
          this into the primary key of the ablation, so it cannot be an
          afterthought)
        - `GEMINI_MODEL` **and** `GEMINI_STRICT_GROUNDING` — the operational
          notes below already warn that a pinned model can be retired and that
          mixing two models' scores in one panel is a silent corruption.
          A row that does not record which model scored its briefs cannot be
          compared against one from before a bump.
        - the **random seed**, and whether you set one at all. If you did not,
          two identical rows differing by 0.01 R² mean nothing, and you will
          not know that when you look back.
        - **n** — how many rows the panel had. An R² from 40 observations and
          one from 400 are not the same claim.

      Where it lives is a smaller decision than what it contains: append-only
      CSV or JSONL under `data/processed/`, or a markdown table in
      `docs/RESULTS.md` you write by hand. Append-only beats a file you rewrite
      — the point is to accumulate. Whatever you choose, `.gitignore` currently
      ignores `data/`, so decide deliberately whether the log is an artifact
      that gets committed (it should be; it is the output of the project) or
      one that stays local.

- [ ] **#ML-LOG-b · The canary goes in the log too.** The leakage canary in
      Phase 1 is a pass/fail you will run many times across many code changes.
      Logging its result each time turns it from a spot check into a
      regression trace — and if it ever starts passing suspiciously well, the
      log tells you *which change* preceded that, which is the only cheap way
      to find a leak you introduced weeks ago.

## Phase 1 — before you model anything

The point of this phase is to find out whether the project's premise holds
before spending time tuning. All three are cheap. **Log every result**
(#ML-LOG) — these four experiments are the ones most worth being able to
reproduce and quote.

- [ ] **#ML-3 · The zero baseline.** Add "predict 0" and "predict the trailing
      21-day return" to `baseline_models()`. If none of Ridge / RF / GBM beat
      *predict zero* on R², the pipeline is not adding information and no
      amount of hyperparameter search will change that.
      **This is the single most important comparison in the project.**

- [ ] **#ML-0 · Does Gemini beat VADER?** The one experiment this rewrite
      created, and it should run before any tuning. The panel carries both the
      `gem_*` block (a language model's read of the corpora) and the `ds2_*`,
      `ds3_*`, `ds5_*`, `shift_*` lexicon features computed from the *same*
      documents. Fit on each set separately, then on both. If `gem_*` does not
      beat the lexicon out of sample, the API bill is buying nothing and the
      honest move is to cut it. `split_columns` plus a prefix filter makes this
      a few lines.

- [ ] **#ML-0b · Does strict grounding cost anything?** Build a small panel
      twice, once with `GEMINI_STRICT_GROUNDING=1` and once with `0`, and
      compare out-of-sample scores. Strict grounding redacts tickers and dates
      so the model cannot recognise what it is reading. If the two score the
      same, recognition was not helping and strict mode is free. If ungrounded
      scores dramatically better, **that gap is lookahead bias, not skill** —
      the model is remembering how the quarter ended. Do not read a better
      ungrounded score as a reason to ship ungrounded.

- [ ] **#ML-6 · The ablation.** Fit numeric-only, text-only, and both.
      `split_columns` already partitions them. If numeric+text does not beat
      numeric-only, DS2/DS3/DS5 are not earning their keep — and that is a
      finding, not a failure. Report it either way.

- [ ] **Check the leakage canary.** Run `py run.py demo`. The synthetic price
      and text series are independent by construction, so R² should be ≈ 0 and
      directional accuracy ≈ 50%. If the demo scores *well*, stop and find the
      leak before touching real data.

## Phase 2 — make the pipeline fit the problem

- [ ] **#ML-1** `sublinear_tf=True` on the TF-IDF vectorizers. DS2 spans ten
      months and DS3 spans two, so raw term frequencies are dominated by
      corpus length; log-scaling usually helps a lot on documents this uneven.
- [ ] **#ML-2** Tune `svd_components`. 24 is a guess. Plot
      `explained_variance_ratio_.cumsum()` (forwarded through `AdaptiveSVD`)
      and pick the knee.
- [ ] **#ML-4** Try alternatives to SVD for the text block: `SelectKBest(f_regression)`
      on raw TF-IDF, or drop SVD and let Ridge regularise the sparse matrix
      directly — it handles high-dimensional sparse input better than trees do.
- [ ] **#ML-5** Sample weights. 2021 rows are less relevant to a forecast made
      today than last quarter's. Exponential decay in `meta_as_of`.

## Phase 3 — change the question

These are the ideas most likely to actually move the number.

- [ ] **#ML-8 · Predict the residual, not the return.** A model predicting raw
      returns spends most of its capacity re-learning "the market moved", which
      DS4 already tells you. Predict the Chapter 8 residual
      (`finance.index_model.residual_series`) — the question DS2/DS3 can
      actually answer — then add the market component back analytically via
      beta. Strongest single idea on this list.
- [ ] **#ML-10 · Quantile regression.** Three
      `GradientBoostingRegressor(loss="quantile", alpha=0.1/0.5/0.9)` fits give
      the app an honest fan chart. On a near-unpredictable target, an interval
      is worth more to a user than a point estimate, and `/api/predict` already
      has an `interval.method` field waiting to say `model_quantiles`.
- [ ] **#ML-9 · Multi-horizon.** The app wants a 30-day *path*, not one number.
      `compute_target` already takes a horizon; fit separate models at 1/5/10/21
      days. Separate models usually beat `MultiOutputRegressor` here — short and
      long horizons genuinely behave differently.
- [ ] **#ML-7** Try `target_kind="direction"`. Compare a calibrated
      classifier's expected value against the regressor's point estimate.

## Phase 4 — the interesting version

- [ ] **#ML-11 · A sequence model** over raw daily bars (LSTM/GRU or a small
      temporal CNN) instead of hand-built rolling features. torch and keras are
      already installed. Do this **after** the tabular baseline is solid — it is
      only interesting once there is a number to beat.
- [ ] **FinBERT for sentiment.** `sentiment_backend="finbert"` is wired.
      Meaningfully better than VADER on news copy; ~400MB download and ~100x
      the compute. Do it only if the sentiment features survive #ML-6.
- [ ] **Cross-sectional model.** Train on a universe rather than a few tickers
      and rank. `finance.index_model.treynor_black_weights` is implemented and
      takes predicted alphas straight from the model — that is the bridge from
      "forecast one stock" to "build a portfolio".

---

## Operational notes from first live use

- **Pin the model, and re-check it occasionally.** `GEMINI_MODEL` is pinned
  rather than aliased to `-latest` on purpose: an alias would change the meaning
  of every cached brief the day Google ships a revision, and a panel whose
  features shifted mid-sweep is worse than one built on an older model. The cost
  is that a pinned model can be retired (`gemini-2.5-flash` was) or become
  contended. `py run.py models` is the check; clear `data/raw/gemini__*` when you
  bump it, or you will mix two models' scores in one panel.

- **Availability, not rate limiting, is the binding constraint.** Measured back
  to back: `gemini-3.6-flash` and `gemini-3.8-flash` both 503'd through four
  retries, `gemini-3.5-flash` answered in 11s. If a sweep is crawling, try a
  different flash model before assuming you are being throttled.

- **Budget the first sweep by GDELT, not Gemini.** A cold bundle is ~20 GDELT
  calls at one per five seconds — roughly 100 seconds — against one Gemini call
  of a few seconds. Gemini is the thing that costs money; GDELT is the thing
  that costs time.

---

## Non-ML work, if you want it

- [ ] **Frontend.** Nothing exists. Charter §8 sketches it: a ticker box, the
      window timeline (`GET /api/windows` is cheap and needs no data fetch),
      the forecast fan chart, the Chapter 6 allocation, and now the Chapter 9
      `valuation` block — fair return, alpha, and the verdict word. The brief's
      `sentiment_rationale` is worth surfacing too: a sentiment score with no
      traceable reason is not something to ask a user to act on. Vite + vanilla
      JS to match the Portfolio project.
- [ ] **Job queue for `/api/predict`.** A cold request builds every dataset and
      makes a Gemini call — tens of seconds. Fine locally, not fine deployed.
      Worth doing once the model is worth serving, not before.
- [ ] **Harden `_name_variants`.** Strict grounding redacts the ticker plus
      company names inferred from capitalised tokens recurring across titles.
      A company mentioned in only a couple of documents will not clear the
      threshold, and a distinctive product name ("iPhone") is not caught at
      all. This raises the cost of recognition without making it impossible.
      A real entity list — or a cheap NER pass over titles — would close most
      of the remaining gap. Worth doing if #ML-0b shows a large grounded /
      ungrounded spread.
- [ ] **Article bodies.** GDELT gives metadata only; `fetch_full_text=True`
      scrapes, badly. `trafilatura` does boilerplate removal properly. Only
      worth it if headline-level text shows signal in #ML-6.
- [ ] **Expand `resolve.ALIASES`,** or drop it and lean on Yahoo search.

---

## Things deliberately not done, and why

- **DCF / dividend discount / multiples.** Not covered by the twelve chapter
  summaries — that material is BKM Ch 13 and 18. The full textbook in
  `References/Stocks` does cover it, but it is a page-image scan with no text
  layer, so it cannot be extracted and verified the way the summaries were. Writing unverified formulas next to verified ones would
  make the whole `finance/` module less trustworthy. Add it by reading the
  chapter yourself, or OCR the scan first — see charter §6.
- **A trained model checked into the repo.** `/api/predict` returns a shrunk
  trailing-drift baseline and flags itself `trained: false`. Shipping a model
  nobody validated would be worse than shipping none.
- **Pushshift / historical Reddit.** The public API closed in 2023, and Reddit's
  own search cannot filter by date range at all — it returns today's top results
  whatever window you ask for. So Reddit contributes to live inference and
  contributes *nothing trustworthy* to a historical panel row; asking it for
  2023 posts would return 2026 ones, which is lookahead in its purest form.
  `Document.kind` exists so the feature code can count news and community
  separately rather than reading a shrinking corpus as falling interest.

- **Google Search grounding on the Gemini call.** Tempting, and fatal. Grounded
  search queries *today's* index, so scoring a historical as-of date would hand
  the model articles written after the outcome it is being asked to predict.
  Gemini synthesises what GDELT retrieved; it never retrieves. GDELT is the
  component that makes point-in-time news possible
  (`startdatetime`/`enddatetime`) and it is therefore not optional, despite
  needing no key.

- **Dropping GDELT now that Gemini is in the loop.** Considered and rejected for
  the reason above. An LLM cannot replace a dated archive: without grounding it
  has a knowledge cutoff and no recency, and with grounding it has no history.
  GDELT stopped being a *dataset* and became *plumbing*; it did not become
  removable.
- **`pip install -e .`** — no packaging ceremony for a project run from its own
  directory. `tests/conftest.py` handles the import path.
