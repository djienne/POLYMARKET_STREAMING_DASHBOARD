from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import re
import time as _time

from ..config import settings
from ..derive.window import compute_window
from ..envelope import envelope
from ..events.bus import bus
from .state_hub import get_hub

log = logging.getLogger(__name__)
router = APIRouter()


class ConnContext:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.instance_id: int = settings.default_instance_id
        self.closed = False

    async def send(self, topic: str, data: dict) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_json(envelope(topic, data))
        except Exception:  # noqa: BLE001
            self.closed = True


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    ctx = ConnContext(ws)
    hub = get_hub()

    # Send initial bootstrap
    try:
        payload = hub.build_bootstrap(ctx.instance_id).model_dump()
        await ctx.send("bootstrap", payload)
    except Exception:
        log.exception("initial bootstrap failed")

    async def on_event(topic: str, data) -> None:
        if ctx.closed:
            return
        # Scope state/trade to the subscribed instance
        if topic == "trade.append":
            if data.get("instance_id") != ctx.instance_id:
                return
        if topic == "state.update":
            # Re-send scoped instance snapshot
            instance = hub.state.instance(ctx.instance_id)
            lb_row = hub.leaderboard.row(ctx.instance_id)
            if instance and lb_row:
                instance.rank = lb_row.rank
                instance.params = lb_row.params
            position = hub.state.position(ctx.instance_id)
            from ..derive.equity import equity_curve
            pnls = hub.state.trade_pnls(ctx.instance_id)
            equity = equity_curve(pnls, 1000.0)
            await ctx.send("instance.update", {
                "instance": instance.model_dump() if instance else None,
                "position": position.model_dump(),
                "equity": equity,
            })
            return
        await ctx.send(topic, data)

    unsub = bus.subscribe("*", on_event)

    stop = asyncio.Event()

    async def window_ticker() -> None:
        while not stop.is_set():
            snap = hub.terminal.latest
            slug = snap.market.slug if (snap and snap.market) else None
            # Fallback chain: any open position's market_id → current quarter-hour boundary
            if not slug:
                for inst in (hub.state.raw.get("instances") or {}).values():
                    pos = inst.get("position")
                    if pos and pos.get("market_id"):
                        slug = pos["market_id"]
                        break
            now = int(_time.time())
            m = re.search(r"btc-updown-15m-(\d+)", slug or "")
            if not slug or not m or (int(m.group(1)) + 900) < now:
                slug = f"btc-updown-15m-{(now // 900) * 900}"
            win = compute_window(slug)
            await ctx.send("window.tick", win.model_dump())
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    ticker_task = asyncio.create_task(window_ticker())

    try:
        while True:
            msg = await ws.receive_text()
            try:
                obj = json.loads(msg)
            except json.JSONDecodeError:
                continue
            if obj.get("action") == "select_instance":
                try:
                    new_id = int(obj.get("instance_id"))
                except (TypeError, ValueError):
                    continue
                ctx.instance_id = new_id
                payload = hub.build_bootstrap(ctx.instance_id).model_dump()
                await ctx.send("bootstrap", payload)
            elif obj.get("action") == "ping":
                await ctx.send("pong", {"t": time.time()})
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws error")
    finally:
        ctx.closed = True
        unsub()
        stop.set()
        ticker_task.cancel()
        try:
            await ticker_task
        except (asyncio.CancelledError, Exception):
            pass
