"""Put the project root on sys.path so `import stocks` works without installing.

The project is deliberately not packaged with a pyproject/setup.py -- it is a
personal project run from its own directory, and `pip install -e .` would be
ceremony without benefit here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
