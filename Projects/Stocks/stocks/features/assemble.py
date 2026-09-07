"""Assemble the datasets into one training row, and rows into a panel.

    build_row(bundle)          one DatasetBundle -> one feature row
    build_panel(symbols, ...)  a walk-forward sweep -> the training DataFrame
    compute_target(...)        the forward return label

The output frame has three kinds of column, distinguished by prefix, and
`pipeline.py` routes them to different transformers on that basis:

    meta_*   symbol, as_of, provenance. Never features. Dropped before fitting.
    text_*   raw strings, for TfidfVectorizer. **Empty by default now** -- see below.
    <rest>   numeric features -- eq_, idx_, scl_, capm_, ff_, evt_, tech_, gem_.
    target   the label.

**Why `text_*` is empty by default.** The project used to emit three raw
corpora here and let `pipeline.py` TF-IDF each into 24 SVD components. That was
72 unnamed columns against roughly 150 named ones, on a panel of maybe two
thousand rows, and no one could say what any of the 72 measured.

Those corpora now go to `ingest/gemini.py` instead, which reads them and
returns a fixed schema of named scores; `features/synthesis.py` flattens that
into ~15 `gem_*` columns. Pass `include_raw_text=True` to restore the old
blocks -- they are wired and tested, and #ML-6's ablation wants to compare
against them -- but the default is off, because the comparison already ran and
the SVD components lost.

**The lexicon features stayed.** `ds2_*`, `ds3_*`, `ds5_*` and `shift_*` are
still computed by `features/text.py` from the same documents, at essentially no
cost since the documents are already in memory. They are the control group: if
the `gem_*` block does not beat VADER-plus-document-counts out of sample, the
language model is not earning its API bill and should be cut. Keeping the cheap
baseline in the panel is what makes that question answerable rather than
rhetorical.

**Why the whole design turns on this file.** The user's spec produces one
labelled row per ticker, and one row cannot train anything. `build_panel`
resolves that by sweeping `as_of` backwards through history and calling
`build_datasets` at each stop, so a design that sounded like a single
prediction becomes a panel of thousands of rows. Everything upstream was built
to be as-of-parameterised precisely so this function could exist.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..finance import returns as ret
from ..ingest.registry import DatasetBundle, Registry, build_datasets
from ..windows import DEFAULT_HORIZON_DAYS, WindowSpec, as_of_grid
from . import synthesis, tabular, text

log = logging.getLogger(__name__)

__all__ = ["build_row", "build_panel", "compute_target", "META_PREFIX", "TEXT_PREFIX"]

META_PREFIX = "meta_"
TEXT_PREFIX = "text_"


def build_row(
    bundle: DatasetBundle,
    sentiment_backend: str = "vader",
    *,
    include_raw_text: bool = False,
) -> dict[str, object]:
    """One DatasetBundle -> one flat row.

    All three datasets contribute, and the cross-dataset features are the ones
    most likely to carry signal -- they encode relationships a model would
    otherwise have to discover from raw blocks:

        scl_*, capm_*, ff_*, evt_*   DS1 x DS2 (stock against the indices)
        gem_macro_divergence         company tone against the macro backdrop
        shift_*                      the lexicon control's own baseline-vs-recent

    `include_raw_text` restores the pre-Gemini TF-IDF corpora. Off by default;
    see the module docstring.
    """
    spec = bundle.spec
    row: dict[str, object] = {
        f"{META_PREFIX}symbol": bundle.symbol,
        f"{META_PREFIX}as_of": pd.Timestamp(bundle.as_of),
        f"{META_PREFIX}synthetic": ",".join(sorted(bundle.synthetic)),
        f"{META_PREFIX}n_synthetic": len(bundle.synthetic),
        # Which grounding regime produced the brief. Carried as meta rather
        # than as a feature because it must never reach the model, but it has
        # to be recoverable from a saved panel: a panel built with strict
        # grounding and one built without are not comparable, and finding that
        # out after the fact requires the answer to be in the file.
        f"{META_PREFIX}grounding": (
            bundle.sentiment_brief.grounding if bundle.sentiment_brief else "none"
        ),
    }

    # --- DS1: the stock's own price history ------------------------------
    row.update(tabular.price_features(bundle.prices_equity, bundle.risk_free, prefix="eq"))

    # --- DS2: the indices and factor proxies ------------------------------
    row.update(tabular.index_features(bundle.prices_index, bundle.risk_free))

    # --- DS1 x DS2: the Chapter 8-12 regressions --------------------------
    row.update(tabular.relative_features(bundle.prices_equity, bundle.prices_index, bundle.risk_free))

    # --- DS3: the synthesised sentiment brief -----------------------------
    # The headline change. One Gemini call over all three corpora returns ~15
    # named scores; this replaces the 72 anonymous SVD components that used to
    # sit here.
    row.update(synthesis.brief_features(bundle.sentiment_brief))

    # --- DS3's control group: the same corpora, scored by lexicon ---------
    # Free (the documents are already in memory) and the only way to prove the
    # language model beats a bag of words. If it does not, `gem_*` is an
    # expensive way to compute `ds3_sentiment_mean`.
    row.update(text.text_stats_features(
        bundle.news_baseline, "ds2", spec.news_baseline.days, sentiment_backend))
    row.update(text.text_stats_features(
        bundle.news_recent, "ds3", spec.news_recent.days, sentiment_backend))
    row.update(text.text_stats_features(
        bundle.macro_text, "ds5", spec.macro.days, sentiment_backend))
    row.update(text.sentiment_shift_features(
        bundle.news_baseline, bundle.news_recent,
        spec.news_baseline.days, spec.news_recent.days, sentiment_backend))

    # --- raw corpora, for the vectorizer inside the pipeline --------------
    # Off by default. Emitted as empty strings rather than omitted so the panel
    # schema is stable across the flag -- a TfidfVectorizer on empty documents
    # yields no vocabulary and AdaptiveSVD clamps, so the pipeline still runs.
    if include_raw_text:
        row[f"{TEXT_PREFIX}baseline"] = text.corpus_for_vectorizer(bundle.news_baseline)
        row[f"{TEXT_PREFIX}recent"] = text.corpus_for_vectorizer(bundle.news_recent)
        row[f"{TEXT_PREFIX}macro"] = text.corpus_for_vectorizer(bundle.macro_text)

    # --- the numeric macro backdrop --------------------------------------
    if not bundle.macro_panel.empty:
        panel = bundle.macro_panel.ffill()
        for col in panel.columns:
            series = panel[col].dropna()
            if series.empty:
                continue
            row[f"macro_{col}_level"] = float(series.iloc[-1])
            if len(series) > 21:
                # The change matters more than the level for most macro series.
                # An unemployment rate of 4% means little on its own; 4% and
                # rising means something specific.
                row[f"macro_{col}_delta_21d"] = float(series.iloc[-1] - series.iloc[-22])

    return row


def compute_target(
    prices: pd.DataFrame,
    as_of: date,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    kind: str = "log_return",
) -> float:
    """The label: what the stock did over the `horizon_days` after `as_of`.

    `prices` here must extend **past** `as_of` -- it is deliberately not the
    DS1 frame, which stops at `as_of` by the leakage rule. `build_panel`
    fetches a separate forward frame for labelling, and keeping the two frames
    distinct is what makes it structurally hard to leak the label into the
    features.

    Kinds:
        log_return   cumulative log return over the horizon. The default.
        direction    1 if the return is positive, else 0.
        volatility   realised annualised volatility over the horizon.

    On `direction`: it is easier to score well on and much less useful, because
    a 51% accurate direction call with no magnitude is not tradeable after
    costs. Use it to sanity-check that the pipeline runs, then go back to
    `log_return`.
    """
    if prices.empty or "adj_close" not in prices:
        return float("nan")

    px = prices["adj_close"].dropna()
    idx = pd.to_datetime(px.index).date

    at_or_before = [i for i, d in enumerate(idx) if d <= as_of]
    if not at_or_before:
        return float("nan")
    start = at_or_before[-1]
    end = start + horizon_days
    if end >= len(px):
        # The forward window has not fully elapsed. Return NaN and let the
        # caller drop the row -- see WindowSpec.is_labellable.
        return float("nan")

    if kind == "log_return":
        return float(np.log(px.iloc[end] / px.iloc[start]))
    if kind == "direction":
        return float(px.iloc[end] > px.iloc[start])
    if kind == "volatility":
        forward = ret.log_returns(px.iloc[start:end + 1]).dropna()
        return float(forward.std(ddof=1) * np.sqrt(252)) if len(forward) > 1 else float("nan")

    raise ValueError(f"unknown target kind {kind!r}")


def build_panel(
    symbols: list[str],
    start: date,
    end: date,
    *,
    step_days: int = 7,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    target_kind: str = "log_return",
    registry: Registry | None = None,
    sentiment_backend: str = "vader",
    include_raw_text: bool = False,
    progress: bool = True,
) -> pd.DataFrame:
    """The walk-forward sweep: build the training panel.

    For each symbol and each as-of date on the grid, build every dataset as
    they looked on that date, reduce them to a row, and label it with the
    realised forward return.

    Cost is the thing to be aware of before running this. With the cache cold,
    every (symbol, as_of) is ~20 GDELT calls, and GDELT starts returning 429s
    below about one call per five seconds -- so budget roughly 100 seconds per
    cold bundle. A sweep of 10 symbols over 3 years of weekly as-of dates is
    ~1,560 bundles, which is an overnight job, not a coffee break.

    That sweep now also spends one Gemini call per bundle, at roughly 10k input
    tokens each -- on the order of $5 total on flash, and $0 on a re-run since
    the briefs are cached alongside everything else. The rate limiter in
    `ingest/gemini.py` is the binding constraint on the free tier, not the
    money. Run `py run.py build-panel --symbols AAPL --synthetic` first: it
    finishes in seconds, calls nothing, and produces the same schema.

    It is fast on re-runs: overlapping windows hit the Parquet/JSON cache, and
    the macro window is ticker-independent, so only the first symbol at each
    as-of date pays
    for the macro pull.

    Start small. `py run.py build-panel --symbols AAPL --synthetic` finishes in
    seconds and produces the same schema, which is enough to develop the model
    against before spending a night on real data.

    The returned frame is sorted by as-of date. Do not shuffle it -- see
    `evaluate.py` on why the split has to respect time.
    """
    registry = registry or Registry()
    grid = as_of_grid(start, end, step_days=step_days, horizon_days=horizon_days)

    if not grid:
        raise ValueError(
            f"no labellable as-of dates between {start} and {end}. "
            f"The last ~{int(horizon_days * 7 / 5) + 5} days are excluded because their "
            "forward return has not happened yet -- try an earlier end date."
        )

    log.info("building panel: %d symbols x %d as-of dates = %d rows",
             len(symbols), len(grid), len(symbols) * len(grid))

    rows: list[dict] = []
    total = len(symbols) * len(grid)
    done = 0

    for symbol in symbols:
        # One forward-extended price pull per symbol, reused for every as-of
        # date's label. Fetching it per as-of would multiply the provider load
        # by the length of the grid for no benefit.
        label_prices = _fetch_label_prices(registry, symbol, grid[0], grid[-1], horizon_days)

        for as_of in grid:
            done += 1
            if progress and done % 25 == 0:
                log.info("  %d/%d (%.0f%%)", done, total, 100 * done / total)

            try:
                bundle = build_datasets(symbol, as_of, registry=registry,
                                        spec=WindowSpec.for_as_of(as_of))
                row = build_row(bundle, sentiment_backend,
                                include_raw_text=include_raw_text)
                row["target"] = compute_target(label_prices, as_of, horizon_days, target_kind)
                rows.append(row)
            except Exception as exc:
                # One bad as-of must not kill a sweep that has been running for
                # an hour. Log it and continue; the loss is one row.
                log.warning("skipping %s @ %s: %s", symbol, as_of, exc)

    if not rows:
        raise RuntimeError("panel is empty -- every bundle failed. Check `py run.py providers`.")

    panel = pd.DataFrame(rows)

    before = len(panel)
    panel = panel[panel["target"].notna()].copy()
    if len(panel) < before:
        log.info("dropped %d rows with no realised label", before - len(panel))

    panel = panel.sort_values(f"{META_PREFIX}as_of").reset_index(drop=True)

    _warn_on_leakage(panel)
    return panel


def _fetch_label_prices(registry: Registry, symbol: str, first_as_of: date,
                        last_as_of: date, horizon_days: int) -> pd.DataFrame:
    """Prices spanning the whole grid plus the forward horizon, for labelling only.

    Kept strictly separate from the DS1 frames that produce features. DS1 stops
    at its as-of date; this one deliberately runs past it. Conflating the two
    is how the label ends up inside the features.
    """
    from ..windows import DateWindow

    pad = int(horizon_days * 7 / 5) + 10
    window = DateWindow(first_as_of - timedelta(days=10), last_as_of + timedelta(days=pad))
    try:
        return registry.prices.fetch_prices(symbol, window)
    except Exception as exc:
        log.warning("label price fetch failed for %s (%s); using synthetic", symbol, exc)
        return registry._synthetic_prices.fetch_prices(symbol, window)


def _warn_on_leakage(panel: pd.DataFrame) -> None:
    """Cheap sanity checks that catch the mistakes that matter.

    None of these prove the panel is clean. They catch the specific failures
    that are both common and silent -- a feature correlating with the target at
    0.9 is not a discovery, it is a bug, and it is much better to hear about it
    here than after a week of modelling.
    """
    if "target" not in panel or panel["target"].isna().all():
        return

    numeric = panel.select_dtypes(include=[np.number]).drop(columns=["target"], errors="ignore")
    numeric = numeric[[c for c in numeric.columns if not c.startswith(META_PREFIX)]]
    # Zero-variance columns have an undefined correlation and make numpy emit a
    # divide-by-zero warning for every one of them. They are also, by
    # definition, not leaking anything.
    numeric = numeric.loc[:, numeric.std(numeric_only=True) > 0]
    if numeric.empty:
        return

    corr = numeric.corrwith(panel["target"]).abs().sort_values(ascending=False)
    suspicious = corr[corr > 0.8].dropna()
    if not suspicious.empty:
        log.warning(
            "possible leakage: %d feature(s) correlate with the target above 0.8 -- %s. "
            "A 30-day forward return is close to unpredictable; correlations this high "
            "almost always mean a feature saw the future.",
            len(suspicious), ", ".join(suspicious.index[:5]),
        )

    synthetic_rows = int((panel.get(f"{META_PREFIX}n_synthetic", pd.Series(0)) > 0).sum())
    if synthetic_rows:
        log.warning(
            "%d of %d rows contain synthetic data. Scores from this panel measure the "
            "pipeline's plumbing, not its predictive power.", synthetic_rows, len(panel),
        )
