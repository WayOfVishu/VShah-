# Project Documentation
## Stocks — 30-Day Equity Forecast from Price, News, and Macro Data

**Status:** Scaffolding complete and running end-to-end. Ingest, feature
engineering, evaluation, and the API are built; the model itself is open work.
**Author:** Vishu
**Context:** Personal project. Grew out of the investments/valuation course
(Bodie, Kane & Marcus 9CE) and an interest in building ML systems end to end.
**Primary purpose:** Build a real ML pipeline over messy, heterogeneous,
genuinely hard data — not to make money, and not to produce a résumé line.
**Last updated:** 2026-09-05

---

## 1. Overview

A web app where a user types a stock — name, ticker, anything — and gets a
30-day forecast built from three datasets:

1. **DS1** the stock's own daily prices, 5 years (tabular)
2. **DS2** S&P 500, NASDAQ, Russell 2000, VIX + value/growth ETFs, 2 years (tabular)
3. **DS3** a language model's synthesis of everything written about it — company
   news from 12 to 2 months ago, news and community discussion from the last two
   months, and the political/economic backdrop over six months — returned as
   ~15 named sentiment scores rather than raw text

Those three go through one sklearn pipeline and out the other side as a
forecast, a Chapter 9 fair-value comparison, and a position recommendation.

**On DS3 and the count.** This began as five datasets, three of them raw text
that reached the model as TF-IDF blocks compressed into 72 anonymous SVD
components. Those three windows are still *retrieved* separately — they have
different point-in-time boundaries and must, or the panel stops being honest —
but they are now *synthesised* into one dataset before the model sees anything.
§5 covers the retrieval-versus-synthesis split; the short version is that GDELT
retrieves and Gemini reads, never the reverse.

The project has two halves that were deliberately separated. The **data and
math half** — provider integration, caching, window discipline, the textbook
formulas, validation methodology — is built. The **modelling half** is
scaffolded and left open, because that is the part with the personal interest
attached to it and doing it is the point.

## 2. Learning objectives

### Primary
- Build an ML pipeline over data that is heterogeneous (tabular + text),
  time-ordered, and low-signal — none of which the coursework datasets were.
- Get the **validation methodology** right. Random `train_test_split` on time
  series is the mistake that makes every naive stock model look brilliant and
  be worthless, and internalising why is more valuable than any model here.
- Turn the investments coursework from formulas-on-a-page into code that runs
  and is tested against the book's own worked examples.

### Secondary
- Integrate several real third-party APIs with rate limits, quotas, archive
  limitations, and unofficial endpoints that change without notice.
- Feature engineering on text where the signal is a *difference between two
  windows*, not a level.
- FastAPI service design against a slow, cache-dependent backend.

## 3. Scope

### In scope (v1)
- The five datasets, with graceful provider fallback down to fully offline
- The BKM Ch 5–8 math, tested against the textbook
- Walk-forward panel construction with enforced leakage discipline
- Purged time-series cross-validation and finance-appropriate metrics
- An sklearn pipeline scaffold with baseline models and a grid search
- FastAPI backend: resolve, datasets, predict
- A CLI covering every step

### Out of scope (v1)
- **Trading.** No broker integration, no order placement, no paper trading.
  This is a forecasting exercise. Position sizing is reported as Chapter 6's
  y*, which is an academic optimum and not advice.
- **Intraday.** Daily bars only. Intraday would need a different data tier and
  a different model class.
- **DCF / dividend discount / multiples valuation.** See §6.
- **Frontend.** Sketched in §8, not built.

## 4. The design decision everything rests on

Read literally, the spec produces **one labelled row per ticker**. Pull five
years of prices and a year of news, predict the next 30 days — that is a single
example, and you cannot fit a model to it.

The resolution is that every window is defined relative to an **as-of date**
which is a parameter, not "today". `build_panel` sweeps `as_of` backwards
through history, rebuilding all five datasets as they would have looked on each
date and labelling each row with the realised forward return. A few tickers over
a few years gives thousands of rows.

Consequences that shaped the rest of the codebase:

- `WindowSpec` is the single source of truth for the five lookbacks, so ingest
  can cache on `(dataset, window)` and stay coherent across as-of dates.
- Every window is **half-open on the right**, so nothing dated at or after
  `as_of` can reach a feature. Enforced in `DateWindow` and re-checked in
  `BaseProvider.clip_frame` / `clip_documents`.
- The label is computed from a **separate, forward-extended price frame**
  (`_fetch_label_prices`), never from the DS1 frame. Keeping them distinct makes
  it structurally hard to leak the target into the features.
- The last ~6 weeks of any sweep are not trainable — their forward return has
  not happened. `is_labellable` drops them rather than emitting null labels.
