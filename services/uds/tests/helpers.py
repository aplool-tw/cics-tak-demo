"""Helpers to boot a real UDS app backed by a fake Map Simulator.

Test-only convenience — not part of the shipping runtime.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

from uds.api.server import create_app
from uds.config import Settings
from uds.engine.loop import MainLoop
from uds.engine.trajectory import DroneContext
from uds.models.flight_state import FlightState
from uds.push.map_client import MapClient
from uds.scenario.loader import build_initial_drones, load_scenario


def build_contexts(scenario) -> dict:
    ctxs = {}
    for spec in scenario.drones:
        wps = [(w.lat, w.lon, w.alt_m) for w in spec.waypoints]
        lp = spec.landing_point
        ctxs[spec.drone_id] = DroneContext(
            waypoints=wps,
            landing_point=(lp.lat, lp.lon, lp.alt_m, lp.descent_speed_ms),
        )
    return ctxs


@asynccontextmanager
async def boot_uds(
    scenario_path,
    *,
    map_sim_url: str,
    api_port: int = 0,
    debug: bool = False,
    verbose: bool = False,
    autostart_flying: bool = True,
    hz: int = 10,
):
    """Spin up MapClient + MainLoop + aiohttp TestServer for an app.

    Yields dict with: settings, scenario, drones, map_client, loop, client, server.
    """
    scenario = load_scenario(str(scenario_path))
    settings = Settings.from_args_and_scenario(
        scenario_path=str(scenario_path),
        cli_api_port=api_port or None,
        cli_hz=hz,
        map_sim_url=map_sim_url,
        verbose=verbose,
        debug=debug,
        scenario=scenario,
    )
    drones = build_initial_drones(scenario)

    session = aiohttp.ClientSession()
    map_client = MapClient(session=session, base_url=map_sim_url, drones=drones)
    await map_client.start()

    # Auto-start flying: flip timeline@0 drones to FLYING_NORMAL immediately for tests.
    if autostart_flying:
        for ev in scenario.timeline:
            if ev.action == "start_flying" and ev.at_s == 0 and ev.drone_id in drones:
                drones[ev.drone_id].flight_state = FlightState.FLYING_NORMAL

    contexts = build_contexts(scenario)
    loop = MainLoop(drones=drones, hz=settings.hz, map_client=map_client, contexts=contexts)
    await loop.start()

    app = create_app(settings=settings, drones=drones, map_client=map_client)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)

    try:
        yield {
            "settings": settings,
            "scenario": scenario,
            "drones": drones,
            "map_client": map_client,
            "loop": loop,
            "client": client,
            "server": server,
            "session": session,
        }
    finally:
        await loop.stop()
        await map_client.close()
        await server.close()
        await session.close()
