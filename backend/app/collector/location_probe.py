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


@dataclass
class CpuResult:
    pct: Optional[float] = None
    measured_at: Optional[float] = None

    def age_s(self) -> Optional[float]:
        if self.measured_at is None:
            return None
        return max(0.0, time.time() - self.measured_at)


class LocationProbe:
    """Measures Polymarket CLOB latency from the active trader side."""

    def __init__(self) -> None:
        self._local = PingResult()
        self._vps = PingResult()
        self._vps_cpu = CpuResult()

    def read_location(self) -> str:
        """Returns "local" | "vps" | "stopped" | "unknown".""" 
        location, _ = self._read_location_marker()
        return location

    def _read_location_marker(self) -> tuple[str, Optional[str]]:
        """Returns (location_kind, profile_name).

        Supported marker values:
        - local
        - stopped
        - vps
        - vps:<profile_name>
        """
        p = settings.live_location_path()
        try:
            val = p.read_text(encoding="utf-8").strip()
        except OSError:
            return "unknown", None
        if val in ("local", "stopped"):
            return val, None
        if val == "vps":
            return "vps", None
        if val.startswith("vps:"):
            profile = val.split(":", 1)[1].strip() or None
            return "vps", profile
        return "unknown", None

    def _read_trader_measured(self) -> Optional[PingResult]:
        """Read the rolling median the live trader writes to .clob_latency_ms.

        Format: "<median_ms> <samples> <epoch>\n" — atomically written by
        order_book.py after every CLOB request, synced from VPS to local by
        vps_state_sync when live is on VPS. When present and recent, this
        is the most faithful latency number (warm-connection median of the
        trader's last 12 CLOB calls).
        """
        path = settings.resolved_results_dir / ".clob_latency_ms"
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        parts = content.split()
        if not parts:
            return None
        try:
            ms = float(parts[0])
            epoch = int(parts[2]) if len(parts) > 2 else None
        except (ValueError, IndexError):
            return None
        return PingResult(ms=ms, measured_at=float(epoch) if epoch else None)

    def active_ping(self) -> tuple[Optional[float], Optional[float], Optional[str]]:
        """Returns (ping_ms, age_s, label) for the ACTIVE execution side.

        Priority: trader-measured warm-connection median > probe measurement.
        """
        loc, profile_name = self._read_location_marker()
        profile = settings.vps_profile(profile_name) if loc == "vps" else None
        label = profile.label if profile is not None else (settings.vps_label if loc == "vps" else "local")

        trader = self._read_trader_measured()
        if trader is not None and trader.ms is not None:
            age = trader.age_s()
            # Prefer the trader-written rolling median whenever it is not too
            # old. A longer grace window avoids the UI dropping to blank when
            # the VPS-side probe lags briefly or the sync loop hiccups.
            if age is None or age <= 900:
                return trader.ms, age, label

        if loc == "vps":
            return self._vps.ms, self._vps.age_s(), label
        return self._local.ms, self._local.age_s(), label

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
        """SSH to the VPS; one call gets both curl time_total AND a CPU sample.

        The remote script reads /proc/stat twice with 500 ms between samples,
        computes cpu% from the delta, and runs a curl probe in between (so
        the two measurements share one SSH round-trip). Output format:
            <time_total_seconds>
            <cpu_pct>
        """
        _, profile_name = self._read_location_marker()
        profile = settings.vps_profile(profile_name)
        if profile is None:
            return
        key = profile.ssh_key
        if not key.exists():
            log.debug("vps ssh key not found: %s", key)
            return
        remote_cmd = (
            "python3 - <<'PY'\n"
            "import subprocess, time\n"
            "def cpu():\n"
            "    with open('/proc/stat', 'r', encoding='utf-8') as f:\n"
            "        parts = f.readline().split()\n"
            "    values = [int(v) for v in parts[1:]]\n"
            "    idle = values[3] + (values[4] if len(values) > 4 else 0)\n"
            "    total = sum(values)\n"
            "    return idle, total\n"
            "ib, tb = cpu()\n"
            f"out = subprocess.check_output(['curl', '-o', '/dev/null', '-s', '-w', '%{{time_total}}\\\\n', '{settings.polymarket_clob_url}/markets?limit=1'], text=True).strip()\n"
            "print(out)\n"
            "time.sleep(0.5)\n"
            "ia, ta = cpu()\n"
            "dt = ta - tb\n"
            "if dt > 0:\n"
            "    print(f'{100 * (1 - (ia - ib) / dt):.1f}')\n"
            "else:\n"
            "    print('')\n"
            "PY"
        )
        cmd = [
            "ssh",
            "-i", str(key),
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=8",
            "-o", "BatchMode=yes",
            f"{profile.user}@{profile.host}",
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
                log.debug("vps probe timed out")
                return
            if proc.returncode != 0:
                log.debug("vps probe rc=%s err=%s", proc.returncode, stderr.decode()[:200])
                return
            lines = stdout.decode().strip().splitlines()
            now = time.time()
            if len(lines) >= 1:
                try:
                    self._vps = PingResult(ms=float(lines[0]) * 1000.0, measured_at=now)
                except ValueError:
                    log.debug("vps ping parse error: %r", lines[0])
            if len(lines) >= 2 and lines[1]:
                try:
                    pct = float(lines[1])
                    self._vps_cpu = CpuResult(
                        pct=max(0.0, min(100.0, pct)), measured_at=now
                    )
                except ValueError:
                    log.debug("vps cpu parse error: %r", lines[1])
        except Exception as exc:  # noqa: BLE001
            log.debug("vps probe failed: %s", exc)

    def vps_cpu(self) -> Optional[float]:
        """Last-measured VPS CPU%, or None if unknown/stale (> 2 min)."""
        if self._vps_cpu.pct is None:
            return None
        age = self._vps_cpu.age_s()
        if age is not None and age > 120:
            return None
        return self._vps_cpu.pct


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
