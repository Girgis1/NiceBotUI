"""Utility helpers for timezone-aware timestamps used by the vision system."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import pytz


def _load_timezone(name: Optional[str]):
    """Return a tzinfo for *name* if it is a valid timezone identifier."""
    if not name:
        return None
    try:
        return pytz.timezone(name)
    except Exception:
        return None


def get_timezone(preferred: Optional[str] = None):
    """Resolve the timezone to be used for timestamps.

    Resolution order:
      1. Explicit ``preferred`` identifier (from configuration).
      2. ``VISION_TIMEZONE`` environment variable.
      3. The local system timezone (if available).
      4. UTC.
    """

    tz = _load_timezone(preferred)
    if tz:
        return tz

    tz = _load_timezone(os.environ.get("VISION_TIMEZONE"))
    if tz:
        return tz

    try:
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is not None:
            zone_name = getattr(local_tz, "zone", None)
            fallback = _load_timezone(zone_name)
            return fallback or local_tz
    except Exception:
        pass

    return pytz.UTC


def now(tz=None) -> datetime:
    """Return the current time in the resolved timezone."""

    tzinfo = tz or get_timezone()
    return datetime.now(tzinfo)


def now_iso(tz=None) -> str:
    """Return an ISO-8601 timestamp using the resolved timezone."""

    return now(tz).isoformat()


def format_timestamp(fmt: str, tz=None) -> str:
    """Format the current time using *fmt* in the resolved timezone."""

    return now(tz).strftime(fmt)
