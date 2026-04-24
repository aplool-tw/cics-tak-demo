"""T051 [US3]: UDS 409 → MITIGATING; another drone unaffected."""

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


async def test_409_transitions_to_mitigating(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    uds_stub.set_status("TRK-001", 409)
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 1.0,
                    "neutralized_at_s": 20.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                },
                {
                    "uid": "TRK-002",
                    "model": "Autel",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 1.0,
                    "neutralized_at_s": 20.0,
                    "operator_bearing_deg": 45.0,
                    "operator_distance_m": 350.0,
                },
            ],
        }
    )
    map_sim_stub.set_objects([_obj("TRK-001"), _obj("TRK-002")])

    async with driver(cfg) as d:
        for _ in range(3):
            await d.tick(advance_s=1.0)
        t1 = d.registry.get_track("TRK-001")
        t2 = d.registry.get_track("TRK-002")
        assert t1.status is DetectionStatus.MITIGATING
        assert t1.takeover_sent is True
        # exactly one call per drone
        n001 = sum(1 for c in uds_stub.calls if c.get("drone_id") == "TRK-001")
        assert n001 == 1
        # TRK-002 progresses normally
        assert t2.status is DetectionStatus.MITIGATING
