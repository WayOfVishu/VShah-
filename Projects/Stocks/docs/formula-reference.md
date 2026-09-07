# Formula Reference

Every formula implemented in `stocks/finance/`, mapped to its source in Bodie,
Kane & Marcus, *Investments*, 9th Canadian Edition — the chapter summaries in
`References/Stocks/`. Chapters 1–12 are covered.

The purpose of this file is traceability. If you are ever unsure whether the
code is right, this table tells you which page to check it against, and
`tests/test_finance.py` asserts the book's own worked examples.

**Conventions.** All rates are decimals (8% is `0.08`), never percentages.
`risk_free_rate` arguments are annual and de-annualized internally.
Annualization uses 252 trading days. Return series may contain NaN; every
function drops rather than fills.

---

## Chapter 5 — Risk, Return, and the Historical Record

| ID | Formula | Function |
|---|---|---|
| F1 | `1 + r_real = (1 + r_nom) / (1 + i)` | `returns.real_rate_exact` |
| F1′ | `r_real ≈ r_nom − i` | `returns.real_rate_approx` |
| F2 | `1 + r_annual = [1 + r(T)]^(1/T)` | `returns.annualize` |
| F3 | `E(r) = Σ p(s)·r(s)` ; `Var = Σ p(s)·(r(s) − E(r))²` | `risk.scenario_expected_return`, `risk.scenario_variance` |
| F4 | `1 + g = [(1+r₁)…(1+rₙ)]^(1/n)` | `returns.geometric_mean_return` |
| F5 | `S = [E(r_p) − r_f] / σ_p` | `risk.sharpe_ratio` |
| F6 | `VaR(1%) = mean − 2.33·SD` | `risk.value_at_risk_normal` |
| LO2 | `EAR = (1 + APR/n)ⁿ − 1` | `returns.effective_annual_rate` |
| LO6 | empirical VaR, skew, excess kurtosis | `risk.value_at_risk_historical`, `risk.skewness`, `risk.excess_kurtosis` |

**Worked examples pinned as tests.** Example 5.1: 8% nominal / 5% inflation →
2.86% exact, 3.00% approximate, a 14 bp overstatement. Example 5.9: risk
premium 5.76%, SD 19.49% → Sharpe 0.30.

**Notes.**
- Arithmetic mean forecasts *next period*; geometric mean describes what an
  investment *did*. Reporting the arithmetic mean as historical performance
  overstates it. The gap is roughly half the variance for near-normal returns,
  and `eq_risk_arith_geo_gap` is emitted as a feature for that reason.
- The 2.33 in F6 is the textbook's rounding of 2.3263. Kept as the book's value
  so the worked examples reconcile.
- Empirical VaR is preferred for individual equities: they are reliably
  fat-tailed (excess kurtosis typically 3–10), and the normal formula is
  correspondingly too optimistic. `eq_risk_var_gap` measures exactly that.

Beyond the textbook, `risk.expected_shortfall` and `risk.max_drawdown` are
included: VaR gives a threshold and says nothing about how far past it losses
go, and standard deviation misses path risk entirely.

---

## Chapter 6 — Capital Allocation to Risky Assets

| ID | Formula | Function |
|---|---|---|
| F1 | `U = E(r) − ½·A·σ²` | `portfolio.utility_score` |
| F2 | `E(r_C) = r_f + y·[E(r_P) − r_f]` | `portfolio.complete_portfolio_return` |
| F3 | `σ_C = y·σ_P` | `portfolio.complete_portfolio_std` |
| F4 | `y* = [E(r_P) − r_f] / (A·σ_P²)` | `portfolio.optimal_risky_weight` |
| F5 | `E(r_C) = r_f + [(E(r_P) − r_f)/σ_P]·σ_C` | `portfolio.capital_allocation_line` |

**Example 6.4, pinned:** r_f = 7%, E(r_P) = 15%, σ_P = 22%, A = 4 → y* = 0.41,
E(r_C) = 10.28%, σ_C = 9.02%, and the complete portfolio's Sharpe ratio equals
P's (8/22 = 0.36). Every point on the CAL shares one slope — leverage scales
risk-adjusted return, it cannot improve it.

**F4 is where this project's math becomes a decision.** A forecast of "+2.3%
over 30 days" is not actionable. The same forecast with 38% annualised
volatility, implying y* = 0.16 for a moderately risk-averse investor, is.
`/api/predict` returns this as its `allocation` block.

