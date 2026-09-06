"""Feature engineering -- five datasets to one modelling table.

    tabular.py   DS1 + DS4 -> price, risk, and Chapter 8 index-model features
    text.py      DS2 + DS3 + DS5 -> sentiment, attention, and shift features
    assemble.py  everything -> one row, and rows -> the training panel

The entry point is `build_panel`. Everything else is called by it.

Column prefixes carry meaning and `pipeline.py` routes on them:

    meta_*    provenance. Dropped before fitting.
    text_*    raw strings, vectorised inside the sklearn Pipeline.
    eq_*      DS1 price/risk features
    idx_*     DS4 index features
    scl_*     DS1 x DS4 -- the single-index regression (Chapter 8)
    ds2_*     DS2 news baseline statistics
    ds3_*     DS3 recent news + community statistics
    ds5_*     DS5 macro text statistics
    shift_*   DS2 vs DS3 -- the deltas the dataset split exists for
    macro_*   DS5's numeric panel (FRED)
    target    the label
"""

from __future__ import annotations

from .assemble import META_PREFIX, TEXT_PREFIX, build_panel, build_row, compute_target

__all__ = ["build_panel", "build_row", "compute_target", "META_PREFIX", "TEXT_PREFIX"]
