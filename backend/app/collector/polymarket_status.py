"""Watches Polymarket's Instatus status page for ongoing maintenance / outages.

Polls https://status.polymarket.com/summary.json (the same JSON feed the public
status page consumes) on a slow cadence. When the page reports a non-UP state
or an active maintenance, the dashboard surfaces a banner and stops treating
the empty CLOB books as real prices.

Why we need this: during platform upgrades the CLOB `/book` returns empty
bids/asks and `/prices-history` returns synthetic 0.5 placeholders. The chart
without context looks like a bug; with the banner it reads as "Polymarket is
down for maintenance".
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..config import settings
from ..events.bus import bus
from ..models import PolymarketStatus

log = logging.getLogger(__name__)

STATUS_URL = "https://status.polymarket.com/summary.json"


class PolymarketStatusWatcher:
    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._status = PolymarketStatus()
        self._consecutive_failures = 0

    @property
    def status(self) -> PolymarketStatus:
        return self._status

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.polymarket_request_timeout_seconds,
                headers={"User-Agent": "polymarket-streaming-dashboard/0.1"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None

    async def poll(self) -> bool:
        """Fetch the status summary. Returns True if the published status changed."""
        try:
            client = await self._ensure_client()
            r = await client.get(STATUS_URL)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            self._consecutive_failures += 1
            if self._consecutive_failures <= 2:
                log.warning("polymarket status fetch failed: %s", e)
            # Keep last known status; don't flip the banner on a transient miss.
            return False
        self._consecutive_failures = 0

        page = data.get("page") if isinstance(data, dict) else None
        page_status = (page or {}).get("status") if isinstance(page, dict) else None
        if not isinstance(page_status, str):
            page_status = "UP"

        active_list = data.get("activeMaintenances") if isinstance(data, dict) else None
        active_name: Optional[str] = None
        if isinstance(active_list, list):
            for item in active_list:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if isinstance(name, str) and name:
                    active_name = name
                    break

        is_op = page_status.upper() == "UP" and active_name is None

        new_status = PolymarketStatus(
            status=page_status,
            is_operational=is_op,
            active_maintenance=active_name,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        changed = (
            new_status.status != self._status.status
            or new_status.is_operational != self._status.is_operational
            or new_status.active_maintenance != self._status.active_maintenance
        )
        self._status = new_status
        if changed:
            log.info(
                "polymarket status: %s operational=%s maintenance=%s",
                new_status.status,
                new_status.is_operational,
                new_status.active_maintenance,
            )
        return changed


async def run_polymarket_status_loop(
    watcher: PolymarketStatusWatcher,
    stop: asyncio.Event,
) -> None:
    try:
        while not stop.is_set():
            try:
                if await watcher.poll():
                    await bus.publish(
                        "polymarket_status.update",
                        watcher.status.model_dump(),
                    )
            except Exception:  # noqa: BLE001
                log.exception("polymarket status poll error")
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=settings.polymarket_status_poll_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass
    finally:
        await watcher.close()
