"""Command-line interface. Entry point is `run.py` at the project root.

    py run.py demo                          offline end-to-end: the canary, then planted signal
    py run.py train --model mlp             one network vs the floor -- synthetic by default, or --data
    py run.py static                        Data Dragon champions + items for the target patch
    py run.py init-db                       create the SQLite schema
    py run.py ingest --max-matches 50       pull matches from the Riot API           (#ING-4)
    py run.py build-dataset                 raw JSON -> the participant table         (#FEAT-3)
    py run.py recommend --champion Ahri --enemy Zed --role MIDDLE                   (#REC-1)
    py run.py serve                         FastAPI backend on :8000
    py run.py pipeline                      static -> init-db -> ingest -> build-dataset -> train

Same shape as Stocks' cli.py on purpose. `demo` is the one to run first: no
key, no network, no ingested data, and it exercises synthetic matches ->
match-grouped split -> the floor -> the reference network -> evaluation. If it
prints two tables, the plumbing works, and anything that breaks afterwards is
a data or modelling problem rather than a wiring one.

A command that reaches an unbuilt TODO stops with that stub's
NotImplementedError, which names the docs/TODO.md tag to read. That is the
intended "not yet" signal -- the same one the draft's run_pipeline.py gave.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

from . import config

log = logging.getLogger("leagueml")


# --- experiment plumbing ---------------------------------------------------


def _make_splits(match_ids, start_ts, how: str, seed: int):
    from .evaluate import chronological_split, match_grouped_split, naive_row_split

    if how == "chronological":
        return chronological_split(match_ids, start_ts)
    if how == "naive-row":
        return naive_row_split(len(match_ids), seed=seed)
    return match_grouped_split(match_ids, seed=seed)


def _fit_and_compare(arrays: dict, floor_x: np.ndarray, splits, match_ids, *, model_name: str,
                     dims: dict, cfg, canary: bool = False, synthetic: bool = False,
                     save: Path | None = None, extra: dict | None = None):
    """The floor and one network on the same split, scored on the same test rows."""
    from .datasets import DictDataset
    from .evaluate import compare
    from .models import build_model
    from .models.baselines import majority_class_baseline, train_logistic_regression
    from .train import predict_proba, save_checkpoint, set_seed, train_model

    # Seeded *before* the model exists: building it draws the initial weights,
    # and a seed set afterwards (as train_model's own is) cannot reach them.
    # Built first, so an unimplemented model stops before any time goes on fitting.
    set_seed(cfg.seed)
    model = build_model(model_name, **dims)

    y = np.asarray(arrays["y"], dtype=np.float32)
    floor = train_logistic_regression(floor_x[splits.train], y[splits.train])
    predictions = {
        "majority": majority_class_baseline(y[splits.train], len(splits.test)),
        "logistic_regression": floor.predict_proba(floor_x[splits.test])[:, 1],
    }

    data = DictDataset(**arrays)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"training {model_name} ({n_params:,} parameters, {len(splits.train):,} training rows)")
    train_model(model, data.subset(splits.train), data.subset(splits.val), cfg)
    predictions[model_name] = predict_proba(model, data.subset(splits.test), device=cfg.device)

    if save:
        save_checkpoint(save, model, model_name=model_name, dims=dims, **(extra or {}))
        print(f"saved {save}")

    return compare(predictions, y[splits.test], split=splits.kind,
                   n_matches=splits.n_matches(match_ids), canary=canary, synthetic=synthetic)


def _synthetic_match_level(spec, n_matches: int, cfg, split: str, *, canary: bool,
                           save: Path | None = None):
    """The reference MLP on one row per match, over the demo's side encoding."""
    from .synthetic import generate_matches, side_encoding

    matches, _ = generate_matches(n_matches, spec)
    x = side_encoding(matches, spec.n_champions)
    ids = matches["meta_match_id"].to_numpy()
    splits = _make_splits(ids, matches["meta_game_start_ts"].to_numpy(), split, cfg.seed)
    return _fit_and_compare({"x": x, "y": matches["blue_win"].to_numpy()}, x, splits, ids,
                            model_name="mlp", dims={"n_features": x.shape[1]}, cfg=cfg,
                            canary=canary, synthetic=True, save=save)


