"""pytest configuration."""

import os
import sys
from pathlib import Path

# Set SQLite URL before any app imports (database.py creates engine at module level)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

# Ensure the backend package is importable
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))