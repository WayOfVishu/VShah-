"""Stock forecasting from prices, news, community sentiment, and macro context.

Five datasets, defined relative to an as-of date, through one ML pipeline, to a
30-day forecast.

    from stocks import build_datasets, build_panel, build_pipeline

    bundle = build_datasets("AAPL")               # the five datasets, today
    panel  = build_panel(["AAPL"], start, end)    # a walk-forward training set
    pipe   = build_pipeline(panel)                # sklearn Pipeline, ready to fit

Layout:

    windows.py    the five-window spec -- read this first, it defines everything
    config.py     environment settings
    resolve.py    free text -> ticker
    ingest/       the five datasets, behind one provider-agnostic function
    finance/      Bodie/Kane/Marcus Ch 1-8 math: returns, risk, portfolio, index model
    features/     datasets -> a modelling table
    pipeline.py   the sklearn pipeline -- THIS IS THE FILE TO WORK IN
    evaluate.py   purged walk-forward validation and honest metrics
    cli.py        command line, entered via run.py
"""

from __future__ import annotations

__version__ = "0.1.0"

from .features.assemble import build_panel, build_row, compute_target
from .ingest import DatasetBundle, build_datasets
from .pipeline import build_pipeline
from .windows import DEFAULT_HORIZON_DAYS, Dataset, WindowSpec, as_of_grid

__all__ = [
    "__version__",
    "Dataset",
    "WindowSpec",
    "DatasetBundle",
    "DEFAULT_HORIZON_DAYS",
    "as_of_grid",
    "build_datasets",
    "build_panel",
    "build_row",
    "build_pipeline",
    "compute_target",
]
