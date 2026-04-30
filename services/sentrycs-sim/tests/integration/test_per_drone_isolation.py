"""T052 [US3]: per-drone isolation — both drones transition DETECTED→MITIGATING in same tick.

Feature-011: sentrycs-sim step 4 no longer uses async UDS tasks.
The time-based DETECTED→MITIGATING transition is synchronous within run_one_tick().
"""

from __future__ import annotations

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
    """Step 4 is now synchronous — both drones transition in the same tick.

    Previously this test verified async UDS task isolation.
    After Feature-011, step 4 transitions DETECTED→MITIGATING synchronously
    without calling UDS, so both drones complete in a single tick.
    """
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "poll_interval_s": 0.05,
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
        # One tick is enough for both drones to transition synchronously
        await d.runner.run_one_tick()

        # Both should be MITIGATING immediately (synchronous step 4)
        t1 = d.registry.get_track("TRK-001")
        t2 = d.registry.get_track("TRK-002")
        assert t1 is not None
        assert t2 is not None
        assert t1.status is DetectionStatus.MITIGATING
        assert t2.status is DetectionStatus.MITIGATING

        # No UDS calls (responsibility of CoT GW PerimeterGuard)
        assert len(uds_stub.calls) == 0

        # snapshot should still complete fast
        snap = d.registry.snapshot()
        assert len(snap) == 2
