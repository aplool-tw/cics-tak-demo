"""T030 [US1]: Map Sim returns a uid not registered in scenario → model=Unknown."""

from __future__ import annotations


import aiohttp

from sentrycs_sim.config import SentrycsConfig
from sentrycs_sim.loop import LoopRunner
from sentrycs_sim.mapsim import MapSimClient
from sentrycs_sim.models import DetectionStatus, DroneRegistry
from sentrycs_sim.state import StateMachine
from sentrycs_sim.uds import UdsClient


async def test_unregistered_uid_becomes_unknown(
    map_sim_stub, uds_stub, scenario_yaml_factory
) -> None:
    cfg: SentrycsConfig = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "poll_interval_s": 0.05,
            "neutralized_hold_s": 60.0,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 999.0,
                    "neutralized_at_s": 9999.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                }
            ],
        }
    )
    # return a DIFFERENT uid (not in scenario)
    map_sim_stub.set_objects(
        [
            {
                "drone_id": "ALIEN-999",
                "lat": 25.04,
                "lon": 121.57,
                "alt_m": 100.0,
                "speed_ms": 12.0,
                "heading_deg": 180.0,
                "status": "FLYING_NORMAL",
                "is_lost": False,
            }
        ]
    )

    registry = DroneRegistry()
    sm = StateMachine()
    async with aiohttp.ClientSession() as session:
        mapsim = MapSimClient(session, cfg.map_sim_url, timeout_s=1.0)
        uds = UdsClient(session, cfg.uds_url, timeout_s=2.0)
        runner = LoopRunner(
            cfg,
            registry=registry,
            state_machine=sm,
            mapsim=mapsim,
            uds=uds,
        )
        await runner.run_one_tick()

    track = registry.get_track("ALIEN-999")
    assert track is not None
    assert track.model == "Unknown"
    assert track.status is DetectionStatus.DETECTED
