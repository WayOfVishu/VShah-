/* Stocks — research sandbox frontend.
   Vanilla JS, no build step, same shape as the Jobs dashboard's public/app.js:
   an `els` map, plain fetch(), and render functions off one state object.

   The flow is deliberately two-step rather than one:

     1. /api/resolve      cheap, fast, and may be ambiguous -> show a picker
     2. /api/predict      slow (builds all five datasets) -> one call, once

   Resolving separately means a wrong ticker is caught before a two-minute
   dataset build, not after it. */

const els = {
  form: document.getElementById("searchForm"),
  input: document.getElementById("searchInput"),
  risk: document.getElementById("riskAversion"),
  btn: document.getElementById("searchBtn"),

  candidates: document.getElementById("candidates"),
  candidateList: document.getElementById("candidateList"),

  progressPanel: document.getElementById("progressPanel"),
  progressList: document.getElementById("progressList"),

  resultPanel: document.getElementById("resultPanel"),
  resultSymbol: document.getElementById("resultSymbol"),
  resultAsOf: document.getElementById("resultAsOf"),
  verdictNum: document.getElementById("verdictNum"),
  modelBanner: document.getElementById("modelBanner"),

  statRange: document.getElementById("statRange"),
  statRangeNote: document.getElementById("statRangeNote"),
  statVol: document.getElementById("statVol"),
  statBeta: document.getElementById("statBeta"),
  statR2: document.getElementById("statR2"),
  statR2Note: document.getElementById("statR2Note"),
  statSentiment: document.getElementById("statSentiment"),
  statAttention: document.getElementById("statAttention"),

  valFair: document.getElementById("valFair"),
  valForecast: document.getElementById("valForecast"),
  valAlpha: document.getElementById("valAlpha"),
  valVerdict: document.getElementById("valVerdict"),
  valNote: document.getElementById("valNote"),
  valCaveat: document.getElementById("valCaveat"),

  brief: document.getElementById("brief"),
  briefSource: document.getElementById("briefSource"),
  briefRationale: document.getElementById("briefRationale"),
  briefThemes: document.getElementById("briefThemes"),
  briefConfidence: document.getElementById("briefConfidence"),
  statSentimentNote: document.getElementById("statSentimentNote"),

  allocFill: document.getElementById("allocFill"),
  allocNote: document.getElementById("allocNote"),

  datasetPanel: document.getElementById("datasetPanel"),
  datasetGrid: document.getElementById("datasetGrid"),

  errorPanel: document.getElementById("errorPanel"),
  errorMessage: document.getElementById("errorMessage"),

  providerPrices: document.getElementById("providerPrices"),
  providerNews: document.getElementById("providerNews"),
  providerMacro: document.getElementById("providerMacro"),

  disclaimerMore: document.getElementById("disclaimerMore"),
  disclaimerFull: document.getElementById("disclaimerFull"),
  disclaimerClose: document.getElementById("disclaimerClose"),
  toastStack: document.getElementById("toastStack"),
};

let busy = false;

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

const pct = (x, digits = 2) =>
  x === null || x === undefined || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(digits)}%`;

const signedPct = (x, digits = 2) =>
  x === null || x === undefined || Number.isNaN(x)
    ? "–"
    : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(digits)}%`;

const num = (x, digits = 2) =>
  x === null || x === undefined || Number.isNaN(x) ? "–" : Number(x).toFixed(digits);

function showToast(message, { type = "info", duration = 4200 } = {}) {
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  el.title = "Dismiss";
  els.toastStack.appendChild(el);
  requestAnimationFrame(() => el.classList.add("is-visible"));

  const remove = () => {
    clearTimeout(timer);
    el.classList.remove("is-visible");
    el.addEventListener("transitionend", () => el.remove(), { once: true });
  };
  const timer = setTimeout(remove, duration);
  el.addEventListener("click", remove);
}

async function getJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    // FastAPI puts the useful message in `detail`; fall back to the status.
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body — keep the status line */ }
    throw new Error(detail);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Provider badges — which sources answered, and whether any are generated
// ---------------------------------------------------------------------------

