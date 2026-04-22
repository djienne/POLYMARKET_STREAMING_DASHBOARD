"""Polymarket latency probe for the current live-trader execution location.

Reads `results/.live_location` to learn whether the live trader is running
locally or on the VPS, then measures Polymarket CLOB latency from the ACTIVE
side:

- local  → httpx GET from the dashboard host (= the local trader host) to
  clob.polymarket.com and record the wall time.
- vps    → ssh to the VPS and run curl there so the measurement reflects
  what the VPS trader actually experiences. SSH handshake overhead is
  stripped — we only keep curl's `time_total`.

Falls back to "—" if the probe fails. Never leaks host addresses to callers;
only `location_label` (e.g. "VPS Tokyo") and a numeric ping_ms are exposed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings

log = logging.getLogger(__name__)


@dataclass
class PingResult:
    ms: Optional[float] = None
    measured_at: Optional[float] = None  # unix epoch seconds

    def age_s(self) -> Optional[float]:
        if self.measured_at is None:
            return None
        return max(0.0, time.time() - self.measured_at)


class LocationProbe:
    """Measures Polymarket CLOB latency from the active trader side."""

    def __init__(self) -> None:
        self._local = PingResult()
        self._vps = PingResult()

    def read_location(self) -> str:
        """Returns "local" | "vps" | "stopped" | "unknown"."""
        p = settings.live_location_path()
        try:
            val = p.read_text(encoding="utf-8").strip()
        except OSError:
            return "unknown"
        if val in ("local", "vps", "stopped"):
            return val
        return "unknown"

    def active_ping(self) -> tuple[Optional[float], Optional[float], Optional[str]]:
        """Returns (ping_ms, age_s, label) for the ACTIVE execution side."""
        loc = self.read_location()
        if loc == "vps":
            return self._vps.ms, self._vps.age_s(), settings.vps_label
        # local / stopped / unknown → show local measurement (still a useful
        # number — it's the dashboard host's view of Polymarket).
        return self._local.ms, self._local.age_s(), "local"

    async def measure_local(self) -> None:
        url = f"{settings.polymarket_clob_url}/markets?limit=1"
        try:
            t0 = time.perf_counter()
            async with httpx.AsyncClient(timeout=settings.polymarket_request_timeout_seconds) as client:
                resp = await client.get(url)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status_code == 200:
                self._local = PingResult(ms=elapsed_ms, measured_at=time.time())
        except Exception as exc:  # noqa: BLE001
            log.debug("local polymarket probe failed: %s", exc)

    async def measure_vps(self) -> None:
        """SSH to the VPS and ask curl to report its own `time_total`."""
        if not settings.vps_host:
            return
        key = settings.resolved_vps_ssh_key()
        if not key.exists():
            log.debug("vps ssh key not found: %s", key)
            return
        # `curl -w '%{time_total}\n' -o /dev/null -s` prints just the time.
        remote_cmd = (
            f"curl -o /dev/null -s -w '%{{time_total}}\\n' "
            f"'{settings.polymarket_clob_url}/markets?limit=1'"
        )
        cmd = [
            "ssh",
            "-i", str(key),
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=8",
            "-o", "BatchMode=yes",
            f"{settings.vps_user}@{settings.vps_host}",
            remote_cmd,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                log.debug("vps polymarket probe timed out")
                return
            if proc.returncode == 0 and stdout:
                val = stdout.decode().strip()
                try:
                    seconds = float(val)
                    self._vps = PingResult(ms=seconds * 1000.0, measured_at=time.time())
                except ValueError:
                    log.debug("vps probe parse error: %r", val)
        except Exception as exc:  # noqa: BLE001
            log.debug("vps polymarket probe failed: %s", exc)


# Single shared instance used by liveness collector.
probe = LocationProbe()


async def run_location_probe_loop(stop: asyncio.Event) -> None:
    """Measure both local and VPS (if configured) each cycle."""
    interval = settings.polymarket_probe_interval_seconds
    while not stop.is_set():
        try:
            await probe.measure_local()
            # Only probe VPS if we know live is there, to avoid unnecessary SSH.
            if probe.read_location() == "vps":
                await probe.measure_vps()
        except Exception:  # noqa: BLE001
            log.exception("location probe iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