def _synthetic_timeline(spec, n_matches: int, cfg, split: str, *, canary: bool,
                        save: Path | None = None):
    """The sequence model (#DL-7) on the synthetic gold-difference curves."""
    from .synthetic import generate_matches

    matches, _ = generate_matches(n_matches, spec)
    # (N, T, 1), raw gold. Scaling is deliberately not done here -- it is
    # question 2 in models/timeline.py.
    frames = np.stack(matches["gold_diff"].to_list())[:, :, None]
    floor_x = frames[:, -1, :]  # the strong floor: gold difference at the last minute alone
    ids = matches["meta_match_id"].to_numpy()
    splits = _make_splits(ids, matches["meta_game_start_ts"].to_numpy(), split, cfg.seed)
    return _fit_and_compare({"frames": frames, "y": matches["blue_win"].to_numpy()}, floor_x,
                            splits, ids, model_name="timeline", dims={"n_frame_features": 1},
                            cfg=cfg, canary=canary, synthetic=True, save=save)


def _participant_level(table, model_name: str, cfg, split: str, *, canary: bool,
                       synthetic: bool, save: Path | None = None):
    """Any model on the participant table -- synthetic or real, same columns."""
    from .features.encode import build_vocabularies, encode_ids, encode_multi_hot

    ids = table["meta_match_id"].to_numpy()
    splits = _make_splits(ids, table["meta_game_start_ts"].to_numpy(), split, cfg.seed)

    # Train rows only -- #FEAT-2 design question 2.
    vocabs = build_vocabularies(table.iloc[splits.train])
    arrays = encode_ids(table, vocabs)
    floor_x = encode_multi_hot(table, vocabs)
    dims = {"n_champions": len(vocabs["champion"]), "n_roles": len(vocabs["role"]),
            "n_items": len(vocabs["item"])}
    if model_name == "mlp":
        arrays, dims = {"x": floor_x, "y": arrays["y"]}, {"n_features": floor_x.shape[1]}

    return _fit_and_compare(arrays, floor_x, splits, ids, model_name=model_name, dims=dims,
                            cfg=cfg, canary=canary, synthetic=synthetic, save=save,
                            extra={"vocabs": vocabs})


def _train_config(args):
    from .train import TrainConfig

    return TrainConfig(epochs=args.epochs, lr=args.lr, batch_size=args.batch_size,
                       weight_decay=args.weight_decay, seed=args.seed,
                       device=config.resolve_device())


# --- commands --------------------------------------------------------------


def cmd_demo(args) -> int:
    """The canary, then planted signal. Offline, about a minute, and the first thing to run."""
    from .synthetic import SyntheticSpec
    from .train import TrainConfig

    cfg = TrainConfig(epochs=args.epochs, seed=args.seed, device=config.resolve_device())

    print("=" * 72)
    print("  Offline demo -- synthetic matches, no key, no network")
    print("=" * 72)

    print("\n[1/2] the canary: outcomes are coin flips, independent of every feature\n")
    canary = _synthetic_match_level(SyntheticSpec(signal=0.0, seed=args.seed), args.n_matches,
                                    cfg, "match-grouped", canary=True)
    print("\n" + canary.summary())

    print("\n[2/2] planted signal: champion strength, same-team synergy, item fit\n")
    planted = _synthetic_match_level(SyntheticSpec(signal=1.0, seed=args.seed), args.n_matches,
                                     cfg, "match-grouped", canary=False)
    print("\n" + planted.summary())

    print("\n" + "=" * 72)
    print("  A canary near AUC 0.5 is CORRECT -- the labels there are independent of")
    print("  the features by construction. The planted run should clear it easily.")
    print("  Watch the canary's val_loss climb while train_loss falls: that is the")
    print("  network memorising coin flips, and it is what #DL-3 is for. Whether the")
    print("  network beats logistic regression is #EVAL-3's question, and one seed")
    print("  cannot answer it. Next: docs/TODO.md, #EVAL-1 and #DL-1.")
    print("=" * 72)
    return 1 if canary.leak_detected else 0