async function loadHealth() {
  try {
    const health = await getJSON("/api/health");
    const synthetic = new Set(health.syntheticSlots || []);

    const set = (el, slot, label) => {
      el.textContent = label;
      el.classList.toggle("is-synthetic", synthetic.has(slot));
    };
    set(els.providerPrices, "prices", health.providers.prices);
    set(els.providerNews, "news", health.providers.news);
    set(els.providerMacro, "macro_numeric", health.providers.macro_numeric);

    if (health.fullySynthetic) {
      showToast(
        "Every data source fell back to generated data. Results are meaningless — check your network.",
        { type: "error", duration: 9000 }
      );
    }
  } catch {
    els.providerPrices.textContent = "offline";
  }
}

// ---------------------------------------------------------------------------
// Step 1 — resolve
// ---------------------------------------------------------------------------

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;

  const q = els.input.value.trim();
  if (!q) return;

  hide(els.errorPanel, els.candidates, els.resultPanel, els.datasetPanel);

  try {
    const resolved = await getJSON(`/api/resolve?q=${encodeURIComponent(q)}`);
    if (resolved.unambiguous) {
      await analyse(resolved.candidates[0].symbol);
    } else {
      renderCandidates(resolved.candidates);
    }
  } catch (err) {
    showError(`Could not resolve "${q}". ${err.message}`);
  }
});

function renderCandidates(candidates) {
  els.candidateList.innerHTML = "";
  for (const c of candidates) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "candidate";
    // textContent on the pieces rather than innerHTML on a template string:
    // company names come from a third-party search and are untrusted.
    const sym = document.createElement("span");
    sym.className = "sym";
    sym.textContent = c.symbol;
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = c.exchange ? `${c.name} · ${c.exchange}` : c.name;
    btn.append(sym, nm);
    btn.addEventListener("click", () => {
      hide(els.candidates);
      analyse(c.symbol);
    });
    els.candidateList.appendChild(btn);
  }
  show(els.candidates);
}

// ---------------------------------------------------------------------------
// Step 2 — predict
// ---------------------------------------------------------------------------

const STEPS = [
  "Resolving ticker",
  "DS1 · 5 years of prices",
  "DS4 · index history",
  "DS2/DS3 · news, 12 months",
  "DS5 · macro backdrop",
  "Building features and forecasting",
];

function startProgress() {
  els.progressList.innerHTML = "";
  STEPS.forEach((label, i) => {
    const li = document.createElement("li");
    li.textContent = label;
    if (i === 0) li.className = "is-done";
    els.progressList.appendChild(li);
  });
  show(els.progressPanel);

  // The backend builds everything in one blocking call and reports no
  // intermediate state, so this is a paced estimate, not real progress. It is
  // honest about roughly how long each stage takes and never claims to have
  // finished the last one — that only happens when the response lands.
  let i = 1;
  return setInterval(() => {
    if (i >= STEPS.length - 1) return;
    els.progressList.children[i].className = "is-done";
    i += 1;
    els.progressList.children[i].className = "is-active";
  }, 4000);
}

