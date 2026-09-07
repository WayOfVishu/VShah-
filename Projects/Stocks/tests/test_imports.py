"""Every module imports cleanly.

Added after a syntax error sat in `stocks/cli.py` while the whole suite passed:
nothing imported it, because the CLI is exercised by running `run.py` rather
than by tests. `py run.py serve` was broken and 131 green tests said otherwise.

This is a cheap, broad guard rather than real coverage. It catches syntax
errors, bad imports, and import-time exceptions in modules no other test
touches, which is exactly the gap that let that one through.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import backend
import stocks


def _module_names(package) -> list[str]:
    return [m.name for m in pkgutil.walk_packages(package.__path__, package.__name__ + ".")]


ALL_MODULES = sorted(_module_names(stocks) + _module_names(backend))


def test_the_walk_found_the_modules():
    """Guards the guard: if `walk_packages` returned nothing, the
    parametrized test below would vacuously pass."""
    assert len(ALL_MODULES) > 15
    assert "stocks.cli" in ALL_MODULES
    assert "backend.app.main" in ALL_MODULES


@pytest.mark.parametrize("module_name", ALL_MODULES)
def test_module_imports(module_name):
    importlib.import_module(module_name)


def test_cli_parser_builds_and_every_command_is_wired():
    """The CLI is normally exercised by running it, so nothing else here would
    notice a broken subcommand."""
    from stocks.cli import build_parser

    parser = build_parser()
    subparsers = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    assert subparsers, "no subcommands registered"

    commands = set(subparsers[0].choices)
    assert commands == {
        "providers",
        "models", "windows", "resolve", "fetch",
        "build-panel", "train", "demo", "serve",
    }

    # Every subcommand must have a handler, or it fails only when invoked.
    for name, sub in subparsers[0].choices.items():
        assert sub.get_default("func") is not None, f"{name} has no func"


def test_cli_parses_the_documented_invocations():
    from stocks.cli import build_parser

    parser = build_parser()
    for argv in (
        ["demo"],
        ["providers", "--synthetic"],
        ["windows", "--as-of", "2025-06-01"],
        ["resolve", "apple"],
        ["fetch", "AAPL", "--save"],
        ["build-panel", "--symbols", "AAPL,MSFT", "--start", "2022-01-01"],
        ["train", "--panel", "data/processed/panel.parquet"],
        ["serve", "--port", "9000"],
    ):
        assert parser.parse_args(argv).func is not None


def test_shared_flags_work_on_either_side_of_the_subcommand():
    """`--synthetic` and `-v` must parse both before and after the subcommand.

    Every example in the README and the module docstrings puts them last. A
    plain top-level flag only accepts the leading form, and adding it to the
    subparsers without `default=argparse.SUPPRESS` silently breaks the leading
    one instead -- so both directions are pinned here.
    """
    from stocks.cli import build_parser

    parser = build_parser()

    assert parser.parse_args(["--synthetic", "providers"]).synthetic is True
    assert parser.parse_args(["providers", "--synthetic"]).synthetic is True
    assert parser.parse_args(["providers"]).synthetic is False

    assert parser.parse_args(["-v", "demo"]).verbose is True
    assert parser.parse_args(["demo", "-v"]).verbose is True
    assert parser.parse_args(["demo"]).verbose is False


def test_every_subcommand_accepts_the_shared_flags():
    from stocks.cli import build_parser

    parser = build_parser()
    required = {
        "providers": [], "windows": [], "resolve": ["x"], "fetch": ["AAPL"],
        "build-panel": ["--symbols", "AAPL"], "train": [], "demo": [], "serve": [],
    }
    for command, extra in required.items():
        args = parser.parse_args([command, *extra, "--synthetic"])
        assert args.synthetic is True, command
