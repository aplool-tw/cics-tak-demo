"""Debug endpoints (--debug only, non-contract). contracts §2."""
from __future__ import annotations

from aiohttp import web

from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState


async def handle_status(request: web.Request) -> web.Response:
    drones: dict[str, DroneState] = request.app["drones"]
    drone_id = request.match_info["drone_id"]
    drone = drones.get(drone_id)
    if drone is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(
        {
            "drone_id": drone.drone_id,
            "lat": drone.lat,
            "lon": drone.lon,
            "alt_m": drone.alt_m,
            "velocity_ms": drone.velocity_ms,
            "heading_deg": drone.heading_deg,
            "flight_state": drone.flight_state.value,
            "model": drone.model,
            "operator_lat": drone.operator_lat,
            "operator_lon": drone.operator_lon,
            "is_landed": drone.flight_state == FlightState.LANDED,
        }
    )


async def handle_drones(request: web.Request) -> web.Response:
    drones: dict[str, DroneState] = request.app["drones"]
    return web.json_response(
        {
            "drones": [
                {
                    "drone_id": d.drone_id,
                    "model": d.model,
                    "flight_state": d.flight_state.value,
                }
                for d in drones.values()
            ]
        }
    )
