from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from ..config import settings
from ..events.bus import bus
from ..models import InstanceStats, OpenPosition, PositionState

log = logging.getLogger(__name__)

STARTING_CAPITAL = 1000.0


def _compute_sharpe(pnls: list[float]) -> float:
    if len(pnls) < 2:
        return 0.0
    import math
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return mean / sd * math.sqrt(len(pnls))


def _compute_max_dd(pnls: list[float], starting: float) -> tuple[float, float]:
    peak = starting
    equity = starting
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = (max_dd / starting) * 100.0 if starting else 0.0
    return max_dd, max_dd_pct


def instance_from_raw(instance_id: int, raw: dict, starting_capital: float = STARTING_CAPITAL) -> InstanceStats:
    pnls = [float(x) for x in raw.get("trade_pnls", []) if isinstance(x, (int, float))]
    capital = float(raw.get("capital", starting_capital))
    total_pnl = float(raw.get("total_pnl", capital - starting_capital))
    wins = int(raw.get("wins", 0))
    losses = int(raw.get("losses", 0))
    trades = int(raw.get("trades_count", len(pnls)))
    wr = (wins / trades * 100.0) if trades else 0.0
    sharpe = _compute_sharpe(pnls)
    mdd, mdd_pct = _compute_max_dd(pnls, starting_capital)
    return InstanceStats(
        instance_id=instance_id,
        capital=capital,
        starting_capital=starting_capital,
        total_pnl=total_pnl,
        total_pnl_pct=(total_pnl / starting_capital) * 100.0 if starting_capital else 0.0,
        sharpe=sharpe,
        max_drawdown=mdd,
        max_drawdown_pct=mdd_pct,
        wins=wins,
        losses=losses,
        win_rate=wr,
        trades_count=trades,
    )


def position_from_raw(raw: dict) -> PositionState:
    pos = raw.get("position")
    last_exit = raw.get("last_tp_sl_time")
    if not pos:
        return PositionState(open=None, last_exit_at=last_exit)
    try:
        open_pos = OpenPosition(
            direction=pos.get("direction"),
            entry_price=float(pos.get("entry_price", 0.0)),
            shares=float(pos.get("shares", 0.0)),
            tp_target=float(pos["tp_price"]) if pos.get("tp_price") is not None else None,
            sl_target=float(pos["stop_loss_price"]) if pos.get("stop_loss_price") is not None else None,
            entered_at=pos.get("opened_at"),
            market_id=pos.get("market_id"),
            notional=float(pos.get("cost_basis")) if pos.get("cost_basis") is not None else None,
        )
    except Exception:
        log.exception("position parse failed")
        open_pos = None
    return PositionState(open=open_pos, last_exit_at=last_exit)


class StateReader:
    def __init__(self, path_fn, instance_ids: Optional[list[int]] = None) -> None:
        """path_fn: callable returning Path to state file (so we can switch files based on mode)."""
        self._path_fn = path_fn
        self._last_mtime: Optional[float] = None
        self._raw: dict = {}

    @property
    def path(self) -> Path:
        return self._path_fn()

    def read_if_changed(self) -> bool:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return False
        if self._last_mtime is not None and st.st_mtime == self._last_mtime:
            return False
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("state read failed: %s", e)
            return False
        self._raw = raw
        self._last_mtime = st.st_mtime
        return True

    def instance(self, instance_id: int) -> Optional[InstanceStats]:
        raw = (self._raw.get("instances") or {}).get(str(instance_id))
        if raw is None:
            return None
        return instance_from_raw(instance_id, raw)

    def position(self, instance_id: int) -> PositionState:
        raw = (self._raw.get("instances") or {}).get(str(instance_id))
        if raw is None:
            return PositionState()
        return position_from_raw(raw)

    def trade_pnls(self, instance_id: int) -> list[float]:
        raw = (self._raw.get("instances") or {}).get(str(instance_id))
        if raw is None:
            return []
        return [float(x) for x in raw.get("trade_pnls", []) if isinstance(x, (int, float))]

    @property
    def raw(self) -> dict:
        return self._raw


async def run_state_loop(reader: "StateReader", stop: asyncio.Event) -> None:
    while not stop.is_set():
        if reader.read_if_changed():
            await bus.publish("state.update", {"mtime": reader._last_mtime})
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.state_poll_interval_seconds)
        except asyncio.TimeoutError:
            pass
