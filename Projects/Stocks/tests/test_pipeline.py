"""End-to-end tests on synthetic data, plus the anti-leakage guards.

Runs entirely offline via the synthetic providers, so `pytest` needs no network
and no keys. These are the tests that would catch a regression in the wiring
between ingest, features, and the pipeline.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from stocks.evaluate import (
    PurgedTimeSeriesSplit,
    directional_accuracy,
    information_coefficient,
    purge_gap_rows,
    regression_report,
)
from stocks.features.assemble import META_PREFIX, TEXT_PREFIX, build_panel, build_row
from stocks.ingest.registry import Registry, build_datasets
from stocks.windows import Dataset
from stocks.pipeline import build_pipeline, split_columns

TODAY = date(2025, 6, 1)
END = TODAY - timedelta(days=60)
START = END - timedelta(days=400)


@pytest.fixture(scope="module")
def registry() -> Registry:
    return Registry(force_synthetic=True)


@pytest.fixture(scope="module")
def panel(registry) -> pd.DataFrame:
    return build_panel(["TEST1", "TEST2"], START, END,
                       step_days=21, registry=registry, progress=False)


class TestBundle:
    def test_all_five_datasets_are_populated(self, registry):
        bundle = build_datasets("TEST", END, registry=registry)
        assert not bundle.prices_equity.empty
        assert bundle.prices_index
        assert bundle.news_baseline and bundle.news_recent and bundle.macro_text
        assert not bundle.macro_panel.empty

    def test_synthetic_provenance_is_recorded(self, registry):
        """A run on fake data must be self-identifying."""
        bundle = build_datasets("TEST", END, registry=registry)
        assert bundle.has_synthetic

    def test_no_price_bar_reaches_the_as_of_date(self, registry):
        """The leakage rule, enforced at the ingest boundary."""
        bundle = build_datasets("TEST", END, registry=registry)
        assert max(pd.to_datetime(bundle.prices_equity.index).date) < END

    def test_no_document_reaches_the_as_of_date(self, registry):
        bundle = build_datasets("TEST", END, registry=registry)
        for docs in (bundle.news_baseline, bundle.news_recent, bundle.macro_text):
            assert all(d.published < END for d in docs)

    def test_baseline_and_recent_documents_do_not_overlap(self, registry):
        bundle = build_datasets("TEST", END, registry=registry)
        boundary = bundle.spec.news_recent.start
        assert all(d.published < boundary for d in bundle.news_baseline)
        assert all(d.published >= boundary for d in bundle.news_recent)


class TestBuildRow:
    def test_produces_features_from_every_dataset(self, registry):
        row = build_row(build_datasets("TEST", END, registry=registry))
        for prefix in ("eq_", "idx_", "scl_", "ds2_", "ds3_", "ds5_", "shift_", "macro_"):
            assert any(k.startswith(prefix) for k in row), f"no {prefix}* features"

    def test_emits_the_three_raw_corpora(self, registry):
        row = build_row(build_datasets("TEST", END, registry=registry))
        for name in ("baseline", "recent", "macro"):
            assert isinstance(row[f"{TEXT_PREFIX}{name}"], str)

    def test_chapter_8_regression_features_are_present_and_sane(self, registry):
        row = build_row(build_datasets("TEST", END, registry=registry))
        assert 0.0 <= row["scl_gspc_r_squared"] <= 1.0
        # The two variance shares must partition total risk.
        assert row["scl_gspc_r_squared"] + row["scl_gspc_firm_specific_share"] == pytest.approx(1.0)

    def test_vix_is_not_regressed_on(self, registry):
        """A volatility index is not an investable asset; its beta is meaningless."""
        row = build_row(build_datasets("TEST", END, registry=registry))
        assert not any(k.startswith("scl_vix") for k in row)


class TestPanel:
    def test_has_rows_and_a_complete_target(self, panel):
        assert len(panel) > 10
        assert panel["target"].notna().all()

    def test_is_sorted_by_as_of(self, panel):
        """Every guarantee in evaluate.py depends on this."""
        assert panel[f"{META_PREFIX}as_of"].is_monotonic_increasing

    def test_every_row_has_the_same_columns(self, panel):
        """A ragged panel would make the imputer treat structural absence as
        random missingness."""
        assert not panel.columns.duplicated().any()
        # Feature columns must be dense enough to be usable; a column that is
        # entirely NaN is a bug in the feature code, not missing data.
        features, _ = split_columns(panel)
        all_nan = [c for c in features if panel[c].isna().all()]
        assert not all_nan, f"columns are entirely NaN: {all_nan[:5]}"

    def test_target_is_a_plausible_monthly_return(self, panel):
        """A 21-day log return should sit well inside +/-100%. Anything wilder
        means the target is being computed over the wrong span."""
        assert panel["target"].abs().max() < 1.0

    def test_no_feature_is_near_perfectly_correlated_with_the_target(self, panel):
        """The leakage canary. On synthetic data the price and text series are
        independent by construction, so any strong correlation is a wiring bug."""
        features, _ = split_columns(panel)
        # Zero-variance columns have an undefined correlation; excluding them
        # keeps numpy from warning once per column and does not weaken the
        # check -- a constant column cannot be leaking anything.
        usable = panel[features].loc[:, panel[features].std() > 0]
        corr = usable.corrwith(panel["target"]).abs()
        worst = corr.dropna().max()
        assert worst < 0.8, f"suspicious correlation {worst:.3f} for {corr.idxmax()}"


class TestPipeline:
    def test_split_columns_excludes_meta_and_target(self, panel):
        numeric, text = split_columns(panel)
        assert not any(c.startswith(META_PREFIX) for c in numeric + text)
        assert "target" not in numeric
        assert all(c.startswith(TEXT_PREFIX) for c in text)
        assert len(text) == 3

    def test_fits_and_predicts(self, panel):
        pipe = build_pipeline(panel)
        X = panel.drop(columns=["target"])
        y = panel["target"]
        pipe.fit(X, y)
        pred = pipe.predict(X)
        assert len(pred) == len(panel)
        assert np.isfinite(pred).all()

    def test_meta_columns_never_reach_the_model(self, panel):
        """`remainder="drop"` must actually drop them -- a model that can see
        meta_symbol learns per-ticker biases that will not generalise."""
        pipe = build_pipeline(panel)
        pipe.fit(panel.drop(columns=["target"]), panel["target"])
        names = pipe.named_steps["preprocessor"].get_feature_names_out()
        assert not any(META_PREFIX in n for n in names)

    def test_predicts_on_a_single_unseen_row(self, panel, registry):
        """The shape the /api/predict endpoint uses."""
        pipe = build_pipeline(panel)
        pipe.fit(panel.drop(columns=["target"]), panel["target"])

        row = build_row(build_datasets("UNSEEN", END, registry=registry))
        pred = pipe.predict(pd.DataFrame([row]))
        assert len(pred) == 1 and np.isfinite(pred[0])


class TestEvaluation:
    def test_purge_gap_covers_the_label_horizon(self):
        assert purge_gap_rows(step_days=7, horizon_days=21) == 5
        # A 30-day step still overlaps: the label spans ~34 calendar days.
        assert purge_gap_rows(step_days=30, horizon_days=21) == 2
        # A tighter sweep needs proportionally more rows purged.
        assert purge_gap_rows(step_days=1, horizon_days=21) == 34

    def test_splits_are_chronological_and_gapped(self):
        cv = PurgedTimeSeriesSplit(n_splits=4, gap=3)
        X = np.arange(200).reshape(-1, 1)
        for train, valid in cv.split(X):
            assert train.max() < valid.min(), "validation must follow training"
            assert valid.min() - train.max() > 3, "purge gap not applied"

    def test_training_window_expands(self):
        cv = PurgedTimeSeriesSplit(n_splits=4, gap=2)
        sizes = [len(train) for train, _ in cv.split(np.arange(200).reshape(-1, 1))]
        assert sizes == sorted(sizes)

    def test_rejects_a_panel_too_small_to_absorb_the_gap(self):
        cv = PurgedTimeSeriesSplit(n_splits=5, gap=10)
        with pytest.raises(ValueError, match="too small"):
            list(cv.split(np.arange(30).reshape(-1, 1)))

    def test_directional_accuracy_ignores_zero_returns(self):
        y_true = np.array([0.1, -0.1, 0.0, 0.2])
        y_pred = np.array([0.05, -0.05, 0.5, -0.3])
        # Zero truth excluded: 2 of 3 correct.
        assert directional_accuracy(y_true, y_pred) == pytest.approx(2 / 3)

    def test_information_coefficient_is_rank_based(self):
        y_true = np.array([1.0, 2.0, 3.0, 4.0])
        # A monotone but non-linear transform must still give IC 1.0.
        assert information_coefficient(y_true, y_true**3) == pytest.approx(1.0)

    def test_report_returns_every_metric(self):
        rng = np.random.default_rng(0)
        report = regression_report(rng.standard_normal(200), rng.standard_normal(200))
        for key in ("r2", "rmse", "mae", "directional_accuracy",
                    "information_coefficient", "hit_rate_top_decile", "n"):
            assert key in report

    def test_random_predictions_score_near_chance(self):
        """The sanity floor: noise must not look like signal."""
        rng = np.random.default_rng(1)
        report = regression_report(rng.standard_normal(2000), rng.standard_normal(2000))
        assert report["r2"] < 0.05
        assert abs(report["directional_accuracy"] - 0.5) < 0.05
        assert abs(report["information_coefficient"]) < 0.1


class TestProviderConfiguration:
    """Guards on the settings that control how long a walk-forward sweep takes.

    DS5 built naively -- six separate queries over fortnightly chunks -- costs
    78 rate-limited calls per bundle, which makes a real sweep infeasible.
    These pin the cheaper arrangement so it cannot regress silently.
    """

    def test_macro_queries_go_out_as_one_or_query(self):
        from stocks.ingest.macro import MACRO_QUERIES, MacroTextProvider

        q = MacroTextProvider.combined_query()
        assert q.startswith("(") and q.endswith(")")
        assert q.count(" OR ") == len(MACRO_QUERIES) - 1
        for topic in MACRO_QUERIES:
            assert f'"{topic}"' in q

    def test_a_bare_ticker_is_quoted_but_a_boolean_expression_is_not(self):
        """Double-quoting an OR expression yields `"(... OR ...)"`, which GDELT
        reads as a literal phrase and matches nothing -- with a 200 status and
        an empty article list, so the failure is completely silent."""
        from stocks.ingest.macro import MacroTextProvider
        from stocks.ingest.news import _gdelt_query

        assert _gdelt_query("AAPL") == '"AAPL"'

        combined = MacroTextProvider.combined_query()
        assert _gdelt_query(combined) == combined
        assert not _gdelt_query(combined).startswith('"(')

    def test_rate_limit_is_conservative_enough_to_survive_a_sweep(self):
        """1.2s produced sustained 429s against the live API. Pinned so a
        well-meaning speed-up cannot silently reintroduce empty text datasets."""
        from stocks.ingest.news import MIN_INTERVAL, GdeltProvider

        assert MIN_INTERVAL >= 5.0
        assert GdeltProvider()._limiter.min_interval >= 5.0

    def test_macro_chunks_are_coarser_than_news_chunks(self):
        """DS5 is a slow-moving backdrop; DS2/DS3 need finer resolution because
        the whole point of the split is comparing them."""
        from stocks.ingest.macro import MacroTextProvider
        from stocks.ingest.news import GdeltProvider

        assert MacroTextProvider.CHUNK_DAYS > GdeltProvider.CHUNK_DAYS

    def test_gdelt_chunk_size_is_configurable(self):
        from stocks.ingest.news import GdeltProvider

        assert GdeltProvider(chunk_days=30).chunk_days == 30
        assert GdeltProvider().chunk_days == GdeltProvider.CHUNK_DAYS

    def test_a_bundle_stays_within_a_sane_call_budget(self):
        """A six-month DS5 plus a year of news must not exceed ~30 GDELT calls.

        At ~1.2s per call that is well under a minute per bundle, which is what
        keeps `build_panel` tractable. If someone reduces the chunk sizes, this
        fails before a sweep silently takes ten times as long.
        """
        from stocks.ingest.macro import MacroTextProvider
        from stocks.ingest.news import GdeltProvider
        from stocks.windows import WindowSpec

        spec = WindowSpec.for_as_of(date(2025, 6, 15))
        news_calls = sum(
            -(-spec.window(ds).days // GdeltProvider.CHUNK_DAYS)
            for ds in (Dataset.NEWS_BASELINE, Dataset.NEWS_RECENT)
        )
        macro_calls = -(-spec.macro.days // MacroTextProvider.CHUNK_DAYS)
        assert news_calls + macro_calls <= 30


class TestResolve:
    def test_exact_ticker_wins(self):
        from stocks.resolve import resolve_one

        assert resolve_one("AAPL").symbol == "AAPL"

    def test_alias_resolves_offline(self):
        from stocks.resolve import resolve

        assert resolve("apple")[0].symbol == "AAPL"
        assert resolve("sp500")[0].symbol == "^GSPC"

    def test_ticker_detection_is_case_sensitive(self):
        from stocks.resolve import looks_like_ticker

        assert looks_like_ticker("AAPL")
        assert looks_like_ticker("BRK.B")
        assert looks_like_ticker("^GSPC")
        assert not looks_like_ticker("apple")

    def test_empty_query_returns_nothing(self):
        from stocks.resolve import resolve

        assert resolve("   ") == ()