`y*` is returned **unclamped**. Above 1 means borrowing at the risk-free rate to
lever up; below 0 means the forecast risk premium is negative, i.e. short. Both
are the formula saying something specific, so the API carries the raw value
alongside a clamped one for display.

Typical A values from the chapter: 2 (aggressive), 3.5, 4 (representative),
5 (conservative).

---

## Chapter 7 — Optimal Risky Portfolios

| ID | Formula | Function |
|---|---|---|
| F1 | `E(r_P) = w_D·E(r_D) + w_E·E(r_E)` | `portfolio.two_asset_return` |
| F2 | `σ_P² = w_D²σ_D² + w_E²σ_E² + 2w_Dw_E·Cov` | `portfolio.two_asset_variance` |
| F3 | `w_D(min) = [σ_E² − Cov] / [σ_D² + σ_E² − 2Cov]` | `portfolio.minimum_variance_weights` |
| F4 | `w_D* = [E(R_D)σ_E² − E(R_E)Cov] / [E(R_D)σ_E² + E(R_E)σ_D² − (E(R_D)+E(R_E))Cov]` | `portfolio.optimal_two_asset_weights` |
| F5 | `E(r_P) = Σ w_i E(r_i)` ; `σ_P² = w′Σw` | `portfolio.portfolio_return`, `portfolio.portfolio_variance` |

**Examples 7.1–7.3, pinned:** bond fund D (E = 8%, σ = 12%), stock fund E
(E = 13%, σ = 20%), Cov = 72 (ρ = 0.30), r_f = 5%.
Minimum-variance: w_D = 0.82, σ = 11.45% — **below either component's own
standard deviation**, which is the diversification effect in one number.
Optimal risky: w_D = 0.40, E(r_P) = 11%, σ_P = 14.2%, Sharpe 0.42.
Complete portfolio at A = 4: y* = 0.7439 → 29.76% bonds, 44.63% stocks.

**F4 takes excess returns, not total returns.** The chapter flags this as a
common confusion, and passing total returns produces a plausible wrong answer
rather than an error — hence the parameter names.

F5's input burden is what motivates Chapter 8: n assets need n expected returns,
n variances, and n(n−1)/2 covariances. At n = 500 that is over 124,000
covariance estimates.

---

## Chapter 8 — Index Models

**The most useful chapter here**, because it says something about a *single
stock* rather than a portfolio, and a single stock is what the app is asked
about.

| ID | Formula | Function |
|---|---|---|
| F1 | `r_i = E(r_i) + β_i·m + e_i` ; `σ_i² = β_i²σ_m² + σ²(e_i)` | the decomposition `SCLResult` reports |
| F2 | `R_i = α_i + β_i·R_M + e_i`, R = r − r_f | `index_model.fit_scl` |
| F3 | `E(R_i) = α_i + β_i·E(R_M)` | `SCLResult.alpha`, `.beta` |
| F4 | `R² = 1 − σ²(e_i)/σ_i² = β_i²σ_M²/σ_i²` | `SCLResult.r_squared` |
| F5 | `S_P² = S_M² + [α_A/σ(e_A)]²` | `index_model.combined_sharpe_squared` |
| F6 | `w_i = [α_i/σ²(e_i)] / Σ[α_j/σ²(e_j)]` | `index_model.treynor_black_weights` |

**Textbook example:** Suncor (SU) on the S&P/TSX Composite, 60 months of
2013–2017 → α = 0.0016 (t = 0.256, not significant), β = 1.1048 (t = 3.87,
significant), R² = 0.2052, correlation 0.4530.

**F1 is the idea the whole feature design is built around.** Total risk splits
into systematic and firm-specific, and in this project those two halves are
driven by *different datasets*:

```
σ_i²   =   β_i²σ_M²        +    σ²(e_i)
           ^ DS4, DS5           ^ DS2, DS3
           indices, macro       company news, community
```

So `scl_gspc_r_squared` tells the model how much of the stock is a market
instrument, and `scl_gspc_firm_specific_share` (= 1 − R²) tells it how much room
the news datasets have to explain anything. A name at R² 0.7 is mostly the
market; a name at 0.15 is mostly its own story. Handing the model that ratio
explicitly means it can weight the text block by regime rather than inferring it.

