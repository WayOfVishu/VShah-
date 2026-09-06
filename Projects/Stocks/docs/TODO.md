# TODO

What was built for you, and what is deliberately left open.

Tags match the `#ML-n` comments in `stocks/pipeline.py`. Work top-down within
each phase; the ordering is by information gained per hour, not by difficulty.

---

## Status

| area | state |
|---|---|
| window spec + leakage rule | **done**, 24 tests |
| finance math (BKM Ch 5–8) | **done**, 40 tests against the textbook's worked examples |
| ingest (5 datasets, 4 providers + synthetic) | **done** |
| feature engineering | **done**, ~150 numeric + 3 text blocks |
| sklearn pipeline scaffold | **done** — runs, but unmodelled |
| purged walk-forward evaluation | **done** |
| FastAPI backend | **done** — `/predict` serves a baseline until a model exists |
| **the model** | **yours** |
| frontend | not started — see charter §8 |

---

## Phase 1 — before you model anything

The point of this phase is to find out whether the project's premise holds
before spending time tuning. All three are cheap.

- [ ] **#ML-3 · The zero baseline.** Add "predict 0" and "predict the trailing
      21-day return" to `baseline_models()`. If none of Ridge / RF / GBM beat
      *predict zero* on R², the pipeline is not adding information and no
      amount of hyperparameter search will change that.
      **This is the single most important comparison in the project.**

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

## Non-ML work, if you want it

- [ ] **Frontend.** Nothing exists. Charter §8 sketches it: a ticker box, the
      five-window timeline (`GET /api/windows` is cheap and needs no data
      fetch), the forecast fan chart, and the Chapter 6 allocation. Vite +
      vanilla JS to match the Portfolio project.
- [ ] **Job queue for `/api/predict`.** A cold request builds all five datasets
      — tens of seconds. Fine locally, not fine deployed. Worth doing once the
      model is worth serving, not before.
- [ ] **Article bodies.** GDELT gives metadata only; `fetch_full_text=True`
      scrapes, badly. `trafilatura` does boilerplate removal properly. Only
      worth it if headline-level text shows signal in #ML-6.
- [ ] **Expand `resolve.ALIASES`,** or drop it and lean on Yahoo search.

---

## Things deliberately not done, and why

- **DCF / dividend discount / multiples.** Not covered by the eight chapter
  summaries. The full textbook in `References/Stocks` does cover it, but it is a
  page-image scan with no text layer, so it cannot be extracted and verified the
  way the summaries were. Writing unverified formulas next to verified ones would
  make the whole `finance/` module less trustworthy. Add it by reading the
  chapter yourself, or OCR the scan first — see charter §6.
- **A trained model checked into the repo.** `/api/predict` returns a shrunk
  trailing-drift baseline and flags itself `trained: false`. Shipping a model
  nobody validated would be worse than shipping none.
- **Pushshift / historical Reddit.** The public API closed in 2023. DS3's
  community half is genuinely limited to recent data; `Document.kind` exists so
  the feature code can count news and community separately rather than reading a
  shrinking corpus as falling interest.
- **`pip install -e .`** — no packaging ceremony for a project run from its own
  directory. `tests/conftest.py` handles the import path.
