from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Optional

from ..config import settings
from ..events.bus import bus
from ..models import (
    MarketInfo,
    PolymarketPrices,
    ProbabilityBundle,
    TerminalSnapshot,
    TimingInfo,
)

MAX_MODEL_POINTS = 1000

log = logging.getLogger(__name__)


def _to_title(slug: Optional[str]) -> Optional[str]:
    # We don't have the title in terminal_data.json; leave None and let UI derive.
    return None


def parse_terminal(raw: dict, path_mtime: Optional[float] = None) -> TerminalSnapshot:
    ssvi = raw.get("ssvi_surface") or {}
    heston = raw.get("heston") or {}
    timing = raw.get("timing") or {}

    probs = ProbabilityBundle(
        ssvi_surface_above=ssvi.get("prob_above"),
        ssvi_surface_below=ssvi.get("prob_below"),
        mc_above=ssvi.get("mc_prob_above"),
        mc_below=ssvi.get("mc_prob_below"),
        heston_above=heston.get("prob_above") if isinstance(heston, dict) else None,
        heston_below=heston.get("prob_below") if isinstance(heston, dict) else None,
        bl_above=raw.get("bl_prob_above"),
        bl_below=raw.get("bl_prob_below"),
        avg_above=raw.get("avg_prob_above"),
        avg_below=raw.get("avg_prob_below"),
        bl_mc_divergence=raw.get("bl_mc_divergence"),
        preferred_model=raw.get("preferred_model"),
    )

    slug = raw.get("market_slug") or raw.get("slug")
    window_start = None
    window_end = None
    if slug:
        import re
        m = re.search(r"btc-updown-15m-(\d+)", slug)
        if m:
            window_start = int(m.group(1))
            window_end = window_start + 900

    market = MarketInfo(
        slug=slug,
        title=_to_title(slug),
        window_start_unix=window_start,
        window_end_unix=window_end,
        spot_price=raw.get("spot_price"),
        barrier=raw.get("target_price") or raw.get("barrier"),
        direction=raw.get("direction"),
        ttm_days=raw.get("ttm_days"),
        ttm_seconds=(raw.get("ttm_days") or 0.0) * 86400.0 if raw.get("ttm_days") else None,
    )

    polymarket = PolymarketPrices(
        best_bid=raw.get("poly_best_bid"),
        best_ask=raw.get("poly_best_ask"),
        mid=raw.get("poly_mid"),
        prob_up=raw.get("poly_prob_up"),
        prob_down=raw.get("poly_prob_down"),
    )

    t = TimingInfo(
        calibration_s=timing.get("calibration_s"),
        surface_fit_s=timing.get("surface_fit_s"),
        mc_s=timing.get("mc_s"),
        bl_s=timing.get("bl_s"),
        surface_bl_s=timing.get("surface_bl_s"),
        used_gap_s=timing.get("used_gap_s"),
        used_source=timing.get("used_source"),
    )

    age = None
    if path_mtime is not None:
        age = max(0.0, time.time() - path_mtime)

    return TerminalSnapshot(
        timestamp=raw.get("timestamp"),
        market=market,
        probabilities=probs,
        polymarket=polymarket,
        timing=t,
        age_seconds=age,
    )


def _snapshot_epoch(snap: TerminalSnapshot, fallback_mtime: Optional[float]) -> Optional[float]:
    if snap.timestamp:
        text = snap.timestamp.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            pass
    return fallback_mtime


def _observed_gap_s(
    prev_snap: Optional[TerminalSnapshot],
    snap: TerminalSnapshot,
    prev_mtime: Optional[float],
    mtime: float,
) -> Optional[float]:
    if prev_snap is None:
        return None
    prev_epoch = _snapshot_epoch(prev_snap, prev_mtime)
    cur_epoch = _snapshot_epoch(snap, mtime)
    if prev_epoch is not None and cur_epoch is not None:
        gap = cur_epoch - prev_epoch
        if gap > 0:
            return gap
    if prev_mtime is not None:
        gap = mtime - prev_mtime
        if gap > 0:
            return gap
    return None


