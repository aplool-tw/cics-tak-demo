"""aiohttp server factory. Registers debug routes only when settings.debug."""
from __future__ import annotations

from aiohttp import web

from uds.api.debug import handle_drones, handle_status
from uds.api.takeover import handle_takeover
from uds.config import Settings
from uds.models.drone_state import DroneState


def create_app(*, settings: Settings, drones: dict[str, DroneState], map_client) -> web.Application:
    app = web.Application()
    app["settings"] = settings
    app["drones"] = drones
    app["map_client"] = map_client

    app.router.add_post("/command/takeover", handle_takeover)

    if settings.debug:
        app.router.add_get("/status/{drone_id}", handle_status)
        app.router.add_get("/drones", handle_drones)

    return app
