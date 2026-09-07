# Stocks

A 30-day equity forecast built from three datasets: the stock's own price
history, the indices it moves with, and a language model's synthesis of
everything written about it — news, community chatter, and the macro backdrop.

Two halves. The **APIs and the math** are built. The **machine learning** is
scaffolded and left open on purpose — that is the part worth doing yourself.

```
py -m venv stocks-env --system-site-packages
./stocks-env/Scripts/python.exe -m pip install -r "../../Virtual Environments/Requirements/stocks.txt"
./stocks-env/Scripts/python.exe run.py demo
```

`demo` runs the whole thing offline on synthetic data — no keys, no network,
about a minute. If it prints an evaluation table, the plumbing works.

---

## The three datasets

Everything is defined relative to an **as-of date**, never "today". That one
decision is what makes the project trainable rather than a single prediction —
see [The one design decision worth knowing](#the-one-design-decision-worth-knowing).

```
|------------------------------ DS1 . prices, equity, 5y ----------------|
|             |----------------- DS2 . prices, index, 2y ---------------|
|                             |----- macro text, 6m --------------------|
|                    |--- news baseline, 12m->2m ------||- recent, 2m --|
                             \________________ DS3 ________________/
-------------------------------------------------------------------------> t
-5y           -2y   -12m                               -2m           as_of
```

| | dataset | shape | window | source |
|---|---|---|---|---|
| DS1 | the stock's prices | tabular | 5 years | yfinance |
| DS2 | S&P 500, NASDAQ, Russell, VIX + value/growth ETFs | tabular | 2 years | yfinance |
| DS3 | **synthesised sentiment** | ~15 named scores | 12 months | Gemini, over GDELT + Reddit |

**DS3 is a synthesis, not a corpus.** Three text windows are retrieved — company
news from 12→2 months ago, company news and community posts from the last two
months, and political/economic news over six months — and handed to Gemini in a
single call. It returns a fixed schema: how positive the coverage is in each
window, how much it moved, whether the story itself changed, how much attention
the name is getting, how divided the coverage is, and how confident it is in any
of that.

That replaces what used to be three raw TF-IDF blocks crushed into 72 unnamed
SVD components. Roughly fifteen dense, interpretable columns instead — on a
panel of a couple of thousand rows, that is the difference between features a
model can use and features it can only overfit.

The earlier/later split survives the collapse, because it was always the most
valuable thing here: a stock with steadily negative coverage is priced for it; a
stock whose coverage turned negative six weeks ago is not. Both windows go into
the same call, labelled but undated, and the model scores the change directly.

**Gemini synthesises. It does not retrieve.** GDELT is what makes a historical
panel possible at all — it is the only free source that can query a *dated*
window (`startdatetime`/`enddatetime`) and return what was published then and
nothing since. Google Search grounding is deliberately not enabled: grounded
search returns *today's* index, so scoring a 2023 as-of date would hand the
model articles written after the outcome it is being asked to predict.

Even reading correctly-dated documents, the model recognises them, so strict
grounding redacts the ticker and inferred company names, strips dates, shuffles
document order, and instructs the model to assume no outside knowledge. It is on
by default. `docs/TODO.md` #ML-0b explains how to measure what it costs.

**Nothing is required to run this.** Every provider slot falls back — keyed
provider → keyless provider → offline synthetic. Without `GEMINI_API_KEY`, DS3
is filled from a word list instead and every layer says so. `py run.py providers`
prints which one answered.

---

## The one design decision worth knowing

**Every window is measured from an as-of date, and the as-of date sweeps.**

Read literally, the spec produces exactly one labelled row per ticker: pull five
years of prices and a year of news, predict the next 30 days. You cannot fit a
model to one row.

So `as_of` is a parameter, and `build_panel` slides the whole window arrangement
backwards through history. Pick a date in 2022, build every dataset **as it
would have looked on that date**, label the row with what the stock actually did
over the next 30 days, step forward a week, repeat. Across a few tickers and a
few years that is thousands of rows.

```python
from stocks import build_panel
panel = build_panel(["AAPL", "MSFT"], date(2022, 1, 1), date(2025, 4, 1))
```

Everything upstream is as-of-parameterised so that this function can exist.
It is also why the leakage rule is enforced in code rather than by discipline:
every window is half-open on the right, so no row dated at or after `as_of` can
reach a feature. That is the failure mode that makes stock models look
brilliant in backtests and lose money live.

---

## Layout

```
run.py                  entry point — py run.py <command>
stocks/
  windows.py            the window spec and the leakage rule. Read this first.
  config.py             environment settings
  resolve.py            "apple" -> AAPL
  ingest/               retrieval + synthesis behind one provider-agnostic call
  finance/              Bodie/Kane/Marcus Ch 1-12 math (see below)
  features/             datasets -> a modelling table
  pipeline.py           the sklearn pipeline  <-- THIS IS YOURS
  evaluate.py           purged walk-forward validation, honest metrics
backend/app/            FastAPI: /api/resolve, /api/datasets, /api/predict
frontend/               the web app — 3 files, no build step
tests/                  220 tests, offline
docs/                   charter, TODO list, formula reference, API terms
```

The frontend is one HTML file, one stylesheet, one script, served straight from
FastAPI — the same shape as the Jobs dashboard's `public/`, and deliberately not
the Portfolio's Vite setup. The page loads three files and imports nothing, so a
bundler would add a toolchain to maintain and buy nothing.

```
py run.py serve              app + API on http://127.0.0.1:8000
py run.py serve --synthetic  same, on generated data — no network, no keys
```

---

## The finance module

`stocks/finance/` implements the math from the twelve chapter summaries in
`References/Stocks`, and every worked example in the textbook is pinned as a
test in `tests/test_finance.py`. If a refactor breaks one of the book's numbers,
that fails.

```
returns.py       Ch 5    holding-period return, annualization, Fisher, geometric mean
risk.py          Ch 5-6  volatility, Sharpe, VaR, drawdown, skew, kurtosis
portfolio.py     Ch 6-7  utility, capital allocation y*, two-asset, Markowitz
index_model.py   Ch 8    the SCL regression: alpha, beta, R-squared, residual risk
capm.py          Ch 9    the SML, forward alpha, zero-beta CAPM, hurdle rates
multifactor.py   Ch 10   joint factor regressions, APT arbitrage, SMB/HML proxies
event_study.py   Ch 11   abnormal returns, CAR, momentum and reversal
technical.py     Ch 12   MA crossovers, relative strength, trin, parity
```

**Chapter 8 says where the signal can live.** Total risk splits cleanly into two
uncorrelated pieces:

```
sigma_i^2  =  beta_i^2 * sigma_M^2   +   sigma^2(e_i)
 total          systematic               firm-specific
```

The two halves are driven by *different datasets*. Systematic risk is what DS2
(the indices) speaks to; firm-specific risk is what DS3 (the sentiment
synthesis) speaks to. Regressing the stock on the index and keeping the residual
separates them, so the sentiment features are asked to explain company-specific
moves instead of competing with the index to re-explain market moves.
`scl_gspc_firm_specific_share` tells the model how much room DS3 even has.

**Chapter 9 is what makes the forecast mean something.** Chapters 5–8 all
describe what a stock *did*. The security market line is the first statement
about what a stock *ought* to return given its beta, so a forecast can finally be
scored rather than just reported:

```
alpha = forecast - [ r_f + beta * (E(r_M) - r_f) ]
```

`/api/predict` returns this as a `valuation` block. "+2.3% over 30 days" is not
judgeable on its own — a beta-1.4 name is *owed* around 9.8% a year, so
forecasting less than that for it is a bearish call wearing a bullish sign.

**Chapters 10–12 each qualify that, and the code keeps the qualifications.**
Ch 10 says one beta is not enough (hence the joint `ff_*` regression against
market/SMB/HML proxies). Ch 11 says any alpha you find is equally evidence your
asset-pricing model is wrong — the joint hypothesis problem — which is why the
verdict calls anything inside ±1% "fairly priced". Ch 12 supplies a behavioural
*mechanism* for why price patterns might persist, and in the same breath warns
that testing enough patterns against history will always turn some up by chance.
A `GridSearchCV` over hundreds of combinations on a couple of thousand
overlapping rows is exactly that machine, which is why the purged walk-forward
split matters more than any indicator in the table.

What is deliberately **not** here: DCF, dividend discount models, FCFE,
multiples. Those are BKM Ch 13 and 18, and the twelve chapter summaries cover
risk, return, portfolio theory, asset pricing and market efficiency — not
equity valuation proper.

`References/Stocks/Bodie-Kane-Marcus Investments Full Textbook.pdf` does contain
the valuation chapters, but it is a **page-image scan** — 1,006 JPEG-2000
images, no text layer — so it cannot be extracted and checked the way the
summaries were. Everything in `finance/` is verified against a machine-readable
source and pinned to the book's own worked examples; adding formulas that could
not be checked the same way would quietly lower the bar for the whole module.

If you want valuation in here, read the chapter yourself and add it following
the three rules at the bottom of `docs/formula-reference.md`.

---

## Commands

```
py run.py demo                          offline end-to-end. Start here.
py run.py providers                     which provider serves each dataset
py run.py windows --as-of 2025-06-01    print the five windows for a date
py run.py resolve "apple"               free text -> ticker candidates
py run.py fetch AAPL --save             build one bundle, write it to data/interim/
py run.py build-panel --symbols AAPL,MSFT --start 2022-01-01
py run.py train --panel data/processed/panel.parquet
py run.py serve                         web app + API on :8000, docs at /docs
py run.py serve --synthetic             ...on generated data, fully offline
```

**A first real `build-panel` is an overnight job, and that is a hard
constraint, not a tuning problem.** GDELT publishes no rate limit but starts
returning 429s at anything under about one call per five seconds, and a single
bundle needs ~20 calls (DS2 chunks into 15, DS3 into 3, DS5 into 6). So budget
roughly **100 seconds per cold bundle**. 10 symbols × 3 years weekly is ~1,560
bundles — call it 40 hours cold.

Three things make that tractable:

- **The cache.** Re-runs read Parquet and JSON from `data/raw/` and are
  effectively instant. Only the first sweep pays.
- **DS5 is ticker-independent**, so across a multi-symbol sweep the first
  symbol at each as-of date pays for the macro pull and the rest hit the cache.
- **`--synthetic` is free.** Develop the model against it, then run the real
  sweep once, overnight.

If a sweep does get rate-limited, `GdeltProvider` backs off exponentially and
raises rather than caching an empty corpus — a silently empty DS2 is
indistinguishable downstream from a stock nobody wrote about, so it must not be
allowed to look like a successful fetch.

---

## What is left for you

`stocks/pipeline.py` is the file to work in. The preprocessing is wired
(`ColumnTransformer` → `Pipeline` → `cross_validate` → `GridSearchCV`, the same
shape as your Group20 notebook), three baseline models are in place, and it
runs today. Eleven `#ML-n` tags mark the open work, tracked in `docs/TODO.md`.

The highest-value one is **#ML-6, the ablation**: fit on numeric features only,
then text only, then both. If the combined model does not beat numeric-only,
the news datasets are not earning their keep, and it is much better to learn
that in week one than week six. `split_columns` makes it a two-line experiment.

### One change from your reference notebooks, and why

Your assignments all used `train_test_split(random_state=0)` and
`StratifiedKFold`. Both shuffle. That is correct for the car-insurance data,
where rows are independent customers, and it is catastrophic here.

Two separate problems:

1. **Lookahead.** A shuffled fold trains on August and validates on May.
2. **Overlapping labels.** Weekly as-of dates with a 21-day horizon means
   consecutive rows share three of four weeks of forward return. Shuffled, the
   near-twin of every validation row sits in training, and the model gets credit
   for memorising.

So `evaluate.py` uses `PurgedTimeSeriesSplit` — chronological folds with a gap
that drops training rows whose label window reaches into validation. Your scores
will look *worse* than the notebook's. That is the point.

### Calibrate before you tune

A 30-day equity return is close to unpredictable. Published research treats an
out-of-sample R² of **0.01** as a genuine result.

| metric | chance | a real result |
|---|---|---|
| R² | 0 | 0.005 – 0.02 |
| directional accuracy | 50% | 52 – 55% |
| information coefficient | 0 | 0.03 – 0.05 |

If your first run shows R² 0.4, something leaked. Check the `_warn_on_leakage`
output and re-read `windows.py`. The synthetic providers generate price and text
series that are **independent by construction**, so a strong score on
`py run.py demo` is itself evidence of a bug — which is a useful thing to be
able to test for.

---

## Configuration

Everything is optional. Copy `.env.example` to `.env` and fill in what you have.

| key | unlocks | notes |
|---|---|---|
| — | prices, news, macro text | yfinance and GDELT need no key |
| `FRED_API_KEY` | the real risk-free rate | free, one minute to register. Worth it — excess returns need it |
| `REDDIT_CLIENT_ID/SECRET` | community sentiment in DS3 | free non-commercial, but signup is manual-approval since late 2025 |
| `NEWSAPI_API_KEY` | an alternative news source | **also needs `NEWSAPI_ALLOW_NONPRODUCTION=true`** — see below |
| `ALPHAVANTAGE_API_KEY` | price fallback | 25 requests/day — fine for the app, not for a sweep |

### Are the APIs actually free?

Yes, all six, at the volumes here — audited against each provider's own terms in
**[`docs/api-terms.md`](docs/api-terms.md)**. Three carry conditions that the
code and the web app honour:

- **GDELT** is free for any use *including commercial*, but requires a citation
  and a link. Both are in the app footer.
- **FRED** requires a specific disclaimer sentence, verbatim. Also in the
  footer, and a test asserts it is still there.
- **Yahoo Finance** (via yfinance) is *"intended for personal use only"*. Fine
  for this project, which is personal. **Not fine for a public or commercial
  deployment** — and since yfinance supplies all price data, it is the first
  thing to re-source if that ever changes.

One finding changed the code: **NewsAPI's free plan forbids production use**
("cannot be used in a staging or production environment (including
internally)"). A key alone therefore no longer enables it — you also have to set
`NEWSAPI_ALLOW_NONPRODUCTION=true`, so turning on a development-only provider is
a deliberate act rather than a side effect of pasting a key into `.env`.

Without `FRED_API_KEY` the risk-free rate falls back to a flat 4% and says so in
the log. That is wrong in a stable, documented way; assuming zero would silently
turn every excess return into a total return and break the Chapter 8 regression.