**Why F2 requires excess returns.** It is the *spread* between the market return
and the risk-free rate that signals macroeconomic news — an 8% return was
disappointing when bills yielded 10% and excellent when they yielded 3%. A
regression on total returns cannot distinguish those. This is why
`FredProvider.risk_free_series` is load-bearing rather than a nice-to-have, and
why the flat-4% fallback logs a warning.

**F5 is the honest ceiling on this project.** The optimal combined portfolio's
squared Sharpe ratio is the index's plus the square of the active portfolio's
information ratio. Security analysis can only help — *if implemented optimally*.
The size of the help is set by the information ratio, and information ratios
that survive out-of-sample testing are small. `evaluate.py` reports the
information coefficient so the result is stated in the units the book uses.

**F6 is the bridge to a portfolio.** Not needed to forecast one stock, but if
you extend to ranking a universe, the model's per-name predicted alpha feeds
straight into it. Negative-alpha names get negative (short) weights.


---

## Chapter 9 — The Capital Asset Pricing Model

**The chapter that turns a forecast into a claim.** Everything through Chapter 8
described what a security *did*. The SML is the first statement about what a
security *ought* to return, which is what lets `pipeline.py`'s output be scored
rather than merely reported.

| ID | Formula | Function |
|---|---|---|
| F1 | `E(r_i) = r_f + β_i·[E(r_M) − r_f]` ; `β_i = Cov(r_i,r_M)/σ_M²` | `capm.sml_expected_return`, `capm.beta_from_covariance` |
| F2 | `E(r_i) = E(r_Z) + β_i·[E(r_M) − E(r_Z)]` | `capm.zero_beta_expected_return` |
| F3 | `α_i = E(r_i)_actual − [r_f + β_i·(E(r_M) − r_f)]` | `capm.sml_alpha`, `capm.evaluate_against_sml` |
| F4 | `Required = r_f + β·MRP` ; `Fair Profit = Required × Capital` | `capm.required_return`, `capm.fair_profit` |

**Worked examples pinned as tests.** The SML alpha example: market 14%, T-bills
6%, β = 1.2 → fair return 15.6%; an analyst forecast of 17% is an alpha of
+1.4%. Example 9.1 (utility rate-making): β = 0.6, r_f = 6%, MRP = 8% → required
10.8%, fair profit $10.8M on $100M of invested capital.

**F3 is the bridge between the ML half of this project and the finance half.**
`/api/predict` annualises the model's 21-day log forecast, runs it through F3
against the fitted β, and returns the result as its `valuation` block. That
alpha is exactly the input Chapter 8's `treynor_black_weights` has always
wanted and never had — extend this to a universe and the two connect directly.

**What F1 leaves out is the point.** Total volatility does not appear. A
speculative name with 90% annualised volatility and β = 0.4 is entitled to
*less* return than a placid utility at β = 1.1, because diversifiable risk earns
no compensation. `tests/test_finance.py` pins this as an executable assertion,
because it is the claim people most often get backwards, and because it is the
reason `eq_vol_*` must never be read as an expected-return feature.

**The market risk premium is the weak link, and it is handled explicitly.** The
MRP is not observable. Estimating it from one year of index returns gives a
standard error of roughly 18 percentage points against a quantity near 5% —
noise several times the size of the signal, and negative often enough to invert
the SML, which scores every high-beta name backwards.
`capm.realised_market_risk_premium` therefore shrinks the sample mean toward the
textbook 8% with weight `n / (n + 1260)`: about 17% sample weight at one year,
50/50 at five. `capm_*_mrp_is_default` flags rows where even that was
unavailable. Any alpha here is a sketch, and the response carries the MRP
alongside so it can never be quoted without its input.

---

## Chapter 10 — Arbitrage Pricing Theory and Multifactor Models

| ID | Formula | Function |
|---|---|---|
| F1 | `E(R_P) = β_P·E(R_M)` (well-diversified P) | the single-factor case of `multifactor.multifactor_expected_return` |
| F2 | `E(r_P) = r_f + β_P1[E(r_1) − r_f] + β_P2[E(r_2) − r_f]` | `multifactor.multifactor_expected_return` |
| F3 | `R_i = α_i + β_iM·R_M + β_iSMB·SMB + β_iHML·HML + e_i` | `multifactor.fit_multifactor` |
| F4 | `profit = $1 × [E(r_Q) − E(r_A)]`, Q matched on factor betas | `multifactor.replicating_weights`, `multifactor.arbitrage_profit` |

