from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from .state_hub import get_hub

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    hub = get_hub()
    from ..collector.liveness import current_liveness
    info = current_liveness()
    return {
        "ok": True,
        "mode": settings.mode,
        "results_dir": str(settings.resolved_results_dir),
        "results_dir_ok": settings.resolved_results_dir.exists(),
        "bot_live": info.bot_live,
        "lock_exists": info.lock_exists,
        "last_terminal_age_s": info.terminal_age_s,
    }


@router.get("/bootstrap")
async def bootstrap(instance_id: int = Query(default=None)) -> dict:
    iid = instance_id if instance_id is not None else settings.default_instance_id
    payload = get_hub().build_bootstrap(iid)
    return payload.model_dump()


@router.get("/instances")
async def instances() -> list[dict]:
    hub = get_hub()
    hub.leaderboard.read_if_changed()
    return [r.model_dump() for r in hub.leaderboard.rows]


@router.get("/instance/{instance_id}")
async def instance_detail(instance_id: int) -> dict:
    return get_hub().build_bootstrap(instance_id).model_dump()


@router.get("/config")
async def merged_config() -> dict:
    out: dict = {"mode": settings.mode}
    for key, path in [("grid", settings.grid_config_path()), ("live", settings.live_config_path())]:
        try:
            out[key] = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            out[key] = None
    return out
