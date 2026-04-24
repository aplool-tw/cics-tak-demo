"""T037 [US1]: graceful shutdown cancels tasks + cleans up quickly."""

from __future__ import annotations

import asyncio
import time

from tests.integration.helpers import driver


def _obj(uid: str):
    return {
        "drone_id": uid,
        "lat": 25.04,
        "lon": 121.57,
        "alt_m": 100.0,
        "speed_ms": 12.0,
        "heading_deg": 180.0,
        "status": "FLYING_NORMAL",
        "is_lost": False,
    }


async def test_runner_stops_within_3s(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "poll_interval_s": 0.05,
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
    map_sim_stub.set_objects([_obj("TRK-001")])

    async with driver(cfg) as d:
        # start real run_forever in a task; then stop
        task = asyncio.create_task(d.runner.run_forever())
        await asyncio.sleep(0.2)
        t0 = time.monotonic()
        d.runner.stop()
        await asyncio.wait_for(task, timeout=3.0)
        elapsed = time.monotonic() - t0
        assert elapsed < 3.0
