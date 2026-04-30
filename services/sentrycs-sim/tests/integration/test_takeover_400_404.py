"""T033 [US1]: time-based DETECTED→MITIGATING transition, no UDS calls from sentrycs-sim.

Feature-011: sentrycs-sim step 4 no longer calls UDS.
All drones transition DETECTED→MITIGATING via time-based mechanism at mitigating_at_s.
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


async def test_uds_400_no_retry(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    """Step 4 does NOT call UDS — both drones transition to MITIGATING via time-based path."""
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 1.0,
                    "neutralized_at_s": 10.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                },
                {
                    "uid": "TRK-002",
                    "model": "Autel",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 1.0,
                    "neutralized_at_s": 10.0,
                    "operator_bearing_deg": 45.0,
                    "operator_distance_m": 350.0,
                },
            ],
        }
    )
    map_sim_stub.set_objects([_obj("TRK-001"), _obj("TRK-002")])

    async with driver(cfg) as d:
        await d.tick()  # DETECTED
        for _ in range(5):
            await d.tick(advance_s=1.0)
        t1 = d.registry.get_track("TRK-001")
        t2 = d.registry.get_track("TRK-002")
        # Both transition to MITIGATING via time-based step 4 (no UDS)
        assert t1 is not None and t1.status is DetectionStatus.MITIGATING
        assert t1.takeover_sent is True
        assert t2 is not None and t2.status is DetectionStatus.MITIGATING
        # No UDS calls from sentrycs-sim
        assert len(uds_stub.calls) == 0


async def test_uds_404_no_retry(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    """Step 4 does NOT call UDS — drone transitions to MITIGATING via time-based path."""
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 1.0,
                    "neutralized_at_s": 10.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                }
            ],
        }
    )
    map_sim_stub.set_objects([_obj("TRK-001")])
    async with driver(cfg) as d:
        for _ in range(5):
            await d.tick(advance_s=1.0)
        t = d.registry.get_track("TRK-001")
        assert t is not None and t.status is DetectionStatus.MITIGATING
        assert t.takeover_sent is True
        # No UDS calls from sentrycs-sim
        assert len(uds_stub.calls) == 0
