from __future__ import annotations

from typing import Iterable


def equity_curve(trade_pnls: Iterable[float], starting_capital: float = 1000.0) -> list[float]:
    curve: list[float] = [starting_capital]
    running = starting_capital
    for p in trade_pnls:
        try:
            running += float(p)
        except (TypeError, ValueError):
            continue
        curve.append(running)
    return curve


CLOSE_EVENTS = {"TP_FILLED", "WIN_EXPIRY", "LOSS_EXPIRY", "STOP_LOSS"}


def equity_timeseries(events, starting_capital: float = 1000.0) -> list[dict]:
    """Build [{t, v}] from a list of TradeEvent objects (filtered to one instance).

    Uses the `capital` column directly (already cumulative after each event), falling back
    to a running sum of `pnl` if capital is missing.
    """
    points: list[dict] = []
    running = starting_capital
    seeded = False
    for ev in events:
        if ev.event not in CLOSE_EVENTS:
            continue
        ts = ev.timestamp
        if ev.capital is not None:
            running = float(ev.capital)
        elif ev.pnl is not None:
            running += float(ev.pnl)
        else:
            continue
        if not seeded and points == []:
            # Synthesize a starting point one second before the first close event
            points.append({"t": ts, "v": starting_capital})
            seeded = True
        points.append({"t": ts, "v": running})
    return points
