from __future__ import annotations

import asyncio
import csv
import io
import logging
from collections import deque
from pathlib import Path
from typing import Deque, Optional

from ..config import settings
from ..events.bus import bus
from ..models import TradeEvent

log = logging.getLogger(__name__)

MAX_PER_INSTANCE = 200


def _to_float(v: str) -> Optional[float]:
    if v == "" or v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _to_int(v: str) -> Optional[int]:
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _row_to_event(row: dict) -> Optional[TradeEvent]:
    iid = _to_int(row.get("instance_id", ""))
    if iid is None:
        return None
    return TradeEvent(
        instance_id=iid,
        timestamp=row.get("timestamp", ""),
        event=row.get("event", ""),
        direction=row.get("direction") or None,
        market_id=row.get("market_id") or None,
        entry_price=_to_float(row.get("entry_price", "")),
        exit_price=_to_float(row.get("exit_price", "")),
        shares=_to_float(row.get("shares", "")),
        pnl=_to_float(row.get("pnl", "")),
        pnl_pct=_to_float(row.get("pnl_pct", "")),
        capital=_to_float(row.get("capital", "")),
        model_prob=_to_float(row.get("model_prob", "")),
        poly_prob=_to_float(row.get("poly_prob", "")),
        spot_price=_to_float(row.get("spot_price", "")),
        barrier=_to_float(row.get("barrier", "")),
    )


class TradesTail:
    def __init__(self, path_fn) -> None:
        self._path_fn = path_fn
        self._offset: int = 0
        self._header: Optional[list[str]] = None
        self._per_instance: dict[int, Deque[TradeEvent]] = {}
        self._last_size: int = 0

    @property
    def path(self) -> Path:
        return self._path_fn()

    def _push(self, event: TradeEvent) -> None:
        dq = self._per_instance.setdefault(event.instance_id, deque(maxlen=MAX_PER_INSTANCE))
        dq.append(event)

    def seed(self, per_instance_limit: int = MAX_PER_INSTANCE) -> list[TradeEvent]:
        """Read entire file once, populate per-instance buffers, advance offset to EOF."""
        p = self.path
        if not p.exists():
            return []
        new_events: list[TradeEvent] = []
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            self._header = reader.fieldnames
            for row in reader:
                ev = _row_to_event(row)
                if ev:
                    self._push(ev)
                    new_events.append(ev)
            self._offset = f.tell()
        self._last_size = p.stat().st_size
        return new_events

    def poll(self) -> list[TradeEvent]:
        p = self.path
        if not p.exists():
            return []
        try:
            size = p.stat().st_size
        except OSError:
            return []
        if size < self._offset:
            # Truncation/rotation — re-seed
            log.info("trades.csv truncated; re-seeding")
            self._offset = 0
            self._per_instance.clear()
            return self.seed()
        if size == self._last_size:
            return []
        self._last_size = size

        new_events: list[TradeEvent] = []
        with p.open("r", encoding="utf-8", newline="") as f:
            if self._header is None:
                # Need a header; read once
                reader = csv.DictReader(f)
                self._header = reader.fieldnames
                # fast-forward past lines we already consumed
                for row in reader:
                    pass
                self._offset = f.tell()
                return []
            f.seek(self._offset)
            # Only process complete lines
            remainder = f.read()
            if "\n" not in remainder:
                return []
            last_nl = remainder.rfind("\n")
            complete = remainder[: last_nl + 1]
            consumed = len(complete.encode("utf-8"))
            self._offset += consumed
            reader = csv.DictReader(io.StringIO(complete), fieldnames=self._header)
            for row in reader:
                ev = _row_to_event(row)
                if ev:
                    self._push(ev)
                    new_events.append(ev)
        return new_events

    def recent(self, instance_id: int, n: int = 50) -> list[TradeEvent]:
        dq = self._per_instance.get(instance_id)
        if not dq:
            return []
        items = list(dq)
        items.reverse()
        return items[:n]

    def chronological(self, instance_id: int) -> list[TradeEvent]:
        dq = self._per_instance.get(instance_id)
        if not dq:
            return []
        return list(dq)


async def run_trades_loop(tail: "TradesTail", stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            new_events = tail.poll()
        except Exception:  # noqa: BLE001
            log.exception("trades poll error")
            new_events = []
        for ev in new_events:
            await bus.publish("trade.append", ev.model_dump())
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_seconds)
        except asyncio.TimeoutError:
            pass
