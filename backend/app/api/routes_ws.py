from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
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

    async def send_instance_snapshot() -> None:
        instance, position, equity, equity_series = hub.instance_snapshot(ctx.instance_id)
        await ctx.send(
            "instance.update",
            {
                "instance": instance.model_dump() if instance else None,
                "position": position.model_dump(),
                "equity": equity,
                "equity_series": equity_series,
            },
        )

    try:
        payload = hub.build_bootstrap(ctx.instance_id).model_dump()
        await ctx.send("bootstrap", payload)
    except Exception:
        log.exception("initial bootstrap failed")

    async def send_edge_update() -> None:
        edge_up, edge_down = hub.current_edges(ctx.instance_id)
        await ctx.send(
            "edge.update",
            {
                "edge_up": edge_up.model_dump() if edge_up else None,
                "edge_down": edge_down.model_dump() if edge_down else None,
            },
        )

    async def on_event(topic: str, data) -> None:
        if ctx.closed:
            return
        if topic == "trade.append" and data.get("instance_id") != ctx.instance_id:
            return
        if topic == "state.update":
            await send_instance_snapshot()
            return
        if topic == "leaderboard.update":
            await ctx.send(topic, data)
            await send_instance_snapshot()
            await send_edge_update()
            return
        await ctx.send(topic, data)
        if topic in ("terminal.update", "orderbook.update"):
            await send_edge_update()

    unsub = bus.subscribe("*", on_event)

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
