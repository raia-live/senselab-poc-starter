"""Shared helpers for the examples. Kept small so each run.py reads top to bottom.

Importing this package loads the ``.env`` at the repository root into the
process environment. Values already set in the environment win, so
``AMFS_API_KEY=... python examples/...`` overrides the file.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"

load_dotenv(REPO_ROOT / ".env", override=False)