def _merge_timing(
    prev: Optional[TimingInfo],
    incoming: TimingInfo,
    observed_gap_s: Optional[float] = None,
) -> TimingInfo:
    if prev is None:
        if incoming.used_gap_s is None and observed_gap_s is not None:
            incoming.used_gap_s = observed_gap_s
        return incoming
    return TimingInfo(
        calibration_s=incoming.calibration_s,
        surface_fit_s=incoming.surface_fit_s,
        mc_s=incoming.mc_s,
        bl_s=incoming.bl_s,
        surface_bl_s=incoming.surface_bl_s,
        # Source/cadence fields describe this specific timing payload. Do not
        # carry them forward, or the UI can show stale "remote" after switching
        # the live trader back to local calibration.
        used_gap_s=incoming.used_gap_s if incoming.used_gap_s is not None else observed_gap_s,
        used_source=incoming.used_source,
    )


class TerminalReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._last_mtime: Optional[float] = None
        self._last: Optional[TerminalSnapshot] = None
        # Per-market model probability history (reset when slug changes)
        self._model_up: Deque[tuple[str, float]] = deque(maxlen=MAX_MODEL_POINTS)
        self._model_down: Deque[tuple[str, float]] = deque(maxlen=MAX_MODEL_POINTS)
        self._cur_slug: Optional[str] = None

    def read_if_changed(self) -> Optional[TerminalSnapshot]:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        if self._last_mtime is not None and st.st_mtime == self._last_mtime:
            # still refresh age
            if self._last is not None:
                self._last.age_seconds = max(0.0, time.time() - st.st_mtime)
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("terminal read failed: %s", e)
            return None
        snap = parse_terminal(raw, st.st_mtime)
        prev_snap = None
        prev_timing = None
        if self._last is not None and self._last.market.slug == snap.market.slug:
            prev_snap = self._last
            prev_timing = self._last.timing
        snap.timing = _merge_timing(
            prev_timing,
            snap.timing,
            _observed_gap_s(prev_snap, snap, self._last_mtime, st.st_mtime),
        )
        self._last_mtime = st.st_mtime
        self._last = snap
        # Record model probabilities for the current market (use avg = the one the bot uses).
        probs = snap.probabilities
        up = (
            probs.avg_above
            if probs.avg_above is not None
            else probs.mc_above
            if probs.mc_above is not None
            else probs.ssvi_surface_above
        )
        down = (
            probs.avg_below
            if probs.avg_below is not None
            else probs.mc_below
            if probs.mc_below is not None
            else probs.ssvi_surface_below
        )
        if up is not None or down is not None:
            ts = snap.timestamp or datetime.now(timezone.utc).isoformat()
            if up is not None:
                self._model_up.append((ts, float(up)))
            if down is not None:
                self._model_down.append((ts, float(down)))
        return snap

    def reset_history_if_new_slug(self, slug: Optional[str]) -> None:
        if slug and slug != self._cur_slug:
            self._cur_slug = slug
            self._model_up.clear()
            self._model_down.clear()

    def model_series(self, side: str) -> list[dict]:
        dq = self._model_up if side == "UP" else self._model_down
        return [{"t": t, "v": v} for (t, v) in dq]

    @property
    def latest(self) -> Optional[TerminalSnapshot]:
        # Ensure age is fresh
        if self._last is not None and self._last_mtime is not None:
            self._last.age_seconds = max(0.0, time.time() - self._last_mtime)
        return self._last


async def run_terminal_loop(reader: "TerminalReader", stop: asyncio.Event) -> None:
    while not stop.is_set():
        snap = reader.read_if_changed()
        if snap is not None:
            await bus.publish("terminal.update", snap.model_dump())
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_seconds)
        except asyncio.TimeoutError:
            pass