**Examples 10.3 and 10.4, pinned:** two factor portfolios at 10% and 12%,
r_f = 4%, β₁ = 0.5, β₂ = 0.75 → fair return 13%, a 9% risk premium *from two
betas both below 1*. If A is priced at 12%, the replicating portfolio Q is
0.5 / 0.75 / −0.25 in T-bills (a negative T-bill weight: borrowing, not lending)
and the long-Q/short-A trade nets $0.01 riskless per dollar.

**What changed in this project.** `features/tabular.py` already regressed the
stock against four indices — but *separately*, one univariate fit each. Four
single-factor models are not a multifactor model. The S&P 500 and NASDAQ
correlate around 0.9, so `scl_gspc_beta` and `scl_ixic_beta` were largely the
same number twice, and neither was the *marginal* sensitivity to tech given
broad-market exposure. `_multifactor_features` now runs one joint regression
and emits `ff_*`. `tests/test_finance.py` demonstrates the difference directly:
drop a correlated factor and the surviving loading absorbs it, moving from 1.0
to above 1.4.

**The factor proxies are proxies, and the code says so at length.** Real
Fama-French SMB and HML come from Ken French's library, built from CRSP
book-to-market sorts. This project builds `^RUT − ^GSPC` for SMB and
`IWD − IWF` for HML — free, keyless, already flowing through DS2, correlated
with the real factors and *not* them. Small-cap indices differ from large-cap
ones in sector composition as much as in size. Read `ff_beta_smb` as
directional, never as comparable to a published loading.

**Compare `ff_firm_specific_share` against `scl_gspc_firm_specific_share`.** If
the multifactor model explains materially more variance, the single-index model
was mislabelling systematic risk as firm-specific — which means DS3 was being
asked to explain moves that were never company-specific to begin with.

---

## Chapter 11 — The Efficient Market Hypothesis

**Read this chapter as the argument against the project, then keep going.**
Weak-form EMH says everything derivable from past prices and volume is already
priced, which if true makes every `tech_*` and `ret_*` feature worthless.
Semistrong extends that to all public information — every document DS3 will ever
see. Taken at face value, the honest expected R² of this pipeline is zero.

The chapter does not quite say that, and the gap is where the project lives:
markets are efficient enough that active management struggles to beat its costs,
and not so efficient that no analysis is worthwhile. `pipeline.py`'s calibration
note — treat R² 0.01 as a genuine result, treat 0.4 as a bug — is this chapter
restated as an engineering expectation.

| ID | Formula | Function |
|---|---|---|
| F1 | `r_t = α + β·r_Mt + e_t` (market model) | `index_model.fit_scl` on **total** returns |
| F2 | `e_t = r_t − (α + β·r_Mt)` | `event_study.abnormal_return`, `.abnormal_return_series` |
| F3 | size spread = 7.65%/yr, smallest minus largest NYSE decile, 1926–2015 | `event_study.SIZE_EFFECT_SPREAD` |

**Example 11.3, pinned:** α = 0.05%, β = 0.8, market +1%, stock +2% → expected
0.85%, abnormal +1.15%.

**F1 takes total returns; Chapter 8's F2 takes excess returns.** Same
arithmetic, different convention, and the two alphas differ by `(1 − β)·r_f`.
Mixing them shifts every abnormal return by a constant, silently. The parameter
names in `event_study.py` say `actual_return`/`market_return` rather than
reusing `index_model`'s `_excess` naming for exactly this reason.

**LO3's methodological rule is enforced structurally, not by comment.** α and β
must be estimated from a period well separated from the event, or the benchmark
is contaminated by the very abnormal performance being measured.
`event_study.abnormal_return_series` therefore *takes* α and β rather than
fitting them, so a function cannot estimate and measure on the same data.
`_event_features` fits on days −273..−22 and measures on the last 21.

**Why CAR belongs in a feature row.** DS3 says what was *said* about a company.
`evt_gspc_car_21d` says how much the market *moved* on firm-specific news over
the same window, with market direction stripped out. Heavy negative coverage
with no negative CAR means the news was already priced — the semistrong
prediction exactly. Heavy coverage with a large CAR means it was not, which is
the post-earnings-announcement-drift case.

**Momentum is a specification, not a lookback.** `evt_momentum_12_1` is the
twelve-month return *skipping the most recent month*, because one-month
reversal points the opposite way to twelve-month momentum and including it
attenuates both. This is why `eq_ret_252d` is not a momentum feature — it is the
blend. `evt_reversal_24_36m` covers years 2–3 back, sign-flipped so a positive
value means the anomaly predicts a rebound.

