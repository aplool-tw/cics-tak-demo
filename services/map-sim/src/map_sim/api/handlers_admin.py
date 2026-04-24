"""Admin / health / debug handlers (contracts §3.3, §4)."""
from __future__ import annotations

from datetime import datetime, timezone

from aiohttp import web

from ..logging import get_logger
from ..models.drone_object import serialize

log = get_logger("map_sim.admin")


async def health(request: web.Request) -> web.Response:
    registry = request.app["registry"]
    started_at: datetime = request.app["started_at"]
    now = datetime.now(timezone.utc)
    registered = await registry.count()
    uptime_s = round((now - started_at).total_seconds(), 1)
    if uptime_s < 0:  # safety against clock skew in tests
        uptime_s = 0.0
    log.debug("health.ok", registered_objects=registered, uptime_s=uptime_s)
    return web.json_response(
        {"status": "ok", "registered_objects": registered, "uptime_s": uptime_s},
        status=200,
    )


async def objects_all(request: web.Request) -> web.Response:
    registry = request.app["registry"]
    all_objs = await registry.get_all()
    now = datetime.now(timezone.utc)
    ttl_warn_s = registry.ttl_warn_s
    lost_flags = [obj.is_lost(ttl_warn_s, now) for obj in all_objs]
    active = sum(1 for f in lost_flags if not f)
    lost = sum(1 for f in lost_flags if f)
    total = len(all_objs)
    objects = [serialize(obj, ttl_warn_s, now) for obj in all_objs]
    return web.json_response(
        {"total": total, "active": active, "lost": lost, "objects": objects},
        status=200,
    )


async def delete_drone(request: web.Request) -> web.Response:
    drone_id = request.match_info["drone_id"]
    registry = request.app["registry"]
    removed = await registry.remove(drone_id)
    status = "removed" if removed else "not_found"
    return web.json_response({"status": status, "drone_id": drone_id}, status=200)
