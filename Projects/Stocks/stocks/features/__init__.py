"""Feature engineering -- three datasets to one modelling table.

    tabular.py   DS1 + DS2 -> price, risk, and Chapter 8-12 index-model features
    synthesis.py DS3's brief -> ~15 named gem_* sentiment scores
    text.py      the same corpora, scored by lexicon -- DS3's control group
    assemble.py  everything -> one row, and rows -> the training panel

The entry point is `build_panel`. Everything else is called by it.

Column prefixes carry meaning and `pipeline.py` routes on them:

    meta_*    provenance. Dropped before fitting.
    text_*    raw strings, vectorised inside the sklearn Pipeline.
    eq_*      DS1 price/risk features
    idx_*     DS2 index features
    scl_*     DS1 x DS2 -- the single-index regression (Chapter 8)
    capm_*    DS1 x DS2 -- the SML fair return and realised alpha (Chapter 9)
    ff_*      DS1 x DS2 -- the joint multifactor regression (Chapter 10)
    evt_*     DS1 x DS2 -- abnormal returns, CAR, momentum, reversal (Chapter 11)
    gem_*     DS3 -- the synthesised sentiment brief
    ds2_*     DS2 news baseline statistics
    ds3_*     DS3 recent news + community statistics
    ds5_*     macro text statistics (lexicon control)
    shift_*   DS2 vs DS3 -- the deltas the dataset split exists for
    macro_*   the numeric macro panel (FRED)
    target    the label
"""

from __future__ import annotations

from .assemble import META_PREFIX, TEXT_PREFIX, build_panel, build_row, compute_target

__all__ = ["build_panel", "build_row", "compute_target", "META_PREFIX", "TEXT_PREFIX"]
