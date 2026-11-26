"""Shared helpers for the examples. Kept small so each run.py reads top to bottom.

Importing this package loads the ``.env`` at the repository root into the
process environment. Values already set in the environment win, so
``AMFS_API_KEY=... python examples/...`` overrides the file.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# The repository root, found from this file's location, so the examples work
# from any working directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
# Where examples 01 and 04 write their JSON results (gitignored).
RESULTS_DIR = REPO_ROOT / "results"

# Runs once, the first time an example imports anything from poc.
# override=False: a variable already set in the shell is kept.
load_dotenv(REPO_ROOT / ".env", override=False)
