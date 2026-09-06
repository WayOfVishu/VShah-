"""Tests for the window spec and the leakage rule it enforces.

These are the tests that matter most in the project. A bug in `finance/` gives
a wrong number that someone will eventually notice. A bug in `windows.py` gives
a model that looks excellent and is worthless, and nobody notices until it is
trading.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from stocks.windows import (
    DEFAULT_HORIZON_DAYS,
    Dataset,
    DateWindow,
    WindowSpec,
    as_of_grid,
    shift_months,
)

AS_OF = date(2025, 6, 15)


class TestShiftMonths:
    def test_simple_shift(self):
        assert shift_months(date(2024, 1, 15), -12) == date(2023, 1, 15)
        assert shift_months(date(2024, 1, 15), 2) == date(2024, 3, 15)

    def test_clamps_to_month_end(self):
        """2024-03-31 minus one month cannot be 2024-02-31."""
        assert shift_months(date(2024, 3, 31), -1) == date(2024, 2, 29)
        assert shift_months(date(2023, 3, 31), -1) == date(2023, 2, 28)

    def test_crosses_year_boundaries(self):
        assert shift_months(date(2024, 2, 10), -3) == date(2023, 11, 10)
        assert shift_months(date(2024, 11, 10), 3) == date(2025, 2, 10)

    def test_zero_shift_is_identity(self):
        assert shift_months(AS_OF, 0) == AS_OF


class TestDateWindow:
    def test_is_half_open_on_the_right(self):
        w = DateWindow(date(2025, 1, 1), date(2025, 2, 1))
        assert w.contains(date(2025, 1, 1))
        assert w.contains(date(2025, 1, 31))
        assert not w.contains(date(2025, 2, 1))

    def test_empty_window_is_rejected(self):
        with pytest.raises(ValueError, match="empty window"):
            DateWindow(date(2025, 1, 1), date(2025, 1, 1))

    def test_days_counts_the_span(self):
        assert DateWindow(date(2025, 1, 1), date(2025, 1, 31)).days == 30


class TestWindowSpec:
    def test_all_five_datasets_have_a_window(self):
        spec = WindowSpec.for_as_of(AS_OF)
        assert set(spec.all_windows()) == set(Dataset)

    def test_lookback_lengths_match_the_design(self):
        spec = WindowSpec.for_as_of(AS_OF)
        assert spec.prices_equity.start == date(2020, 6, 15)   # 5 years
        assert spec.prices_index.start == date(2023, 6, 15)    # 2 years
        assert spec.news_baseline.start == date(2024, 6, 15)   # 12 months back
        assert spec.news_baseline.end == date(2025, 4, 15)     # to 2 months back
        assert spec.news_recent.start == date(2025, 4, 15)     # the recent 2 months
        assert spec.macro.start == date(2024, 12, 15)          # 6 months

    def test_no_window_reaches_the_as_of_date(self):
        """The leakage rule. Every input window is exclusive of as_of."""
        spec = WindowSpec.for_as_of(AS_OF)
        for ds in Dataset:
            assert not spec.window(ds).contains(AS_OF), f"{ds.value} contains as_of"
            assert spec.window(ds).end <= AS_OF

    def test_news_windows_partition_the_year_without_overlap(self):
        """DS2 and DS3 must tile the 12 months exactly -- no gap, no double count."""
        spec = WindowSpec.for_as_of(AS_OF)
        assert spec.news_baseline.end == spec.news_recent.start
        assert spec.news_baseline.start == shift_months(AS_OF, -12)
        assert spec.news_recent.end == AS_OF

        boundary = spec.news_baseline.end
        assert not spec.news_baseline.contains(boundary)
        assert spec.news_recent.contains(boundary)

    def test_label_window_is_strictly_in_the_future(self):
        spec = WindowSpec.for_as_of(AS_OF)
        assert spec.label_window().start == AS_OF
        assert spec.label_window().end > AS_OF

    def test_label_window_does_not_overlap_any_input_window(self):
        """The property the whole design rests on."""
        spec = WindowSpec.for_as_of(AS_OF)
        label = spec.label_window()
        for ds in Dataset:
            assert spec.window(ds).end <= label.start, f"{ds.value} overlaps the label"

    def test_recent_as_of_dates_are_not_labellable(self):
        """The last ~6 weeks have no realised 30-day outcome yet."""
        today = date(2025, 6, 15)
        assert not WindowSpec.for_as_of(today).is_labellable(today)
        assert not WindowSpec.for_as_of(today - timedelta(days=10)).is_labellable(today)
        assert WindowSpec.for_as_of(today - timedelta(days=120)).is_labellable(today)

    def test_overrides_are_respected(self):
        spec = WindowSpec.for_as_of(AS_OF, equity_years=10, news_months=6)
        assert spec.prices_equity.start == date(2015, 6, 15)
        assert spec.news_baseline.start == date(2024, 12, 15)


class TestAsOfGrid:
    def test_steps_at_the_requested_interval(self):
        grid = as_of_grid(date(2022, 1, 1), date(2022, 3, 1),
                          step_days=7, today=date(2026, 1, 1))
        assert len(grid) == 9
        assert all((b - a).days == 7 for a, b in zip(grid, grid[1:]))

    def test_excludes_dates_with_no_realised_label(self):
        """The tail of the range must be dropped, not returned with a null label."""
        today = date(2025, 6, 15)
        grid = as_of_grid(today - timedelta(days=90), today, step_days=7, today=today)
        assert grid
        for as_of in grid:
            assert WindowSpec.for_as_of(as_of).is_labellable(today)
        assert max(grid) < today - timedelta(days=DEFAULT_HORIZON_DAYS)

    def test_returns_empty_when_the_whole_range_is_too_recent(self):
        today = date(2025, 6, 15)
        assert as_of_grid(today - timedelta(days=5), today, today=today) == []

    def test_rejects_a_non_positive_step(self):
        with pytest.raises(ValueError, match="step_days"):
            as_of_grid(date(2022, 1, 1), date(2022, 2, 1), step_days=0)

    def test_larger_steps_give_fewer_rows(self):
        args = dict(start=date(2022, 1, 1), end=date(2023, 1, 1), today=date(2026, 1, 1))
        assert len(as_of_grid(**args, step_days=7)) > len(as_of_grid(**args, step_days=30))


class TestDatasetEnum:
    def test_text_and_tabular_partition_the_five_datasets(self):
        text = {d for d in Dataset if d.is_text}
        tabular = {d for d in Dataset if d.is_tabular}
        assert text | tabular == set(Dataset)
        assert not (text & tabular)
        assert len(text) == 3 and len(tabular) == 2
