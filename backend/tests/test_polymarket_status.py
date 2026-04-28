"""Verify status watcher recovers from maintenance → operational."""
from __future__ import annotations

import asyncio
import pytest

from app.collector.polymarket_status import PolymarketStatusWatcher


class _FakeResp:
    def __init__(self, body: dict) -> None:
        self._body = body

    def raise_for_status(self) -> None:  # pragma: no cover
        pass

    def json(self) -> dict:
        return self._body


class _FakeClient:
    """Yields a queue of responses so a single watcher can see status flip."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)

    async def get(self, url: str) -> _FakeResp:
        return _FakeResp(self._responses.pop(0))

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_watcher_flips_back_to_operational_after_maintenance() -> None:
    """Watcher must not get stuck in DOWN state when Polymarket recovers."""
    w = PolymarketStatusWatcher()
    w._client = _FakeClient([
        # Tick 1: maintenance starts.
        {"page": {"status": "UNDERMAINTENANCE"}, "activeMaintenances": [
            {"id": "x", "name": "CLOB v2 exchange upgrade", "status": "INPROGRESS"},
        ]},
        # Tick 2: maintenance still ongoing, but no named entry yet.
        {"page": {"status": "UNDERMAINTENANCE"}, "activeMaintenances": None},
        # Tick 3: Polymarket comes back online.
        {"page": {"status": "UP"}, "activeMaintenances": []},
        # Tick 4: still up — should remain operational.
        {"page": {"status": "UP"}},
    ])

    changed1 = await w.poll()
    assert changed1 is True
    assert w.status.is_operational is False
    assert w.status.status == "UNDERMAINTENANCE"
    assert w.status.active_maintenance == "CLOB v2 exchange upgrade"

    changed2 = await w.poll()
    assert changed2 is True  # active_maintenance went None → field changed
    assert w.status.is_operational is False

    changed3 = await w.poll()
    assert changed3 is True
    assert w.status.is_operational is True
    assert w.status.status == "UP"
    assert w.status.active_maintenance is None

    changed4 = await w.poll()
    assert changed4 is False  # idempotent — same UP state
    assert w.status.is_operational is True


@pytest.mark.asyncio
async def test_watcher_keeps_last_status_on_fetch_failure() -> None:
    """Transient network failure must not flip the banner off."""
    import httpx

    class _FailClient:
        def __init__(self) -> None:
            self.calls = 0

        async def get(self, url: str):
            self.calls += 1
            raise httpx.ConnectError("network down")

        async def aclose(self) -> None:
            pass

    w = PolymarketStatusWatcher()
    # Seed with a "down" status.
    w._client = _FakeClient([
        {"page": {"status": "UNDERMAINTENANCE"}, "activeMaintenances": []},
    ])
    await w.poll()
    assert w.status.is_operational is False

    # Now simulate fetch failures.
    w._client = _FailClient()
    changed = await w.poll()
    assert changed is False
    # Status preserved despite failure.
    assert w.status.is_operational is False
    assert w.status.status == "UNDERMAINTENANCE"
