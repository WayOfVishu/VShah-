# Formula Reference

Every formula implemented in `stocks/finance/`, mapped to its source in Bodie,
Kane & Marcus, *Investments*, 9th Canadian Edition — the chapter summaries in
`References/Stocks/`.

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
