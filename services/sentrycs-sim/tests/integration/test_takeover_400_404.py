"""T033 [US1]: UDS 400 / 404 → stays DETECTED, latches, no retry."""

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
    uds_stub.default_status = 400
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
    # 2nd drone fine (200), 1st gets 400 because default_status applies to both.
    # Override per uid:
    uds_stub.default_status = 200
    uds_stub.set_status("TRK-001", 400)

    map_sim_stub.set_objects([_obj("TRK-001"), _obj("TRK-002")])

    async with driver(cfg) as d:
        await d.tick()  # DETECTED
        for _ in range(5):
            await d.tick(advance_s=1.0)
        t1 = d.registry.get_track("TRK-001")
        t2 = d.registry.get_track("TRK-002")
        assert t1 is not None and t1.status is DetectionStatus.DETECTED
        assert t1.takeover_sent is True
        # exactly one call for TRK-001
        n001 = sum(1 for c in uds_stub.calls if c.get("drone_id") == "TRK-001")
        assert n001 == 1
        # TRK-002 unaffected → MITIGATING
        assert t2 is not None and t2.status is DetectionStatus.MITIGATING


async def test_uds_404_no_retry(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    uds_stub.default_status = 404
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
        assert t is not None and t.status is DetectionStatus.DETECTED
        assert t.takeover_sent is True
        assert sum(1 for c in uds_stub.calls if c.get("drone_id") == "TRK-001") == 1
