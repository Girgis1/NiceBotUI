"""Shared constants for the dashboard tab."""

from pathlib import Path

import pytz

ROOT = Path(__file__).parent.parent
TIMEZONE = pytz.timezone("Australia/Sydney")
HISTORY_PATH = ROOT / "run_history.json"
