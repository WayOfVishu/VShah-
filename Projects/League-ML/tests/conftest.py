"""Put the project root on sys.path so `import leagueml` works without installing.

Same as Stocks' conftest: a personal project run from its own directory, where
`pip install -e .` would be ceremony without benefit.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
