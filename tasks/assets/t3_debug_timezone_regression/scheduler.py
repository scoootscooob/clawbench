from __future__ import annotations

from datetime import datetime, timezone


def format_run_window(iso_timestamp: str) -> str:
    dt = datetime.fromisoformat(iso_timestamp)
    # BUG: this treats aware timestamps as local time before converting to UTC.
    dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

