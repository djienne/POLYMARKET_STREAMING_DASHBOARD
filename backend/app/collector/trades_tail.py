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
from ..models import TodaySummary, TradeEvent
from ..time_utils import paris_date_key

log = logging.getLogger(__name__)

MAX_RECENT_PER_INSTANCE = 200
REALIZED_EVENTS = {
    "TP_FILLED",
    "WIN_EXPIRY",
    "LOSS_EXPIRY",
    "STOP_LOSS",
    "UNRESOLVED_RESTART",
}
WIN_EVENTS = {"TP_FILLED", "WIN_EXPIRY"}
LOSS_EVENTS = {"STOP_LOSS", "LOSS_EXPIRY"}


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


# Single-trader CSVs (live/paper 15m) don't carry an instance_id — pin to the
# dashboard's default selected instance so the frontend filter matches.
SINGLE_TRADER_INSTANCE_ID = 100


def _row_to_events(row: dict) -> list[TradeEvent]:
    """Parse one CSV row into 0, 1, or 2 TradeEvents.

    Two schemas supported:
    - Grid per-event (instance_id, timestamp, event, ...) → 1 event
    - Single-trader per-position (id, opened_at, closed_at, result, ...) →
      ENTRY at opened_at + close event at closed_at
    """
    iid = _to_int(row.get("instance_id", ""))
    if iid is not None:
        ev = TradeEvent(
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
        return [ev]

    opened_at = row.get("opened_at", "") or ""
    if not opened_at:
        return []
    direction = row.get("direction") or None
    entry_price = _to_float(row.get("entry_price", ""))
    exit_price = _to_float(row.get("exit_price", ""))
    shares = _to_float(row.get("shares", ""))
    pnl = _to_float(row.get("pnl", ""))
    pnl_pct = _to_float(row.get("pnl_pct", ""))
    model_prob = _to_float(row.get("model_prob", ""))
    poly_prob = _to_float(row.get("poly_price", ""))
    spot_price = _to_float(row.get("spot_price", ""))
    barrier = _to_float(row.get("reference_price", ""))
    closed_at = row.get("closed_at", "") or ""
    result = (row.get("result", "") or "").strip()

    entry_ev = TradeEvent(
        instance_id=SINGLE_TRADER_INSTANCE_ID,
        timestamp=opened_at,
        event="ENTRY",
        direction=direction,
        market_id=None,
        entry_price=entry_price,
        exit_price=None,
        shares=shares,
        pnl=None,
        pnl_pct=None,
        capital=None,
        model_prob=model_prob,
        poly_prob=poly_prob,
        spot_price=spot_price,
        barrier=barrier,
    )
    if not closed_at or not result:
        return [entry_ev]
    close_ev = TradeEvent(
        instance_id=SINGLE_TRADER_INSTANCE_ID,
        timestamp=closed_at,
        event=result,
        direction=direction,
        market_id=None,
        entry_price=entry_price,
        exit_price=exit_price,
        shares=shares,
        pnl=pnl,
        pnl_pct=pnl_pct,
        capital=None,
        model_prob=model_prob,
        poly_prob=poly_prob,
        spot_price=spot_price,
        barrier=barrier,
    )
    return [entry_ev, close_ev]


class TradesTail:
    def __init__(self, path_fn) -> None:
        self._path_fn = path_fn
        self._offset: int = 0
        self._header: Optional[list[str]] = None
        self._recent_per_instance: dict[int, Deque[TradeEvent]] = {}
        self._realized_per_instance: dict[int, list[TradeEvent]] = {}
        self._daily_per_instance: dict[int, dict[str, TodaySummary]] = {}
        self._last_size: int = 0

    @property
    def path(self) -> Path:
        return self._path_fn()

    def _push(self, event: TradeEvent) -> None:
        dq = self._recent_per_instance.setdefault(
            event.instance_id,
            deque(maxlen=MAX_RECENT_PER_INSTANCE),
        )
        dq.append(event)
        if event.event in REALIZED_EVENTS and (
            event.capital is not None or event.pnl is not None
        ):
            history = self._realized_per_instance.setdefault(event.instance_id, [])
            history.append(event)
        day_key = paris_date_key(event.timestamp)
        if day_key:
            by_day = self._daily_per_instance.setdefault(event.instance_id, {})
            summary = by_day.setdefault(day_key, TodaySummary())
            if event.event == "ENTRY":
                summary.entries += 1
            if event.event in REALIZED_EVENTS:
                summary.closed += 1
                if event.pnl is not None:
                    summary.pnl += event.pnl
                if event.event in WIN_EVENTS:
                    summary.wins += 1
                elif event.event in LOSS_EVENTS:
                    summary.losses += 1

    def seed(self, per_instance_limit: int = MAX_RECENT_PER_INSTANCE) -> list[TradeEvent]:
        """Read entire file once, populate per-instance buffers, advance offset to EOF."""
        p = self.path
        if not p.exists():
            return []
        new_events: list[TradeEvent] = []
        try:
            with p.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                self._header = reader.fieldnames
                for row in reader:
                    for ev in _row_to_events(row):
                        self._push(ev)
                        new_events.append(ev)
                self._offset = f.tell()
            self._last_size = p.stat().st_size
        except OSError:
            return []
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
            self._recent_per_instance.clear()
            self._realized_per_instance.clear()
            self._daily_per_instance.clear()
            return self.seed()
        if size == self._last_size:
            return []
        self._last_size = size

        new_events: list[TradeEvent] = []
        try:
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
                    for ev in _row_to_events(row):
                        self._push(ev)
                        new_events.append(ev)
        except OSError:
            return []
        return new_events

    def recent(self, instance_id: int, n: int = 50) -> list[TradeEvent]:
        dq = self._recent_per_instance.get(instance_id)
        if not dq:
            return []
        items = list(dq)
        items.reverse()
        return items[:n]

    def chronological(self, instance_id: int) -> list[TradeEvent]:
        return self.realized_history(instance_id)

    def realized_history(self, instance_id: int) -> list[TradeEvent]:
        return list(self._realized_per_instance.get(instance_id, []))

    def today_summary(self, instance_id: int, day_key: str) -> TodaySummary:
        summary = self._daily_per_instance.get(instance_id, {}).get(day_key)
        return summary.model_copy() if summary else TodaySummary()


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
