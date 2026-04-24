"""HTTP Status API (aiohttp.web, :7070). Contract: http-status-api.md."""

from __future__ import annotations

import time
from typing import Any, Callable

from aiohttp import web

from ..logging import get_logger
from ..models import DroneRegistry


def _err(reason: str = "not_found") -> web.Response:
    return web.json_response({"status": "error", "reason": reason}, status=404)


def build_app(
    *,
    registry: DroneRegistry,
    start_monotonic: float,
    get_map_sim_reachable: Callable[[], bool],
) -> web.Application:
    log = get_logger("sentrycs_sim.api")

    async def _detections(request: web.Request) -> web.Response:
        snap = registry.snapshot()
        payload = [r.model_dump() for r in snap]
        return web.json_response(payload)

    async def _detection_by_uid(request: web.Request) -> web.Response:
        uid = request.match_info["uid"]
        r = registry.get(uid)
        if r is None:
            return _err()
        return web.json_response(r.model_dump())

    async def _health(request: web.Request) -> web.Response:
        uptime = round(time.monotonic() - start_monotonic, 1)
        payload: dict[str, Any] = {
            "status": "ok",
            "uptime_s": uptime,
            "tracked_drones": len(registry.snapshot()),
            "map_sim_reachable": bool(get_map_sim_reachable()),
        }
        return web.json_response(payload)

    @web.middleware
    async def _access_log(request: web.Request, handler: Any) -> web.StreamResponse:
        t0 = time.monotonic()
        try:
            resp = await handler(request)
            status = resp.status
            return resp
        except web.HTTPException as exc:
            status = exc.status
            raise
        finally:
            latency_ms = round((time.monotonic() - t0) * 1000.0, 3)
            log.debug(
                "http_request",
                method=request.method,
                path=request.path,
                status=status,  # noqa: F821
                latency_ms=latency_ms,
            )

    app = web.Application(middlewares=[_access_log])
    app.router.add_get("/detections", _detections)
    app.router.add_get("/detection/{uid}", _detection_by_uid)
    app.router.add_get("/health", _health)
    return app