def cmd_train(args) -> int:
    from .synthetic import SyntheticSpec, generate_matches, to_participant_rows

    cfg = _train_config(args)
    save = Path(args.save) if args.save else None

    if args.data:
        import pandas as pd

        if args.model == "timeline":
            raise NotImplementedError("real-data timeline inputs come from participant_frames -- "
                                      "see docs/TODO.md #FEAT-4 and #DL-7")
        table = pd.read_parquet(args.data)
        print(f"participant table: {len(table):,} rows from {args.data}\n")
        result = _participant_level(table, args.model, cfg, args.split, canary=False,
                                    synthetic=False, save=save)
    else:
        spec = SyntheticSpec(signal=args.signal, strength=args.strength, synergy=args.synergy,
                             seed=args.seed)
        canary = args.signal == 0
        note = " (the canary)" if canary else ""
        print(f"synthetic: {args.n_matches:,} matches, signal={args.signal}{note}\n")
        if args.model == "timeline":
            result = _synthetic_timeline(spec, args.n_matches, cfg, args.split, canary=canary, save=save)
        elif args.model == "mlp" and not args.participant:
            result = _synthetic_match_level(spec, args.n_matches, cfg, args.split, canary=canary, save=save)
        else:
            matches, _ = generate_matches(args.n_matches, spec)
            result = _participant_level(to_participant_rows(matches), args.model, cfg, args.split,
                                        canary=canary, synthetic=True, save=save)

    print("\n" + result.summary())
    return 0


def cmd_static(args) -> int:
    from .static.data_dragon import save_static_data

    print(f"Data Dragon {config.DDRAGON_VERSION} (patch {config.PATCH_LABEL}) -> {config.STATIC_DIR}")
    save_static_data(config.DDRAGON_VERSION)
    print("saved champions + items")
    return 0


def cmd_init_db(args) -> int:
    from .storage.db import init_db

    config.ensure_data_dirs()
    init_db()
    print(f"schema applied to {config.DB_PATH}")
    return 0


def cmd_ingest(args) -> int:
    from .ingestion.fetch_matches import run

    run(max_matches=args.max_matches)
    return 0


def cmd_build_dataset(args) -> int:
    from .features.build_feature_table import build_feature_table

    table = build_feature_table()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out)
    print(f"{len(table):,} participant rows -> {out}")
    return 0


def cmd_recommend(args) -> int:
    from .models import build_model
    from .recommend import recommend_items
    from .train import load_checkpoint

    path = Path(args.checkpoint)
    if not path.exists():
        print(f"no checkpoint at {path} -- train one first, e.g.")
        print(f"  py run.py train --model embedding --data data/processed/participants.parquet --save {path}")
        return 1
    checkpoint = load_checkpoint(path)
    model = build_model(checkpoint["model_name"], **checkpoint["dims"])
    model.load_state_dict(checkpoint["state_dict"])

    top = recommend_items(args.champion, args.enemy, args.role, model, checkpoint.get("vocabs"),
                          top_k=args.top_k)
    print(f"Top item recommendations for {args.champion} ({args.role}) vs. {args.enemy}:")
    for rank, (item_name, lift) in enumerate(top, start=1):
        print(f"  {rank}. {item_name}  ({lift:+.1%} predicted win-prob lift)")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    print(f"  api   http://{args.host}:{args.port}/api/health")
    print(f"  docs  http://{args.host}:{args.port}/docs")
    uvicorn.run("backend.app.main:app", host=args.host, port=args.port, reload=not args.no_reload)
    return 0


def cmd_pipeline(args) -> int:
    """The draft's run_pipeline.py -- single-command reproducibility (charter Section 9)."""
    from .features.build_feature_table import build_feature_table
    from .ingestion.fetch_matches import run as run_ingestion
    from .static.data_dragon import save_static_data
    from .storage.db import init_db

    print("[1/5] Setting up data directories + local database...")
    config.ensure_data_dirs()
    init_db()

    print(f"[2/5] Fetching Data Dragon {config.DDRAGON_VERSION} (patch {config.PATCH_LABEL})...")
    save_static_data(config.DDRAGON_VERSION)

    print("[3/5] Running ingestion (the long step -- resumable, see docs/TODO.md #ING-4)...")
    run_ingestion(max_matches=args.max_matches)

    print("[4/5] Building the participant table...")
    table = build_feature_table()
    out = config.PROCESSED_DIR / "participants.parquet"
    table.to_parquet(out)

    print(f"[5/5] Training + evaluating the floor and {args.model}...")
    result = _participant_level(table, args.model, _train_config(args), "chronological",
                                canary=False, synthetic=False,
                                save=config.CHECKPOINT_DIR / f"{args.model}.pt")
    print("\n" + result.summary())
    print("\nDone. Try: py run.py recommend --champion <you> --enemy <them> --role <role>")
    return 0


