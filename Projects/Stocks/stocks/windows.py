"""The five-dataset window specification -- the single source of truth.

Every dataset in this project is defined as a date range measured backwards
from an **as-of date**, never from "today". That one decision is what makes the
project trainable, so it is worth being explicit about why.

The obvious reading of the design ("pull the last 5 years of prices and the
last year of news, then predict the next 30 days") produces exactly **one**
labelled example per ticker. You cannot fit a model to one row. What you
actually want is to slide the whole five-window arrangement backwards through
history: pick an as-of date in 2021, build all five datasets *as they would
have looked on that date*, and label the row with what the stock actually did
over the following 30 days. Repeat weekly for a few years and across a few
hundred tickers and you have a panel with enough rows to learn from.

So `as_of` is the pivot:

    training   as_of sweeps a grid of historical dates (see `as_of_grid`)
    inference  as_of = today, and the label is what you are predicting

The windows, all relative to `as_of`:

    |------------------------------ DS1 . prices, equity, 5y ----------------|
    |                                                                       |
    |             |----------------- DS4 . prices, index, 2y ---------------|
    |             |                                                         |
    |                             |----- DS5 . macro text, 6m --------------|
    |                             |                                         |
    |                    |-- DS2 . news baseline, 12m->2m --||- DS3 . 2m ---|
    |                    |                                  |               |
    -------------------------------------------------------------------------> t
    -5y           -2y   -12m                               -2m           as_of

DS2 and DS3 partition the one-year news pull at the two-month mark. They are
kept apart rather than pooled because they answer different questions: DS2 is
the slow-moving narrative a stock has been carrying for most of a year, DS3 is
what changed recently. Featurised separately, the model can learn from the
*difference* between them -- a sentiment or topic shift against a stable
baseline -- which is unavailable if you average the whole year into one vector.

**The leakage rule.** Nothing in any window may be dated at or after `as_of`.
`DateWindow` is closed half-open on the right (`start <= t < end`) for exactly
this reason, and `stocks.features.assemble` refuses a frame that violates it.
This is the failure mode that makes stock models look brilliant in backtests
and lose money live, so it is enforced in code rather than left to discipline.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

__all__ = [
    "Dataset",
    "DateWindow",
    "WindowSpec",
    "shift_months",
    "as_of_grid",
    "TRADING_DAYS_PER_MONTH",
    "DEFAULT_HORIZON_DAYS",
]

# NYSE/TSX average about 21 trading days a month. The user-facing promise is a
# "30-day forecast", which in market terms means 21 bars ahead, not 30.
TRADING_DAYS_PER_MONTH = 21
DEFAULT_HORIZON_DAYS = 21


class Dataset(str, Enum):
    """The five *retrieval* windows, named once so nothing uses a raw string.

    These are fetch windows, not the datasets the model sees. Three of them --
    the two news windows and the macro window -- are now inputs to the Gemini
    synthesis step rather than model inputs in their own right, so what reaches
    `pipeline.py` is three datasets, not five:

        DS1  the stock's own price history      <- PRICES_EQUITY
        DS2  the indices and factor proxies     <- PRICES_INDEX
        DS3  the synthesised sentiment brief    <- NEWS_BASELINE + NEWS_RECENT + MACRO

    The enum keeps all five because every one is still a distinct window that
    has to be requested, cached, and clipped separately -- collapsing them here
    would lose the point-in-time boundaries that make the panel honest. See
    `ingest/registry.py` for the retrieval-versus-synthesis split.
    """

    PRICES_EQUITY = "prices_equity"      # tabular . 5 years of the target stock
    NEWS_BASELINE = "news_baseline"      # text    . 12 months ago -> 2 months ago
    NEWS_RECENT = "news_recent"          # text    . the most recent 2 months
    PRICES_INDEX = "prices_index"        # tabular . 2 years of indices + factor ETFs
    MACRO = "macro"                      # text    . 6 months of political/economic

    @property
    def is_text(self) -> bool:
        return self in {Dataset.NEWS_BASELINE, Dataset.NEWS_RECENT, Dataset.MACRO}

    @property
    def is_tabular(self) -> bool:
        return not self.is_text


def shift_months(d: date, months: int) -> date:
    """Move `d` by `months` calendar months, clamping to the end of the month.

    Written out rather than pulled from dateutil because it is six lines and
    this module is imported by everything -- including the tests, which should
    not need a third-party package to check a date arithmetic edge case.

    Clamping matters: 2024-03-31 shifted back two months is 2024-01-31, but
    shifted back one month has to be 2024-02-29, not a nonexistent 2024-02-31.

    >>> shift_months(date(2024, 3, 31), -1)
    datetime.date(2024, 2, 29)
    >>> shift_months(date(2024, 1, 15), -12)
    datetime.date(2023, 1, 15)
    """
    total = (d.year * 12 + d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True, slots=True)
class DateWindow:
    """A half-open date range, `start <= t < end`.

    Half-open is not a style preference. A row stamped exactly `as_of` is a row
    you would not have had when standing on `as_of`, and the boundary between
    DS2 and DS3 has to fall on one side or the other without being counted
    twice.
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(f"empty window: {self.start} >= {self.end}")

    def contains(self, d: date) -> bool:
        return self.start <= d < self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    def __str__(self) -> str:
        return f"[{self.start.isoformat()}, {self.end.isoformat()})"


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """All five windows for one as-of date.

    Construct with `WindowSpec.for_as_of(...)` rather than by hand -- the
    lookback lengths are part of the project's definition, not per-call
    parameters, and having them in one place is what lets the ingest cache key
    on `(dataset, as_of)` and stay coherent.
    """

    as_of: date
    equity_years: int = 5
    index_years: int = 2
    news_months: int = 12
    recent_months: int = 2
    macro_months: int = 6

    @classmethod
    def for_as_of(cls, as_of: date | None = None, **overrides: int) -> "WindowSpec":
        return cls(as_of=as_of or date.today(), **overrides)

    # --- the five windows ------------------------------------------------

    @property
    def prices_equity(self) -> DateWindow:
        return DateWindow(shift_months(self.as_of, -12 * self.equity_years), self.as_of)

    @property
    def news_baseline(self) -> DateWindow:
        return DateWindow(
            shift_months(self.as_of, -self.news_months),
            shift_months(self.as_of, -self.recent_months),
        )

    @property
    def news_recent(self) -> DateWindow:
        return DateWindow(shift_months(self.as_of, -self.recent_months), self.as_of)

    @property
    def prices_index(self) -> DateWindow:
        return DateWindow(shift_months(self.as_of, -12 * self.index_years), self.as_of)

    @property
    def macro(self) -> DateWindow:
        return DateWindow(shift_months(self.as_of, -self.macro_months), self.as_of)

    def window(self, ds: Dataset) -> DateWindow:
        return getattr(self, ds.value)

    def all_windows(self) -> dict[Dataset, DateWindow]:
        return {ds: self.window(ds) for ds in Dataset}

    # --- the label side --------------------------------------------------

    def label_window(self, horizon_days: int = DEFAULT_HORIZON_DAYS) -> DateWindow:
        """The forward range the target is measured over.

        Only meaningful in training. At inference time this range is the future
        and no data exists in it -- that is the whole point of the exercise.
        Expressed in calendar days so it can be compared against a date index;
        `horizon_days` is in *trading* days, hence the 7/5 widening plus a few
        days of slack for holidays.
        """
        calendar_days = int(horizon_days * 7 / 5) + 5
        return DateWindow(self.as_of, self.as_of + timedelta(days=calendar_days))

    def is_labellable(self, today: date | None = None,
                      horizon_days: int = DEFAULT_HORIZON_DAYS) -> bool:
        """True when the forward window has fully elapsed, so a label exists.

        The last ~6 weeks of any historical sweep are *not* trainable rows: the
        30-day outcome has not happened yet. Silently including them is how you
        end up training on a target column that is mostly NaN.
        """
        return self.label_window(horizon_days).end <= (today or date.today())

    def describe(self) -> str:
        rows = [f"as_of {self.as_of.isoformat()}"]
        rows += [f"  {ds.value:<14} {self.window(ds)}  ({self.window(ds).days:>5}d)"
                 for ds in Dataset]
        return "\n".join(rows)


def as_of_grid(
    start: date,
    end: date,
    *,
    step_days: int = 7,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    today: date | None = None,
) -> list[date]:
    """The as-of dates to build training rows for.

    Weekly by default. Two competing pressures set the step:

    - Smaller steps give more rows, but consecutive rows share almost all of
      their input windows and almost all of their forward return window, so the
      extra rows are near-duplicates. They inflate your row count without
      adding information, and they make a random CV split look far better than
      the model really is, because the "same" example lands in both folds.
    - Larger steps give genuinely independent rows, but fewer of them.

    Weekly with a 21-day horizon still overlaps -- consecutive rows share three
    of four weeks of forward return. That overlap is exactly why `evaluate.py`
    uses `TimeSeriesSplit` with a purge gap instead of `KFold`. If you want
    strictly non-overlapping labels, pass `step_days=30`.

    Rows whose forward window has not finished are dropped, not returned with a
    null label.
    """
    if step_days < 1:
        raise ValueError("step_days must be >= 1")
    today = today or date.today()

    out, cursor = [], start
    while cursor <= end:
        if WindowSpec.for_as_of(cursor).is_labellable(today, horizon_days):
            out.append(cursor)
        cursor += timedelta(days=step_days)
    return out
