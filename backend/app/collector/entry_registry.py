"""Dedup ENTRY trade events across the two emitters.

- state_reader publishes an ENTRY via ``trade.append`` the instant the live
  state file flips from no-position to position-open. This is the fast path
  that makes the entry GIF and entry chart marker appear at open time.
- trades_tail reads rows from ``15m_live_trades.csv``. Single-trader rows
  only appear at close time, but they contain both ``opened_at`` and
  ``closed_at``, so ``_row_to_events`` naturally splits into
  [ENTRY, CLOSE]. That ENTRY is retroactive — minutes late — and would
  re-fire the GIF alongside the WIN/LOSS gif if not suppressed.

This registry is the handshake: whichever path emits ENTRY first marks the
``opened_at`` here, and the other skips. Strings are compared verbatim, so
both sides must read ``opened_at`` from the same source shape (they do —
live trader writes ISO-8601 with microseconds from a single datetime
instance for both state.json and trades.csv).
"""
from __future__ import annotations

from threading import Lock

_lock = Lock()
_emitted: set[str] = set()


def mark_emitted(opened_at: str) -> None:
    if not opened_at:
        return
    with _lock:
        _emitted.add(opened_at)


def was_emitted(opened_at: str) -> bool:
    if not opened_at:
        return False
    with _lock:
        return opened_at in _emitted


def reset() -> None:
    with _lock:
        _emitted.clear()
