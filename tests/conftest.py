"""pytest configuration — add backend to sys.path."""

import sys
from pathlib import Path

# Ensure the backend package is importable
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))