**Carry the joint hypothesis problem with every alpha this project prints.**
Every test of efficiency is jointly a test of whatever asset-pricing model
defined "normal". A positive alpha is equally evidence that the CAPM is the
wrong benchmark. This is why `SMLVerdict.verdict` calls anything inside ±1%
"fairly priced" rather than a recommendation.

---

## Chapter 12 — Behavioural Finance and Technical Analysis

| ID | Formula | Function |
|---|---|---|
| F1 | `fair ratio = A/B` ; `premium = (actual − fair)/fair` | `technical.parity_ratio`, `technical.parity_premium` |
| F2 | `MA_t = (P_t + … + P_{t−n+1})/n` | `technical.moving_average`, `.ma_crossover_state`, `.ma_crossover_age` |
| F3 | `Trin = (decl vol/n decl)/(adv vol/n adv)` | `technical.trin` — **implemented, not wired** |

**Royal Dutch/Shell, pinned:** a 60/40 profit split implies a fair price ratio
of exactly 1.5. Royal Dutch traded ~10% above parity in February 1993, widening
to ~17% before reversing after 1999.

**That example is the most important thing in this chapter for this project,
and it is not a formula.** An arbitrageur who correctly identified the 10%
mispricing in 1993 lost money for six years first. Being right about value and
being right about the next thirty days are different claims. Every alpha the
Chapter 9 module produces inherits that caveat.

**Why technical features are defensible here at all.** The chapter supplies a
*mechanism*: the disposition effect — holding losers too long, selling winners
too early — generates real price momentum even when fundamental value follows a
pure random walk, because supply and demand respond to purchase price rather
than to value. Overconfidence links volume to subsequent returns, which is why
technicians watch volume alongside price.

**And the counter-argument, which this project is squarely exposed to.**
Technical signals are loose enough to fit any chart after the fact, and testing
enough patterns against history will always turn up some that look significant
by chance. A `GridSearchCV` over hundreds of feature-model combinations on a
couple of thousand overlapping rows *is* a data-mining machine. This is why
`evaluate.py`'s purged time-series split matters more than any indicator, and
why every function in `technical.py` returns a *feature* rather than a
buy/sell — none of them are signals, and `#ML-6`'s ablation decides which earn
their column.

**`ma_crossover_age` exists because state is not the signal.** A stock eight
months above its 50-day average is not a breakout. `tech_sma_dist_*` gives
distance and `ma_crossover_state` gives sign; neither can tell a fresh cross
from a stale one. It saturates at `max_lookback` rather than returning NaN,
because "no crossing in a year" is a real observation about a persistent trend
and imputing it would replace a genuine extreme with a median.

**Trin is implemented and deliberately unused.** It needs market-wide
advancing/declining issue counts and their volumes, and no provider in
`ingest/` serves them. Leaving a hole where a named textbook formula belongs is
worse than a function whose docstring says it has no inputs yet. If a breadth
provider is ever added, this is what it feeds.

---

## Chapters 1–4

Institutional and definitional — asset classes, market structure, trading
mechanics, mutual funds and ETFs. No formulas implemented, but two things from
them shaped the code:

- **Ch 2, LO4 (indexes).** Why DS4 uses several indices rather than one. The
  S&P 500 is the default SCL benchmark (a broad-market proxy, per Ch 8), but a
  tech name's systematic risk is far better described by the NASDAQ, so both are
  regressed and both sets of `scl_*` features are emitted.
- **Ch 3, LO4 (trading costs).** The reason a directional accuracy of 51% is not
  a strategy. Bid-ask spread and commission are a floor that a forecast has to
  clear before it means anything, which is why `hit_rate_top_decile` — accuracy
  among high-conviction calls — is the metric that matters for acting on output.

---

## Adding to this module

If you implement something new in `stocks/finance/`:

1. Cite the chapter and formula ID in the docstring.
2. Pin the textbook's worked example in `tests/test_finance.py`.
3. Add a row here.

If the source is *not* machine-readable, say so explicitly in the docstring.
The module's value is that it is checkable against a source, and one unverified
formula sitting next to verified ones costs more trust than the formula is worth.

That applies to the full textbook scan in `References/Stocks`: it contains the
equity valuation material (DDM, FCFE, P/E multiples) but as page images with no
text layer. Anything taken from it is transcribed by eye, so mark it as such and
be twice as careful about pinning a worked example.