- Rows overlap. Weekly as-of dates with a 21-day horizon means consecutive rows
  share three of four weeks of forward return, which is why validation must
  purge (§7).

## 5. Architecture

```
                  free text ("apple")
                        |
                   resolve.py  --------> AAPL
                        |
                   WindowSpec(as_of)
                        |
        +---------------+---------------+
        |   ingest/registry  RETRIEVAL  |     provider fallback:
        |  yfinance | GDELT | FRED |    |     keyed -> keyless -> synthetic
        |  Reddit   | synthetic         |
        +---------------+---------------+
                        |
             3 text corpora, correctly dated
                        |
        +---------------+---------------+
        |   ingest/gemini    SYNTHESIS  |     reads only what GDELT returned;
        |  strict grounding, temp 0     |     search grounding NOT enabled
        +---------------+---------------+
                        |
              DatasetBundle  (DS1 + DS2 + brief + provenance)
                        |
        +---------------+---------------+
        |          features/            |
        |  tabular.py   <- finance/     |     BKM Ch 5-12 math
        |  synthesis.py <- the brief    |     -> gem_* named scores
        |  text.py                      |     -> lexicon control group
        |  assemble.py                  |
        +---------------+---------------+
                        |
                 one row  ->  build_panel  ->  the training panel
                        |
                   pipeline.py            <-- THE OPEN WORK
                        |
                   evaluate.py            purged walk-forward
                        |
                  backend/app             FastAPI
```

Provider selection is preference-ordered per slot with a synthetic floor, so the
project runs on a fresh clone with no keys and no network. That is the intended
first experience, not a degraded one — but a synthetic run mistaken for a real
one is the most expensive confusion available here, so provenance is carried in
`DatasetBundle.synthetic`, surfaced by `/api/health`, printed by
`py run.py providers`, and warned about by `evaluate.py`.

## 6. The finance module, and what is not in it

`stocks/finance/` implements the twelve chapter summaries in `References/Stocks`
(Bodie, Kane & Marcus, *Investments*, 9th Canadian Edition). Every worked
example in those chapters is pinned as a test.

The load-bearing chapter is **8, the single-index model**. Total risk splits
into two uncorrelated pieces — systematic (`beta² σ_M²`) and firm-specific
(`σ²(e)`) — and those two halves are driven by *different datasets in this
project*: DS2 drives the systematic half, DS3 the firm-specific half.
Regressing the stock on the index and keeping the residual is what stops the
sentiment features from competing with the index to re-explain market moves. The
`scl_*` features encode that split directly, and `#ML-8` proposes going further
and predicting the residual itself.

**Chapter 9 is what closes the loop between the two halves of the project.**
Chapters 5–8 are all descriptions of what a security did. The security market
line is the first forward statement — what a stock *ought* to return given its
beta — so the pipeline's output can be scored against it as an alpha rather than
reported as a bare percentage. That alpha is also precisely what Chapter 8's
`treynor_black_weights` consumes, so the model's output and the portfolio math
finally connect. `/api/predict` returns it as a `valuation` block.

**Chapters 10–12 are implemented as qualifications, and the code keeps them as
qualifications.** Ch 10 (`ff_*`) says one beta cannot describe systematic risk
and runs a joint factor regression instead of four univariate ones. Ch 11
(`evt_*`) supplies the event-study machinery and, more importantly, the joint
hypothesis problem: any alpha is equally evidence that the benchmark model is
wrong. Ch 12 (`tech_*`) supplies a behavioural mechanism for why price patterns
might persist *and* the data-mining warning that a large grid search over a
small overlapping panel is exactly the procedure that manufactures false ones.
None of the three are decoration — they are the reasons to distrust a good
score, and they live next to the code that produces it.

**Not implemented: DCF, dividend discount models, FCFE, comparable multiples.**
Those are BKM Ch 13 and 18. The twelve chapter summaries cover risk, return,
portfolio theory, asset pricing and market efficiency — not equity valuation
proper.

The full textbook *is* in `References/Stocks` — but it is a page-image scan
(1,006 JPEG-2000 images, no `ToUnicode` maps, 37 text operators in 322 MB), so
it cannot be extracted programmatically. Every formula in `finance/` was checked
against machine-readable source text and pinned to a worked example; formulas
transcribed by eye from page images would not meet that bar, and mixing the two
costs more trust than the formulas are worth.

Two ways forward, both deliberate choices rather than defaults:
- read the valuation chapter manually and add it under the rules in
  `docs/formula-reference.md` (cite, pin a worked example, add a row), or
- OCR the scan (tesseract) to get a checkable source first.

