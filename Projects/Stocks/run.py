#!/usr/bin/env python3
"""Repo-root entry point -- mirrors hwcheck.py and Portfolio's run.py.

Lets you run `py run.py <command>` from Projects/Stocks/ without setting
PYTHONPATH. Mechanical plumbing; the real CLI is in stocks/cli.py.

    py run.py demo                offline end-to-end run. Start here.
    py run.py providers           which provider serves each dataset
    py run.py fetch AAPL          build one bundle for a ticker
    py run.py build-panel --symbols AAPL,MSFT
    py run.py train
    py run.py serve               the FastAPI backend
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stocks.cli import main  # noqa: E402  (import after sys.path fixup, intentionally)

if __name__ == "__main__":
    sys.exit(main())
