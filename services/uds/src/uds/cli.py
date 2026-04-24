"""UDS CLI entry point: `python -m uds ...`.

Wires together: logging → scenario loader → drones → MapClient → MainLoop → aiohttp server.
"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Optional

import aiohttp
from aiohttp import web

from uds.api.server import create_app
from uds.config import Settings
from uds.engine.loop import MainLoop
from uds.engine.state_machine import Event, try_transition
from uds.engine.trajectory import DroneContext
from uds.logging import configure_logging, get_logger
from uds.push.map_client import MapClient
from uds.scenario.loader import build_initial_drones, load_scenario


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="uds", description="Unified Drone Simulator")
    p.add_argument("--scenario", required=True, help="Path to scenario YAML")
    p.add_argument("--api-port", type=int, default=None, help="REST API port (default 8080)")
    p.add_argument(
        "--map-sim-url",
        default="http://127.0.0.1:8090",
        help="Map Simulator base URL (default http://127.0.0.1:8090)",
    )
    p.add_argument("--hz", type=int, default=None, help="Main loop frequency [1..20]")
    p.add_argument("--verbose", action="store_true", help="Log level = DEBUG")
    p.add_argument(
        "--debug",
        action="store_true",
        help="Enable non-contract debug endpoints GET /status/{id} and GET /drones",
    )
    return p.parse_args(argv)


def _build_contexts(scenario) -> dict[str, DroneContext]:
    ctxs = {}
    for spec in scenario.drones:
        wps = [(w.lat, w.lon, w.alt_m) for w in spec.waypoints]
        lp = spec.landing_point
        ctxs[spec.drone_id] = DroneContext(
            waypoints=wps,
            landing_point=(lp.lat, lp.lon, lp.alt_m, lp.descent_speed_ms),
        )
    return ctxs


async def _run(args: argparse.Namespace) -> int:
    configure_logging(verbose=args.verbose)
    log = get_logger("uds.cli")

    # Scenario (may SystemExit(2))
    scenario = load_scenario(args.scenario)

    settings = Settings.from_args_and_scenario(
        scenario_path=args.scenario,
        cli_api_port=args.api_port,
        cli_hz=args.hz,
        map_sim_url=args.map_sim_url,
        verbose=args.verbose,
        debug=args.debug,
        scenario=scenario,
    )

    drones = build_initial_drones(scenario)
    contexts = _build_contexts(scenario)

    session = aiohttp.ClientSession()
    map_client = MapClient(session=session, base_url=settings.map_sim_url, drones=drones)
    await map_client.start()

    loop_task = MainLoop(
        drones=drones, hz=settings.hz, map_client=map_client, contexts=contexts
    )
    await loop_task.start()

    # Schedule timeline events
    ev_loop = asyncio.get_event_loop()
    for ev in scenario.timeline:
        ev_loop.call_later(ev.at_s, _fire_timeline_event, drones, ev)

    app = create_app(settings=settings, drones=drones, map_client=map_client)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=settings.api_port)
    await site.start()
    log.info(
        "uds.started",
        api_port=settings.api_port,
        hz=settings.hz,
        map_sim_url=settings.map_sim_url,
        debug=settings.debug,
    )

    # Wait for signal
    stop_event = asyncio.Event()

    def _sig_handler():
        stop_event.set()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                ev_loop.add_signal_handler(sig, _sig_handler)
            except NotImplementedError:
                pass

        await stop_event.wait()
    finally:
        log.info("uds.stopping")
        await loop_task.stop()
        await runner.cleanup()
        await map_client.close()
        await session.close()

    return 0


def _fire_timeline_event(drones, ev) -> None:
    log = get_logger("uds.timeline")
    drone = drones.get(ev.drone_id)
    if drone is None:
        log.warning("timeline.missing_drone", drone_id=ev.drone_id)
        return
    if ev.action == "start_flying":
        ok = try_transition(drone, Event.START_FLYING)
        log.info(
            "timeline.fired",
            drone_id=ev.drone_id,
            action=ev.action,
            at_s=ev.at_s,
            transitioned=ok,
        )


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