§10.5 tracks this as an open decision.

## 7. Validation methodology

The reference notebooks (`References/Stocks/Code Inspiration`) all use
`train_test_split(random_state=0)` and `StratifiedKFold`. Both shuffle, which is
correct there — those rows are independent customers — and wrong here, twice
over:

1. **Lookahead.** A shuffled fold trains on August and validates on May.
2. **Overlapping labels.** Consecutive rows share most of their forward return
   window. Shuffled, the near-twin of every validation row is in training.

`PurgedTimeSeriesSplit` fixes both: chronological expanding-window folds with a
gap that drops training rows whose label window reaches into validation.
`purge_gap_rows(step_days, horizon_days)` computes the gap from the sweep's own
parameters.

Metrics are chosen for a low-signal target. R² leads but is not the headline —
a 30-day equity return is close to unpredictable, and published work treats an
out-of-sample R² of 0.01 as real. `information_coefficient` (Spearman) is the
standard quant measure and is rank-based, so it is not dominated by the outliers
that dominate MSE. `hit_rate_top_decile` is the one that matters for acting on a
forecast: you never trade the median call.

**Expected performance, so nobody over-reads a run:**

| metric | chance | a real result | implausible |
|---|---|---|---|
| R² | 0 | 0.005 – 0.02 | > 0.15 |
| directional accuracy | 50% | 52 – 55% | > 60% |
| information coefficient | 0 | 0.03 – 0.05 | > 0.15 |

The synthetic providers generate price and text series that are **independent by
construction**. A strong score on `py run.py demo` therefore indicates leakage,
which makes the demo a usable regression test for it.

## 8. Web app (not built)

`GET /api/windows` is deliberately cheap — no data fetch — so a frontend can
draw the five-window timeline immediately while the slow work proceeds.

Sketch, if you build it (Vite + vanilla JS, matching the Portfolio project):

1. ticker box → `GET /api/resolve` → picker when `unambiguous` is false
2. timeline of the five windows → `GET /api/windows`
3. dataset summary card with **provenance visible** → `GET /api/datasets/{symbol}`
4. forecast fan chart → `POST /api/predict` (fan needs `#ML-10` first)
5. the Chapter 6 allocation, with a risk-aversion slider (A = 2…8)

**Latency is the real constraint.** A cold `/api/predict` builds all five
datasets — a dozen rate-limited provider calls, tens of seconds. Acceptable
locally, not acceptable deployed. The fix is a job queue with polling, and it is
worth building once the model is worth serving, not before.

## 9. Bill of materials

Free tier throughout, except Gemini — metered, and roughly $5 for a full
ten-symbol three-year sweep on `gemini-2.5-flash`. Cached, so re-runs are free.

| provider | key | limit | serves |
|---|---|---|---|
| yfinance | none | unofficial, rate-limits when swept | DS1, DS2 |
| GDELT DOC 2.0 | none | 250 records/query; ~1 call / 5s; indexes to 2015 | **all DS3 retrieval** |
| Gemini | free | low RPM on the free tier; ~10k tokens/call | **DS3 synthesis** |
| FRED | free | generous | macro numerics, **the risk-free rate** |
| Reddit (PRAW) | free | no date-range search since Pushshift closed | DS3, live inference only |
| NewsAPI | free | 30 days back — cannot build the baseline window | recent window only |
| Alpha Vantage | free | 25 requests/day | price fallback |

**Reddit's row is the one to read twice.** Its search API cannot filter by date
range at all — it returns today's top results whatever window is requested. That
makes it genuinely useful for live inference and actively harmful for a
historical panel row, where it would return 2026 posts against a 2023 as-of
date. It is therefore restricted to the recent window and is the only provider
whose *absence* costs nothing structural.

**GDELT is the keystone.** DS2 needs articles from 12 to 2 months ago, and
almost every consumer news API stops at 7–30 days. GDELT is the only free source
that reaches back far enough to make the historical sweep possible at all. It
returns metadata (title, date, source, tone) rather than article bodies, which
is a real limitation and a survivable one — headlines are dense with sentiment
by construction.

**GDELT is also the runtime budget.** It publishes no rate limit and sends no
`Retry-After`; it just starts returning 429s below roughly one call per five
seconds, and keeps returning them for some minutes afterwards. That interval,
times ~20 chunked calls per bundle, sets the cost of everything:

| | measured |
|---|---|
| one cold bundle | ~100 s |
| one cached bundle | < 1 s |
| 10 symbols × 3 years weekly, cold | ~40 h |

Three design responses, all in the code:

