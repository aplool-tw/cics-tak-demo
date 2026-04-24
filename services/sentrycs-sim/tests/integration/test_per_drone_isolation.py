"""T052 [US3]: per-drone isolation — slow UDS for one drone doesn't block others."""

from __future__ import annotations

import asyncio
import time

from tests.integration.helpers import driver
from sentrycs_sim.models import DetectionStatus


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


async def test_slow_uds_for_one_drone_does_not_block_tick(
    map_sim_stub, uds_stub, scenario_yaml_factory
) -> None:
    # make UDS for TRK-002 hang for 5s (> 3s tick)
    uds_stub.set_delay("TRK-002", 5.0)
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "poll_interval_s": 0.05,
            "uds_timeout_s": 6.0,  # allow it to eventually succeed
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 0.0,
                    "neutralized_at_s": 20.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                },
                {
                    "uid": "TRK-002",
                    "model": "Autel",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 0.0,
                    "neutralized_at_s": 20.0,
                    "operator_bearing_deg": 45.0,
                    "operator_distance_m": 350.0,
                },
            ],
        }
    )
    map_sim_stub.set_objects([_obj("TRK-001"), _obj("TRK-002")])

    async with driver(cfg) as d:
        # use runner.run_one_tick directly without waiting for in-flight tasks.
        await d.runner.run_one_tick()

        # 1st tick should schedule 2 takeover tasks; TRK-001 should complete quickly.
        t0 = time.monotonic()
        # poll for TRK-001 to become MITIGATING within ~1s
        while time.monotonic() - t0 < 1.0:
            t1 = d.registry.get_track("TRK-001")
            if t1 and t1.status is DetectionStatus.MITIGATING:
                break
            await asyncio.sleep(0.05)
        t1 = d.registry.get_track("TRK-001")
        assert t1.status is DetectionStatus.MITIGATING
        # TRK-002 still in flight (DETECTED still)
        t2 = d.registry.get_track("TRK-002")
        assert t2.status is DetectionStatus.DETECTED
        # snapshot should still complete fast
        snap = d.registry.snapshot()
        assert len(snap) == 2
