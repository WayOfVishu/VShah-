#!/usr/bin/env python3
"""Project-root entry point -- mirrors Stocks' run.py and Hardware-Check's hwcheck.py.

Lets you run `py run.py <command>` from Projects/League-ML/ without setting
PYTHONPATH. Mechanical plumbing; the real CLI is in leagueml/cli.py.

    py run.py demo                offline end-to-end run. Start here.
    py run.py train --model mlp   one network vs the floor
    py run.py pipeline            the draft's run_pipeline.py, as one command
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from leagueml.cli import main  # noqa: E402  (import after sys.path fixup, intentionally)

if __name__ == "__main__":
    sys.exit(main())