1. **Chunk sizes are the lever.** `GdeltProvider.chunk_days` (21 for news) and
   `MacroTextProvider.CHUNK_DAYS` (30) trade call count against coverage
   evenness. DS2/DS3 need fine resolution because comparing them is the point;
   DS5 does not. A test pins the combined budget at ≤ 30 calls per bundle so a
   well-meaning edit cannot quietly multiply sweep time.
2. **DS5 is ticker-independent**, so it amortises across a multi-symbol sweep —
   the first symbol at each as-of date pays, the rest hit the cache.
3. **A fully-failed pull raises rather than caching an empty corpus.** This is
   the important one. A rate-limited run that logs each failed chunk and
   continues would produce a bundle with zero documents, which is
   indistinguishable downstream from a stock nobody wrote about — and would
   then be cached as a legitimate result. Two bugs found during development
   were exactly this shape (see §12).

## 10. Open decisions

1. **Article bodies?** GDELT metadata-only is the default. Scraping bodies is
   slow, paywall-blocked, and legally murkier. Decide after `#ML-6` shows
   whether headline-level text carries signal at all.
2. **Target: raw return or Chapter 8 residual?** (`#ML-8`) The residual is the
   better-posed question but needs the market component added back
   analytically. Probably the highest-value experiment on the list.
3. **How wide a universe?** Currently a handful of tickers. A cross-sectional
   model over a few hundred names is a different and probably better project,
   and `treynor_black_weights` is already in place for it. It also multiplies
   ingest cost by the universe size.
4. **Sentiment backend.** VADER (default, no fitting, no leakage risk) vs
   FinBERT (better on news copy, 400MB, ~100x compute). Resolve with an ablation
   rather than by assumption.
5. **Equity valuation from the scanned textbook.** The full BKM PDF in
   `References/Stocks` covers DDM, FCFE and multiples, but as page images with
   no text layer (see §6). Either transcribe the chapter by hand into
   `finance/valuation.py` under the `docs/formula-reference.md` rules, or OCR the
   scan first so it can be verified like the rest. Not started; the risk-return
   and index-model math the summaries *do* cover is what the features actually
   use today.

## 11. Bugs found during development

Recorded because all three share a shape worth recognising: **they produce a
plausible result rather than an error.** That is the class of bug this project
is most exposed to, and the reason the codebase is so insistent about
provenance and sanity checks.

1. **Double-quoted boolean query.** `GdeltProvider.fetch_documents` wrapped its
   query in quotes to stop GDELT tokenising a bare ticker. When
   `MacroTextProvider` began sending a pre-quoted OR expression, it became
   `"("federal reserve" OR ...)"` — which GDELT parses as one literal phrase
   and matches nothing. It returns **HTTP 200 with an empty article list**, so
   DS5 silently came back with zero documents. Fixed with `_gdelt_query`, which
   quotes a bare term and passes a formed expression through, plus a test.

2. **Rate limit an order of magnitude tighter than assumed.** 1.2s between
   calls produced sustained 429s. Every chunk failed, each was logged and
   skipped, and `build_datasets` completed "successfully" with empty DS2, DS3
   and DS5. Fixed three ways: 5s interval, exponential backoff, and — most
   importantly — a fully-failed pull now **raises instead of caching**, because
   an empty corpus cached as a legitimate hit poisons every later run.

3. **`TruncatedSVD` crashing on a thin corpus.** `n_components=24` against a
   vocabulary of 15 terms raised. Not a misconfiguration — a normal consequence
   of a short sweep or a thinly-covered ticker, and unknowable until the
   vectoriser is fitted inside the fold. Fixed with `AdaptiveSVD`, which clamps.
   (This one failed loudly, which is why it was the cheapest of the three.)

Also corrected: `purge_gap_rows(step_days=30, horizon_days=21)` is 2, not 1 —
the label spans ~34 calendar days, so even a monthly sweep has overlapping rows.
The original docstring claimed 1 and a test caught it.

## 12. Honest framing

This project will very probably not predict stock prices usefully. That is not
pessimism, it is the base rate: 30-day equity returns are close to a random
walk, professionals with better data and more compute achieve information
coefficients of 0.03–0.05, and most published retail attempts at this are
measuring leakage rather than skill.

The project is worth building anyway, for reasons that do not depend on the
model working:

- the validation methodology transfers to every time-series ML problem
- the data engineering — heterogeneous sources, caching, graceful degradation,
  provenance — is the part that generalises
- the finance math is now executable and tested rather than notes on a page
- and finding out *rigorously* that the news datasets do not add signal
  (`#ML-6`) is a genuine result, reached honestly

The failure mode to avoid is not "the model does not work". It is "the model
appears to work because something leaked". Nearly every design choice in
`windows.py`, `assemble.py`, and `evaluate.py` exists to make that harder.
