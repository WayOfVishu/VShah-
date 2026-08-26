"""
Scaffolded test for netdiag.engine_runner — skipped until #NET-4 lands
(see docs/TODO.md). Deliberately doesn't spin up the real C++ binary
(that's an integration concern, not a unit test) — it points at a small
fake "engine" script instead, so you can exercise the success/failure
handling without needing cpp/build/sysdiag_engine to exist or be correct.
"""

import stat
import sys

import pytest

from netdiag import engine_runner


@pytest.fixture
def fake_engine_script(tmp_path):
    """A tiny standalone script that behaves like sysdiag_engine's contract:
    valid JSON to stdout, exit 0. Written in Python for portability rather
    than shelling out to the real binary."""
    script = tmp_path / "fake_engine.py"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        'sys.stdout.write(\'{"system": {}, "memory_sandbox": []}\')\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.mark.skip(reason="netdiag.engine_runner.run_engine is not implemented yet — see docs/TODO.md #NET-4")
def test_returns_parsed_json_on_success(fake_engine_script, monkeypatch):
    # TODO once #NET-4 lands: point config.SYSDIAG_ENGINE_PATH at
    # fake_engine_script (monkeypatch.setattr) and assert run_engine()
    # returns the dict {"system": {}, "memory_sandbox": []} — i.e. that
    # stdout got parsed as JSON correctly.
    monkeypatch.setattr(engine_runner.config, "SYSDIAG_ENGINE_PATH", fake_engine_script)
    result = engine_runner.run_engine()
    assert result == {"system": {}, "memory_sandbox": []}


@pytest.mark.skip(reason="netdiag.engine_runner.run_engine is not implemented yet — see docs/TODO.md #NET-4")
def test_missing_binary_raises_a_clear_error(monkeypatch, tmp_path):
    # TODO: point SYSDIAG_ENGINE_PATH at a path that doesn't exist and
    # assert your chosen exception/return shape (design question 2 in
    # engine_runner.py) rather than an opaque FileNotFoundError bubbling
    # straight out of subprocess.run.
    monkeypatch.setattr(engine_runner.config, "SYSDIAG_ENGINE_PATH", tmp_path / "does_not_exist")
    with pytest.raises(Exception):
        engine_runner.run_engine()