async function analyse(symbol) {
  busy = true;
  els.btn.disabled = true;
  hide(els.errorPanel, els.resultPanel, els.datasetPanel);
  const ticker = startProgress();

  try {
    const [prediction, datasets] = await Promise.all([
      getJSON("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          risk_aversion: Number(els.risk.value),
        }),
      }),
      // Fetched alongside rather than after: both build the same bundle, and
      // the second one hits the disk cache the first one just populated.
      getJSON(`/api/datasets/${encodeURIComponent(symbol)}`).catch(() => null),
    ]);

    renderPrediction(prediction);
    if (datasets) renderDatasets(datasets);
  } catch (err) {
    showError(err.message);
  } finally {
    clearInterval(ticker);
    hide(els.progressPanel);
    busy = false;
    els.btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderPrediction(p) {
  els.resultSymbol.textContent = p.symbol;
  els.resultAsOf.textContent = `AS OF ${p.as_of} · ${p.horizon_days} TRADING DAYS`;

  const change = Math.expm1(p.expected_return);
  els.verdictNum.textContent = signedPct(change);
  els.verdictNum.className = `verdict-num is-${p.direction}`;

  // One banner, and the synthetic warning outranks the untrained-model one:
  // a forecast from fabricated inputs is a worse problem than a forecast from
  // a placeholder model, and stacking both just gets skimmed.
  const warning = p.warning;
  if (warning) {
    els.modelBanner.textContent = warning;
    els.modelBanner.classList.toggle("is-synthetic", (p.synthetic || []).length > 0);
    show(els.modelBanner);
  } else {
    hide(els.modelBanner);
  }

  const lo = Math.expm1(p.interval.low);
  const hi = Math.expm1(p.interval.high);
  els.statRange.textContent = `${signedPct(lo, 1)} … ${signedPct(hi, 1)}`;
  els.statRangeNote.textContent =
    p.interval.method === "historical_volatility"
      ? "from historical volatility — not a model confidence interval"
      : "model quantiles";

  const ctx = p.context || {};
  els.statVol.textContent = pct(ctx.annualized_volatility, 1);
  els.statBeta.textContent = num(ctx.beta_sp500);

  els.statR2.textContent = pct(ctx.r_squared_sp500, 1);
  // R² is the most interpretable number on the page once translated: it says
  // how much of this stock is really just the market.
  if (ctx.r_squared_sp500 != null) {
    const firmShare = pct(1 - ctx.r_squared_sp500, 0);
    els.statR2Note.textContent = `${firmShare} of its moves are company-specific`;
  } else {
    els.statR2Note.textContent = "";
  }

  // Prefer the model's read of the shift; fall back to the lexicon's when DS3
  // could not produce one, and say which is on screen. Showing two different
  // numbers under one label across runs would be worse than showing neither.
  const briefShift = ctx.sentiment_brief_shift;
  const shift = briefShift != null ? briefShift : ctx.sentiment_shift;
  els.statSentiment.textContent =
    shift == null ? "–" : `${shift >= 0 ? "+" : ""}${num(shift)}`;
  if (els.statSentimentNote) {
    els.statSentimentNote.textContent =
      briefShift != null ? "recent vs prior, as the model read it" : "recent 2mo vs prior 10mo (lexicon)";
  }
  els.statAttention.textContent =
    ctx.attention_ratio == null ? "–" : `${num(ctx.attention_ratio)}×`;

  renderValuation(p.valuation);
  renderBrief(ctx);
  renderAllocation(p.allocation);
  show(els.resultPanel);
}

// Verdict -> the class that colours it. Kept as a map rather than an if-chain
// so an unrecognised verdict from a future API version renders neutrally
// instead of silently picking whichever branch happened to be last.
const VERDICT_CLASS = {
  underpriced: "verdict-good",
  overpriced: "verdict-bad",
  fairly_priced: "verdict-neutral",
  unknown: "verdict-neutral",
};

function renderValuation(v) {
  if (!v) return;

  els.valFair.textContent = pct(v.fair_return);
  els.valForecast.textContent = pct(v.forecast_return_annual);
  els.valAlpha.textContent = signedPct(v.alpha);

  // Colour the alpha by sign, but only once it clears the band the API itself
  // treats as noise. Painting a +0.3% alpha green would be the page telling a
  // stronger story than the number supports.
  els.valAlpha.classList.remove("is-positive", "is-negative");
  if (v.verdict === "underpriced") els.valAlpha.classList.add("is-positive");
  if (v.verdict === "overpriced") els.valAlpha.classList.add("is-negative");

  const label = (v.verdict || "unknown").replace(/_/g, " ");
  els.valVerdict.textContent = label;
  els.valVerdict.className = `verdict ${VERDICT_CLASS[v.verdict] || "verdict-neutral"}`;
  els.valNote.textContent = v.note || "";

  // When the premium could not be estimated from index history, the alpha is
  // built on a textbook constant rather than this market. That is a materially
  // weaker claim and the page has to say so where the number is, not in a
  // footnote nobody reads.
  const defaulted = v.market_risk_premium_is_default;
  els.valCaveat.classList.toggle("is-warning", !!defaulted);
  if (defaulted) {
    els.valCaveat.textContent =
      "The market risk premium could not be estimated from index history, so " +
      "the textbook 8% was used. This alpha is a sketch, not a valuation — it " +
      "says as much about that assumption as about the stock.";
  }
}

function renderBrief(ctx) {
  const rationale = ctx.sentiment_rationale;
  if (!rationale) {
    hide(els.brief);
    return;
  }

  els.briefRationale.textContent = rationale;

  // "synthetic" grounding means no language model ran — the scores came from a
  // word list. Labelling it here is the difference between a reader trusting
  // the brief and knowing not to.
  const grounding = ctx.sentiment_grounding;
  const isSynthetic = grounding === "synthetic";
  els.briefSource.textContent = isSynthetic ? "word list, not a model" : `grounding: ${grounding}`;
  els.briefSource.classList.toggle("tag-warn", isSynthetic);

  els.briefThemes.innerHTML = "";
  for (const theme of ctx.sentiment_themes || []) {
    const chip = document.createElement("span");
    chip.className = "theme";
    chip.textContent = theme;
    els.briefThemes.appendChild(chip);
  }

  const c = ctx.sentiment_confidence;
  els.briefConfidence.textContent =
    c == null
      ? ""
      : isSynthetic
        ? "Confidence is pinned at zero: a lexicon has no view about its own reliability."
        : `Model's own confidence in these scores: ${pct(c, 0)}.`;

  show(els.brief);
}

function renderAllocation(a) {
  if (!a) return;
  const clamped = Math.max(0, Math.min(1, a.y_star_clamped));
  els.allocFill.style.width = `${clamped * 100}%`;
  els.allocFill.classList.toggle("is-short", a.is_short);
  els.allocFill.classList.toggle("is-levered", a.is_levered);
  els.allocNote.textContent = a.note;
}

// The retrieval windows, which is what /api/datasets reports. Three of these
// are now inputs to DS3's synthesis rather than datasets the model sees, so
// they are labelled by what they fetch rather than by a dataset number.
const DATASET_LABELS = {
  prices_equity: "DS1 · Stock prices",
  prices_index: "DS2 · Indices + factors",
  news_baseline: "Retrieval · News baseline",
  news_recent: "Retrieval · Recent news",
  macro: "Retrieval · Macro backdrop",
};

function renderDatasets(d) {
  els.datasetGrid.innerHTML = "";
  const synthetic = new Set(d.synthetic || []);

  const cards = [
    ["prices_equity", `${d.prices_equity.n_bars} bars`, d.prices_equity.window, d.sources.prices_equity],
    [
      "prices_index",
      `${Object.keys(d.prices_index).length} indices`,
      Object.values(d.prices_index)[0]?.window,
      d.sources.prices_index,
    ],
    ["news_baseline", `${d.news_baseline.n_documents} docs`, d.news_baseline.window, d.sources.news_baseline],
    ["news_recent", `${d.news_recent.n_documents} docs`, d.news_recent.window, d.sources.news_recent],
    ["macro", `${d.macro.n_documents} docs`, d.macro.window, d.sources.macro],
  ];

  for (const [key, count, window, source] of cards) {
    const card = document.createElement("div");
    card.className = "dataset-card";
    if (synthetic.has(key)) card.classList.add("is-synthetic");

    const h4 = document.createElement("h4");
    h4.textContent = DATASET_LABELS[key];

    const win = document.createElement("span");
    win.className = "ds-window";
    win.textContent = window ? `${window.start} → ${window.end}` : "";

    const cnt = document.createElement("span");
    cnt.className = "ds-count";
    cnt.textContent = count;

    const src = document.createElement("span");
    src.className = "ds-source";
    src.textContent = `via ${source || "unknown"}`;

    card.append(h4, win, cnt, src);

    if (synthetic.has(key)) {
      const flag = document.createElement("span");
      flag.className = "ds-flag";
      flag.textContent = "generated data";
      card.appendChild(flag);
    }
    els.datasetGrid.appendChild(card);
  }

  show(els.datasetPanel);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function show(...nodes) { nodes.forEach((n) => (n.hidden = false)); }
function hide(...nodes) { nodes.forEach((n) => (n.hidden = true)); }

function showError(message) {
  els.errorMessage.textContent = message;
  show(els.errorPanel);
  showToast(message, { type: "error" });
}

els.disclaimerMore.addEventListener("click", () => {
  const open = els.disclaimerFull.hidden;
  els.disclaimerFull.hidden = !open;
  els.disclaimerMore.setAttribute("aria-expanded", String(open));
  if (open) els.disclaimerFull.scrollIntoView({ behavior: "smooth", block: "nearest" });
});

els.disclaimerClose.addEventListener("click", () => {
  els.disclaimerFull.hidden = true;
  els.disclaimerMore.setAttribute("aria-expanded", "false");
});

loadHealth();
