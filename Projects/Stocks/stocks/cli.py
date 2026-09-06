"""Command-line interface. Entry point is `run.py` at the project root.

    py run.py providers                      which provider serves each dataset
    py run.py windows --as-of 2025-06-01     print the five windows for a date
    py run.py resolve "apple"                free text -> ticker candidates
    py run.py fetch AAPL                     build one bundle, print a summary
    py run.py build-panel --symbols AAPL,MSFT --start 2022-01-01
    py run.py train --panel data/processed/panel.parquet
    py run.py demo                           end-to-end on synthetic data
    py run.py serve                          start the API

`demo` is the one to run first: it is fully offline, takes seconds, and
exercises ingest -> features -> pipeline -> evaluation in one go. If it passes,
the plumbing works and anything that breaks afterwards is a data problem rather
than a wiring problem.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from .config import get_settings
from .windows import DEFAULT_HORIZON_DAYS, WindowSpec

log = logging.getLogger("stocks")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(name)-28s %(message)s",
        stream=sys.stderr,
    )
    # yfinance and urllib3 are chatty at INFO and drown out the sweep progress.
    for noisy in ("urllib3", "yfinance", "peewee", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _parse_date(text: str) -> date:
    return date.fromisoformat(text)


# --- commands ------------------------------------------------------------


def cmd_providers(args) -> int:
    from .ingest.registry import Registry

    registry = Registry(force_synthetic=args.synthetic)
    print(registry.describe())
    print()

    settings = get_settings()
    print("keys detected:")
    for label, present in [
        ("ALPHAVANTAGE_API_KEY", bool(settings.alphavantage_key)),
        ("NEWSAPI_API_KEY", bool(settings.newsapi_key)),
        ("REDDIT_CLIENT_ID/SECRET", settings.has_reddit),
        ("FRED_API_KEY", bool(settings.fred_key)),
    ]:
        print(f"  {label:<26} {'yes' if present else 'no'}")
    print(f"\ndata dir: {settings.data_dir}")
    return 0


def cmd_windows(args) -> int:
    spec = WindowSpec.for_as_of(args.as_of)
    print(spec.describe())
    print(f"\n  label window   {spec.label_window(args.horizon)}  "
          f"({args.horizon} trading days forward)")
    print(f"  labellable     {spec.is_labellable(horizon_days=args.horizon)}")
    return 0


def cmd_resolve(args) -> int:
    from .resolve import resolve

    candidates = resolve(args.query)
    if not candidates:
        print(f"no match for {args.query!r}")
        return 1
    for c in candidates:
        print(f"  {c.confidence:.2f}  {c}  [{c.source}]")
    return 0


def cmd_fetch(args) -> int:
    from .ingest.registry import Registry, build_datasets
    from .resolve import resolve_one

    symbol = args.symbol if args.symbol.isupper() else resolve_one(args.symbol).symbol
    registry = Registry(force_synthetic=args.synthetic)

    print(f"fetching {symbol} as of {args.as_of or date.today()} ...\n")
    bundle = build_datasets(symbol, args.as_of, registry=registry)
    print(bundle.summary())

    if args.save:
        settings = get_settings()
        out = settings.interim_dir / f"{symbol}_{bundle.as_of.isoformat()}"
        out.mkdir(parents=True, exist_ok=True)
        bundle.prices_equity.to_parquet(out / "prices_equity.parquet")
        # Text goes out as .txt, per the original design -- one file per
        # document window, readable without any tooling.
        for name, docs in [("news_baseline", bundle.news_baseline),
                           ("news_recent", bundle.news_recent),
                           ("macro", bundle.macro_text)]:
            (out / f"{name}.txt").write_text(
                "\n\n---\n\n".join(f"[{d.published}] [{d.source}] {d.title}\n{d.text}"
                                   for d in docs),
                encoding="utf-8",
            )
        print(f"\nsaved to {out}")
    return 0


def cmd_build_panel(args) -> int:
    from .features.assemble import build_panel
    from .ingest.registry import Registry

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    registry = Registry(force_synthetic=args.synthetic)

    panel = build_panel(
        symbols, args.start, args.end,
        step_days=args.step, horizon_days=args.horizon,
        target_kind=args.target, registry=registry,
        sentiment_backend=args.sentiment,
    )

    print(f"\npanel: {panel.shape[0]} rows x {panel.shape[1]} columns")
    print(f"  date range   {panel['meta_as_of'].min().date()} .. {panel['meta_as_of'].max().date()}")
    print(f"  symbols      {', '.join(sorted(panel['meta_symbol'].unique()))}")
    print(f"  target       mean {panel['target'].mean():+.4f}  sd {panel['target'].std():.4f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out)
    print(f"\nsaved to {out}")
    return 0


def cmd_train(args) -> int:
    import pandas as pd

    from .evaluate import evaluate_pipeline
    from .pipeline import baseline_models, build_pipeline

    panel = pd.read_parquet(args.panel)
    print(f"panel: {panel.shape[0]} rows x {panel.shape[1]} columns\n")

    results = {}
    for name, model in baseline_models().items():
        print(f"--- {name} ---")
        pipe = build_pipeline(panel, model)
        result = evaluate_pipeline(pipe, panel, n_splits=args.splits,
                                   step_days=args.step, horizon_days=args.horizon)
        print(result.summary(), "\n")
        results[name] = result.pooled.get("information_coefficient", float("nan"))

    best = max(results, key=lambda k: results[k] if results[k] == results[k] else -9e9)
    print(f"best by information coefficient: {best} ({results[best]:.4f})")
    print("\nNext: open notebooks/01_pipeline_playground.ipynb and work through docs/TODO.md.")
    return 0


def cmd_demo(args) -> int:
    """End-to-end on synthetic data. Offline, fast, and the first thing to run."""
    from .evaluate import evaluate_pipeline
    from .features.assemble import build_panel
    from .ingest.registry import Registry
    from .pipeline import build_pipeline

    print("=" * 72)
    print("  Offline demo -- synthetic data, no network, no keys")
    print("=" * 72)

    registry = Registry(force_synthetic=True)
    print("\n" + registry.describe())

    end = date.today() - timedelta(days=45)
    start = end - timedelta(days=730)

    print(f"\nbuilding panel: 3 symbols, {start} .. {end}, fortnightly")
    panel = build_panel(["DEMO1", "DEMO2", "DEMO3"], start, end,
                        step_days=14, registry=registry, progress=False)
    print(f"  {panel.shape[0]} rows x {panel.shape[1]} columns")

    print("\nfitting Ridge and evaluating walk-forward ...\n")
    result = evaluate_pipeline(build_pipeline(panel), panel, n_splits=4, step_days=14)
    print(result.summary())

    print("\n" + "=" * 72)
    print("  The synthetic price and text series are independent by construction,")
    print("  so a score near zero here is CORRECT. A strong score would mean the")
    print("  pipeline is leaking. See ingest/prices.py SyntheticPriceProvider.")
    print("=" * 72)
    return 0


def cmd_serve(args) -> int:
    import os

    import uvicorn

    # The routers build their own Registry per request, so the only way to
    # force synthetic app-wide is through the environment.
    if args.synthetic:
        os.environ["STOCKS_FORCE_SYNTHETIC"] = "true"
        print("  !! --synthetic: serving generated data, not real market data\n")

    print(f"  app   http://{args.host}:{args.port}/")
    print(f"  api   http://{args.host}:{args.port}/api/health")
    print(f"  docs  http://{args.host}:{args.port}/docs")
    uvicorn.run("backend.app.main:app", host=args.host, port=args.port, reload=not args.no_reload)
    return 0


# --- parser --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stocks", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--synthetic", action="store_true",
                   help="force the offline synthetic providers for every dataset")

    # The same two flags again, so they work on either side of the subcommand:
    # `py run.py --synthetic fetch AAPL` and `py run.py fetch AAPL --synthetic`
    # both read naturally, and every example in the README and the docstrings
    # uses the trailing form.
    #
    # `default=argparse.SUPPRESS` is what makes this safe. Without it, a
    # subparser's `store_true` default of False would overwrite a True already
    # set by the top-level parser, so the leading form would silently stop
    # working -- the classic argparse shared-flag trap. SUPPRESS leaves the
    # attribute unset when the flag is absent, so the top-level value survives.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--synthetic", action="store_true", default=argparse.SUPPRESS,
                        help="force the offline synthetic providers for every dataset")

    sub = p.add_subparsers(dest="command", required=True, parser_class=argparse.ArgumentParser)

    def add(name: str, **kwargs) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], **kwargs)

    add("providers", help="show which provider serves each dataset").set_defaults(func=cmd_providers)

    w = add("windows", help="print the five dataset windows for an as-of date")
    w.add_argument("--as-of", type=_parse_date, default=None)
    w.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_DAYS)
    w.set_defaults(func=cmd_windows)

    r = add("resolve", help="resolve free text to ticker candidates")
    r.add_argument("query")
    r.set_defaults(func=cmd_resolve)

    f = add("fetch", help="build one dataset bundle and summarise it")
    f.add_argument("symbol")
    f.add_argument("--as-of", type=_parse_date, default=None)
    f.add_argument("--save", action="store_true", help="write the bundle to data/interim/")
    f.set_defaults(func=cmd_fetch)

    b = add("build-panel", help="walk-forward sweep -> training panel")
    b.add_argument("--symbols", required=True, help="comma-separated tickers")
    b.add_argument("--start", type=_parse_date, default=date.today() - timedelta(days=1095))
    b.add_argument("--end", type=_parse_date, default=date.today() - timedelta(days=45))
    b.add_argument("--step", type=int, default=7, help="days between as-of dates")
    b.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_DAYS)
    b.add_argument("--target", default="log_return", choices=["log_return", "direction", "volatility"])
    b.add_argument("--sentiment", default="vader", choices=["vader", "lexicon", "finbert"])
    b.add_argument("--out", default="data/processed/panel.parquet")
    b.set_defaults(func=cmd_build_panel)

    t = add("train", help="baseline models + walk-forward evaluation")
    t.add_argument("--panel", default="data/processed/panel.parquet")
    t.add_argument("--splits", type=int, default=5)
    t.add_argument("--step", type=int, default=7)
    t.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_DAYS)
    t.set_defaults(func=cmd_train)

    add("demo", help="offline end-to-end run on synthetic data").set_defaults(func=cmd_demo)

    s = add("serve", help="run the FastAPI backend")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--no-reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        if args.verbose:
            raise
        print("\n(re-run with -v for the full traceback)", file=sys.stderr)
        return 1
