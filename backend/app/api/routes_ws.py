from __future__ import annotations

import asyncio
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

QUEUE_LIMIT = 256
CRITICAL_TOPICS = {"bootstrap", "instance.update", "trade.append"}
DROPPABLE_TOPICS = {
    "terminal.update",
    "orderbook.update",
    "leaderboard.update",
    "liveness.update",
    "liveness.tick",
    "edge.update",
    "calibration.start",
    "calibration.end",
}


class ConnContext:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.instance_id: int = settings.default_instance_id
        self.closed = False
        self._queue: list[tuple[str, dict]] = []
        self._queue_event = asyncio.Event()
        self._queue_lock = asyncio.Lock()

    async def send_now(self, topic: str, data: dict) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_json(envelope(topic, data))
        except Exception:  # noqa: BLE001
            self.closed = True

    def _drop_oldest_droppable(self) -> bool:
        for idx, (topic, _) in enumerate(self._queue):
            if topic in DROPPABLE_TOPICS:
                del self._queue[idx]
                return True
        return False

    async def enqueue(self, topic: str, data: dict) -> None:
        if self.closed:
            return
        async with self._queue_lock:
            if len(self._queue) >= QUEUE_LIMIT:
                if topic in CRITICAL_TOPICS:
                    self._drop_oldest_droppable()
                elif not self._drop_oldest_droppable():
                    return
            self._queue.append((topic, data))
            self._queue_event.set()

    async def clear_queue(self) -> None:
        async with self._queue_lock:
            self._queue.clear()
            self._queue_event.clear()

    async def sender_loop(self) -> None:
        while not self.closed:
            await self._queue_event.wait()
            while not self.closed:
                async with self._queue_lock:
                    if not self._queue:
                        self._queue_event.clear()
                        break
                    topic, data = self._queue.pop(0)
                await self.send_now(topic, data)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    ctx = ConnContext(ws)
    hub = get_hub()
    sender_task = asyncio.create_task(ctx.sender_loop())

    async def send_instance_snapshot() -> None:
        instance, position, equity, equity_series, today_summary = hub.instance_snapshot(ctx.instance_id)
        await ctx.enqueue(
            "instance.update",
            {
                "instance": instance.model_dump() if instance else None,
                "position": position.model_dump(),
                "equity": equity,
                "equity_series": equity_series,
                "today_summary": today_summary.model_dump(),
            },
        )

    try:
        payload = hub.build_bootstrap(ctx.instance_id).model_dump()
        await ctx.send_now("bootstrap", payload)
    except Exception:
        log.exception("initial bootstrap failed")

    async def send_edge_update() -> None:
        edge_up, edge_down = hub.current_edges(ctx.instance_id)
        await ctx.enqueue(
            "edge.update",
            {
                "edge_up": edge_up.model_dump() if edge_up else None,
                "edge_down": edge_down.model_dump() if edge_down else None,
            },
        )

    async def on_event(topic: str, data) -> None:
        if ctx.closed:
            return
        if topic == "trade.append":
            if data.get("instance_id") != ctx.instance_id:
                return
            await ctx.enqueue(topic, data)
            await send_instance_snapshot()
            await send_edge_update()
            return
        if topic == "state.update":
            await send_instance_snapshot()
            return
        if topic == "leaderboard.update":
            await ctx.enqueue(topic, data)
            await send_instance_snapshot()
            await send_edge_update()
            return
        await ctx.enqueue(topic, data)
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
                await ctx.clear_queue()
                payload = hub.build_bootstrap(ctx.instance_id).model_dump()
                await ctx.send_now("bootstrap", payload)
            elif obj.get("action") == "ping":
                await ctx.send_now("pong", {"t": time.time()})
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws error")
    finally:
        ctx.closed = True
        unsub()
        ctx._queue_event.set()
        sender_task.cancel()
        try:
            await sender_task
        except (asyncio.CancelledError, Exception):
            pass
