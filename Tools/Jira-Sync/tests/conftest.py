"""Puts the tool's root on sys.path so `from jira_sync import ...` resolves
when pytest is run from anywhere.

Same approach as Stocks' tests/conftest.py — no `pip install -e .`, no
packaging ceremony for something run from its own directory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
