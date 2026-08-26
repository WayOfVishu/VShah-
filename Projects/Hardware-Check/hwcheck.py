#!/usr/bin/env python3
"""
Repo-root entry point — lets you run `python hwcheck.py ...` from
hardware-check/ without fiddling with PYTHONPATH. Mechanical plumbing,
mirrors league-ml/run_pipeline.py's role in the other repo in this
workspace.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "python"))

from cli.main import main  # noqa: E402  (import after sys.path fixup, intentionally)

if __name__ == "__main__":
    sys.exit(main())
