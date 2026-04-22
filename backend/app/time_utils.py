from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def parse_utc_iso(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_to_unix(value: Optional[str]) -> Optional[float]:
    dt = parse_utc_iso(value)
    return dt.timestamp() if dt is not None else None
