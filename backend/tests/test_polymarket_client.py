from __future__ import annotations

import httpx
import pytest

from app.collector.polymarket_client import (
    BREAKER_THRESHOLD,
    PolymarketClient,
    _EndpointUnavailable,
)


def _client() -> PolymarketClient:
    return PolymarketClient(slug_fn=lambda: None)


def _make_handler(seq):
    """Return an httpx MockTransport handler that yields response codes from seq in order."""
    it = iter(seq)

    def handler(request: httpx.Request) -> httpx.Response:
        code = next(it)
        if isinstance(code, Exception):
            raise code
        return httpx.Response(code, json={"ok": code == 200})

    return handler


@pytest.mark.asyncio
async def test_retry_recovers_after_429s():
    pc = _client()
    transport = httpx.MockTransport(_make_handler([429, 429, 200]))
    pc._client = httpx.AsyncClient(transport=transport)
    r = await pc._request_with_retry("ep", "https://x/y", base_delay=0.0)
    assert r.status_code == 200
    assert pc._endpoint_failures["ep"] == 0
    assert "ep" not in pc._endpoint_degraded
    await pc.close()


@pytest.mark.asyncio
async def test_retry_exhausts_then_marks_failure():
    pc = _client()
    transport = httpx.MockTransport(_make_handler([500, 500, 500]))
    pc._client = httpx.AsyncClient(transport=transport)
    with pytest.raises(httpx.HTTPStatusError):
        await pc._request_with_retry("ep", "https://x/y", base_delay=0.0)
    assert pc._endpoint_failures["ep"] == 1
    await pc.close()


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_threshold():
    pc = _client()
    transport = httpx.MockTransport(_make_handler([500] * 3 * BREAKER_THRESHOLD))
    pc._client = httpx.AsyncClient(transport=transport)
    for _ in range(BREAKER_THRESHOLD):
        with pytest.raises(httpx.HTTPStatusError):
            await pc._request_with_retry("ep", "https://x/y", base_delay=0.0)
    assert "ep" in pc._endpoint_degraded
    # Next call short-circuits without hitting the transport.
    with pytest.raises(_EndpointUnavailable):
        await pc._request_with_retry("ep", "https://x/y", base_delay=0.0)
    await pc.close()


@pytest.mark.asyncio
async def test_recovery_clears_degraded_state():
    pc = _client()
    pc._endpoint_failures["ep"] = BREAKER_THRESHOLD
    pc._endpoint_degraded.add("ep")
    transport = httpx.MockTransport(_make_handler([200]))
    pc._client = httpx.AsyncClient(transport=transport)
    # Simulate the per-poll-cycle reset that poll() does.
    pc._endpoint_degraded.clear()
    r = await pc._request_with_retry("ep", "https://x/y", base_delay=0.0)
    assert r.status_code == 200
    assert pc._endpoint_failures["ep"] == 0
    assert "ep" not in pc._endpoint_degraded
    await pc.close()


@pytest.mark.asyncio
async def test_4xx_non_429_does_not_retry():
    pc = _client()
    transport = httpx.MockTransport(_make_handler([404]))
    pc._client = httpx.AsyncClient(transport=transport)
    with pytest.raises(httpx.HTTPStatusError):
        await pc._request_with_retry("ep", "https://x/y", base_delay=0.0)
    await pc.close()
