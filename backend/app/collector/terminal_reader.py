from __future__ import annotations

import asyncio
import json
import logging
import subprocess
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


def _is_vps_live() -> bool:
    return _vps_profile_name_if_live() is not None


def _vps_profile_name_if_live() -> Optional[str]:
    if settings.mode != "live":
        return None
    try:
        location = settings.live_location_path().read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    if location == "vps":
        return ""
    if location.startswith("vps:"):
        return location.split(":", 1)[1].strip()
    return None


def _looks_like_local_grid_payload(raw: dict) -> bool:
    timing = raw.get("timing") or {}
    return timing.get("used_source") is None and timing.get("used_gap_s") is None


def _is_configured_terminal_path(path: Path) -> bool:
    try:
        return path.resolve() == settings.terminal_path().resolve()
    except OSError:
        return False


class TerminalReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._last_mtime: Optional[float] = None
        self._last_observed_mtime: Optional[float] = None
        self._last: Optional[TerminalSnapshot] = None
        self._last_remote_attempt = 0.0
        self._remote_poll_interval_s = 5.0
        # Per-market model probability history (reset when slug changes)
        self._model_up: Deque[tuple[str, float]] = deque(maxlen=MAX_MODEL_POINTS)
        self._model_down: Deque[tuple[str, float]] = deque(maxlen=MAX_MODEL_POINTS)
        self._cur_slug: Optional[str] = None

    def _read_remote_vps_terminal(self, *, force: bool = False) -> Optional[dict]:
        now = time.monotonic()
        if not force and now - self._last_remote_attempt < self._remote_poll_interval_s:
            return None
        self._last_remote_attempt = now

        profile_name = _vps_profile_name_if_live()
        if profile_name is None:
            return None
        profile = settings.vps_profile(profile_name)
        if profile is None or not profile.ssh_key.exists():
            return None

        remote_path = f"{profile.dir}/results/terminal_data.json"
        if "'" in remote_path:
            return None
        cmd = [
            "ssh",
            "-i",
            str(profile.ssh_key),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=6",
            "-o",
            "BatchMode=yes",
            f"{profile.user}@{profile.host}",
            f"cat '{remote_path}'",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.debug("remote VPS terminal read failed: %s", exc)
            return None
        if proc.returncode != 0:
            log.debug("remote VPS terminal read rc=%s err=%s", proc.returncode, proc.stderr[:200])
            return None
        try:
            raw = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            log.debug("remote VPS terminal parse failed: %s", exc)
            return None
        return raw if isinstance(raw, dict) else None

    def _record_snapshot(self, raw: dict, path_mtime: float) -> Optional[TerminalSnapshot]:
        snap = parse_terminal(raw, path_mtime)
        if self._last is not None and self._last.timestamp == snap.timestamp:
            if self._last_observed_mtime is not None:
                self._last.age_seconds = max(0.0, time.time() - self._last_observed_mtime)
            return None
        prev_snap = None
        prev_timing = None
        if self._last is not None and self._last.market.slug == snap.market.slug:
            prev_snap = self._last
            prev_timing = self._last.timing
        snap.timing = _merge_timing(
            prev_timing,
            snap.timing,
            _observed_gap_s(prev_snap, snap, self._last_observed_mtime, path_mtime),
        )
        self._last_observed_mtime = path_mtime
        self._last = snap
        self._record_model_probabilities(snap)
        return snap

    def _record_model_probabilities(self, snap: TerminalSnapshot) -> None:
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

    def read_if_changed(self) -> Optional[TerminalSnapshot]:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        vps_live = _is_configured_terminal_path(self.path) and _is_vps_live()
        if self._last_mtime is not None and st.st_mtime == self._last_mtime:
            if vps_live:
                raw = self._read_remote_vps_terminal()
                if raw is not None:
                    return self._record_snapshot(raw, time.time())
            # still refresh age
            if self._last is not None:
                observed_mtime = self._last_observed_mtime or st.st_mtime
                self._last.age_seconds = max(0.0, time.time() - observed_mtime)
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("terminal read failed: %s", e)
            return None
        if vps_live and _looks_like_local_grid_payload(raw):
            remote_raw = self._read_remote_vps_terminal(force=True)
            if remote_raw is None:
                self._last_mtime = st.st_mtime
                log.debug("ignoring non-hybrid terminal_data.json while VPS live is active")
                return None
            raw = remote_raw
            path_mtime = time.time()
        else:
            path_mtime = st.st_mtime

        self._last_mtime = st.st_mtime
        return self._record_snapshot(raw, path_mtime)

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