# --- parser ------------------------------------------------------------------


def _add_training_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--weight-decay", type=float, default=0.0, help="L2 penalty -- #DL-4")
    p.add_argument("--seed", type=int, default=config.SEED)


def build_parser() -> argparse.ArgumentParser:
    from .models import MODELS

    p = argparse.ArgumentParser(prog="leagueml", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")

    # -v works on either side of the subcommand. default=SUPPRESS stops the
    # subparser's False from overwriting a True the top-level parser already
    # set -- the argparse shared-flag trap Stocks' cli.py explains in full.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS)

    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, **kwargs) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], **kwargs)

    d = add("demo", help="offline end-to-end: the canary, then planted signal")
    d.add_argument("--n-matches", type=int, default=3000)
    d.add_argument("--epochs", type=int, default=30)
    d.add_argument("--seed", type=int, default=config.SEED)
    d.set_defaults(func=cmd_demo)

    t = add("train", help="one network vs the floor")
    t.add_argument("--model", default="mlp", choices=list(MODELS))
    t.add_argument("--data", help="participant table (.parquet) from build-dataset; omit for synthetic")
    t.add_argument("--n-matches", type=int, default=3000, help="synthetic only")
    t.add_argument("--signal", type=float, default=1.0, help="synthetic only; 0 is the canary")
    t.add_argument("--strength", type=float, default=0.5,
                   help="synthetic only; 0 leaves only interactions the floor cannot see (#EVAL-3)")
    t.add_argument("--synergy", type=float, default=1.0, help="synthetic only; same-team pair bonus")
    t.add_argument("--participant", action="store_true",
                   help="synthetic mlp on participant rows through #FEAT-2's encoder, not match rows")
    t.add_argument("--split", default="match-grouped",
                   choices=["match-grouped", "chronological", "naive-row"],
                   help="naive-row is wrong on purpose -- #EVAL-2")
    t.add_argument("--save", help="write the trained checkpoint here, e.g. data/checkpoints/mlp.pt")
    _add_training_args(t)
    t.set_defaults(func=cmd_train)

    add("static", help="Data Dragon champions + items for the target patch").set_defaults(func=cmd_static)
    add("init-db", help="create the SQLite schema").set_defaults(func=cmd_init_db)

    i = add("ingest", help="pull matches from the Riot API (#ING-4)")
    i.add_argument("--max-matches", type=int, default=None)
    i.set_defaults(func=cmd_ingest)

    b = add("build-dataset", help="raw JSON -> participant table (#FEAT-3)")
    b.add_argument("--out", default=str(config.PROCESSED_DIR / "participants.parquet"))
    b.set_defaults(func=cmd_build_dataset)

    r = add("recommend", help="top items for a matchup (#REC-1)")
    r.add_argument("--champion", required=True, help="your champion, e.g. Ahri")
    r.add_argument("--enemy", required=True, help="enemy laner's champion, e.g. Zed")
    r.add_argument("--role", required=True, choices=["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"])
    r.add_argument("--checkpoint", default=str(config.CHECKPOINT_DIR / "embedding.pt"))
    r.add_argument("--top-k", type=int, default=3)
    r.set_defaults(func=cmd_recommend)

    s = add("serve", help="run the FastAPI backend")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--no-reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    pl = add("pipeline", help="static -> init-db -> ingest -> build-dataset -> train")
    pl.add_argument("--max-matches", type=int, default=None)
    pl.add_argument("--model", default="embedding", choices=[m for m in MODELS if m != "timeline"])
    _add_training_args(pl)
    pl.set_defaults(func=cmd_pipeline)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)-7s %(name)-24s %(message)s", stream=sys.stderr)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except NotImplementedError as exc:
        if args.verbose:
            raise
        print(f"\nnot built yet: {exc}", file=sys.stderr)
        print("That is the intended 'not yet' signal -- read that tag in docs/TODO.md.",
              file=sys.stderr)
        return 2
    except Exception as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        if args.verbose:
            raise
        print("\n(re-run with -v for the full traceback)", file=sys.stderr)
        return 1
