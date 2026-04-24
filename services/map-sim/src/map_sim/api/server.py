"""aiohttp application factory — wires registry, routes, lifecycle hooks."""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone

from aiohttp import web

from ..cleanup.ttl_task import run_cleanup_loop
from ..config import Settings
from ..logging import get_logger
from ..registry.object_registry import ObjectRegistry
from . import handlers_admin, handlers_query, handlers_update


def build_app(settings: Settings, *, registry: ObjectRegistry | None = None) -> web.Application:
    app = web.Application()
    log = get_logger("map_sim.server")

    reg = registry or ObjectRegistry(
        ttl_warn_s=settings.ttl_warn_s, ttl_remove_s=settings.ttl_remove_s
    )

    app["registry"] = reg
    app["settings"] = settings
    app["started_at"] = datetime.now(timezone.utc)
    app["logger"] = log

    # routes
    app.router.add_post("/objects/update", handlers_update.update)
    app.router.add_get("/objects", handlers_query.query)
    app.router.add_get("/objects/all", handlers_admin.objects_all)
    app.router.add_delete("/objects/{drone_id}", handlers_admin.delete_drone)
    app.router.add_get("/health", handlers_admin.health)

    async def _on_startup(app_: web.Application) -> None:
        task = asyncio.create_task(
            run_cleanup_loop(reg, settings.cleanup_period_s, log),
            name="map_sim.ttl_cleanup",
        )
        app_["cleanup_task"] = task

    async def _on_cleanup(app_: web.Application) -> None:
        task = app_.get("cleanup_task")
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app
