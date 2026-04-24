from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes_http import router as http_router
from .api.routes_ws import router as ws_router
from .api.state_hub import get_hub
from .collector.calibration_watcher import run_calibration_loop
from .collector.docker_log_tail import run_docker_log_loop
from .collector.leaderboard_reader import run_leaderboard_loop
from .collector.liveness import run_liveness_loop
from .collector.location_probe import run_location_probe_loop
from .collector.orderbook_tail import run_orderbook_loop
from .collector.polymarket_client import run_polymarket_loop
from .collector.state_reader import run_state_loop
from .collector.terminal_reader import run_terminal_loop
from .collector.trades_tail import run_trades_loop
from .config import settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    hub = get_hub()

    # Prime readers once
    hub.state.read_if_changed()
    hub.leaderboard.read_if_changed()
    hub.terminal.read_if_changed()
    hub.orderbook.seed()  # populate UP/DOWN price history
    hub.trades.seed()  # populate per-instance buffers from existing trades.csv
    try:
        await hub.polymarket.poll()
    except Exception:
        log.exception("polymarket seed failed")
    # In dry-run mode, seed model probabilities from the local grid logs.
    # In live mode, the model chart must use the active live trader's
    # terminal_data only; the local grid can still be running and would pollute
    # the live chart with unrelated model ticks.
    if settings.mode == "dry_run":
        try:
            await hub.docker_log.poll(since_seconds=1200)
        except Exception:
            log.exception("docker log seed failed")

    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(run_liveness_loop(stop)),
        asyncio.create_task(run_location_probe_loop(stop)),
        asyncio.create_task(run_terminal_loop(hub.terminal, stop)),
        asyncio.create_task(run_state_loop(hub.state, stop)),
        asyncio.create_task(run_trades_loop(hub.trades, stop)),
        asyncio.create_task(run_leaderboard_loop(hub.leaderboard, stop)),
        asyncio.create_task(run_orderbook_loop(hub.orderbook, stop)),
        *(
            [asyncio.create_task(run_docker_log_loop(hub.docker_log, stop))]
            if settings.mode == "dry_run"
            else []
        ),
        asyncio.create_task(run_polymarket_loop(hub.polymarket, stop)),
        asyncio.create_task(run_calibration_loop(hub.calibration, stop)),
    ]
    log.info("dashboard backend started: mode=%s results=%s", settings.mode, settings.resolved_results_dir)
    try:
        yield
    finally:
        stop.set()
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


def create_app() -> FastAPI:
    app = FastAPI(title="Polymarket Streaming Dashboard", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(http_router)
    app.include_router(ws_router)

    # Optional: serve frontend static build when it exists
    static_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
    return app


app = create_app()
