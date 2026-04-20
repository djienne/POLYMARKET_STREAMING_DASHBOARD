from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from ..config import settings
from ..events.bus import bus
from ..models import LivenessInfo

log = logging.getLogger(__name__)


def _mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def current_liveness() -> LivenessInfo:
    lock = settings.lock_path()
    lock_exists = lock.exists()
    term_mtime = _mtime(settings.terminal_path())
    age = None
    if term_mtime is not None:
        age = max(0.0, time.time() - term_mtime)
    fresh = age is not None and age < 60.0
    return LivenessInfo(
        bot_live=lock_exists and fresh,
        lock_exists=lock_exists,
        terminal_age_s=age,
    )


async def run_liveness_loop(stop: asyncio.Event) -> None:
    last: Optional[bool] = None
    while not stop.is_set():
        info = current_liveness()
        if info.bot_live != last:
            last = info.bot_live
            await bus.publish("liveness.update", info.model_dump())
        # Always publish terminal_age tick so UI can show seconds since last tick
        await bus.publish("liveness.tick", info.model_dump())
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.state_poll_interval_seconds)
        except asyncio.TimeoutError:
            pass
