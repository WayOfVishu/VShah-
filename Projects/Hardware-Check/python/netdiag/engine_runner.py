"""
Runs the compiled C++ engine as a subprocess and parses its JSON stdout.

TODO (Phase 4, week 8 — docs/TODO.md #NET-4). Secondary learning objective
(project-charter.md Section 2: "multi-language IPC ... and structured data
exchange"). This is the actual boundary between the two languages in this
project — worth taking seriously even though it's "only" subprocess.run(),
because everything that can go wrong at a process boundary is exactly what
project-charter.md Section 6's Reliability requirement and Section 10's
"subprocess/IPC hangs or truncates" risk are about.

Design questions:
  1. subprocess.run(..., capture_output=True, text=True) gets you stdout
     and stderr separately, plus a return code. main.cpp (C++ side)
     deliberately writes JSON to stdout and error text to stderr, and exits
     non-zero on failure — go re-read cpp/src/main.cpp's comment on why,
     then decide what this function does with each of those three signals.
  2. What if config.SYSDIAG_ENGINE_PATH doesn't exist at all (the binary was
     never built)? That's a different failure mode from "the binary ran and
     exited non-zero" — should it be reported differently to the caller?
  3. subprocess.run has a `timeout=` parameter. sysdiag_engine is supposed
     to finish in well under a second for a normal snapshot
     (project-charter.md Section 6, Performance) — what timeout value
     would actually catch a hang without being so tight it flags a slow-but-
     fine run as broken?
  4. json.loads() on the captured stdout can itself raise
     json.JSONDecodeError if the C++ side ever prints something that isn't
     valid JSON (a stray debug print, a partial write). Should that be
     treated the same as "the engine exited non-zero", or differently?
"""

from pathlib import Path
from typing import Any

from netdiag import config


def run_engine(memory_demo: str | None = None) -> dict[str, Any]:
    """Invoke the compiled sysdiag_engine binary and return its parsed JSON report.

    memory_demo: if given, passed through as --memory-demo=<value> (see
    cpp/src/main.cpp's usage comment for valid values). Leave None for a
    normal diagnostic pass — see memory_sandbox.hpp's design question 2 for
    why that flag isn't on by default.
    """
    engine_path: Path = config.SYSDIAG_ENGINE_PATH
    raise NotImplementedError("run_engine() is not implemented yet — see docs/TODO.md #NET-4")
