"""T051 [US3]: Multi-drone → two drones both reach MITIGATING via time-based transition.

Feature-011: sentrycs-sim step 4 handles DETECTED→MITIGATING; no UDS calls.
"""

from __future__ import annotations

from tests.integration.helpers import driver
from sentrycs_sim.models import DetectionStatus


def _obj(uid: str, status: str = "FLYING_NORMAL", lat=25.04, lon=121.57):
    return {
        "drone_id": uid,
        "lat": lat,
        "lon": lon,
        "alt_m": 100.0,
        "speed_ms": 12.0,
        "heading_deg": 180.0,
        "status": status,
        "is_lost": False,
    }


async def test_two_drones_independent_progress(
    map_sim_stub, uds_stub, scenario_yaml_factory
) -> None:
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 5.0,
                    "neutralized_at_s": 30.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                },
                {
                    "uid": "TRK-002",
                    "model": "Autel",
                    "detected_at_s": 10.0,
                    "mitigating_at_s": 15.0,
                    "neutralized_at_s": 40.0,
                    "operator_bearing_deg": 45.0,
                    "operator_distance_m": 350.0,
                },
            ],
        }
    )
    map_sim_stub.set_objects([_obj("TRK-001"), _obj("TRK-002", lon=121.58)])

    async with driver(cfg) as d:
        # t=1 → only TRK-001 is eligible (detected_at_s=0 for #1, 10 for #2)
        await d.tick(advance_s=1.0)
        assert d.registry.get_track("TRK-001") is not None
        # TRK-002 detected_at_s=10 not yet reached
        assert d.registry.get_track("TRK-002") is None

        # advance to t=11 → both present
        await d.tick(advance_s=10.0)
        assert d.registry.get_track("TRK-002") is not None

        # advance past both mitigating times (t=21)
        await d.tick(advance_s=10.0)
        # Both should be MITIGATING via time-based step 4 (no UDS)
        t1 = d.registry.get_track("TRK-001")
        t2 = d.registry.get_track("TRK-002")
        assert t1.status is DetectionStatus.MITIGATING
        assert t2.status is DetectionStatus.MITIGATING

        # No UDS calls from sentrycs-sim (responsibility of CoT GW PerimeterGuard)
        assert len(uds_stub.calls) == 0
