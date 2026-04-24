"""T035 [US1]: MITIGATING + target disappears 10s+ → NEUTRALIZED."""

from __future__ import annotations

from tests.integration.helpers import driver
from sentrycs_sim.models import DetectionStatus


def _obj(uid: str, status: str = "FLYING_NORMAL"):
    return {
        "drone_id": uid,
        "lat": 25.04,
        "lon": 121.57,
        "alt_m": 100.0,
        "speed_ms": 12.0,
        "heading_deg": 180.0,
        "status": status,
        "is_lost": False,
    }


async def test_mitigating_disappear_grace(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "mitigating_disappear_grace_s": 10.0,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 1.0,
                    "neutralized_at_s": 30.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                }
            ],
        }
    )
    map_sim_stub.set_objects([_obj("TRK-001")])
    async with driver(cfg) as d:
        # drive to MITIGATING
        await d.tick()
        for _ in range(3):
            await d.tick(advance_s=1.0)
        assert d.registry.get_track("TRK-001").status is DetectionStatus.MITIGATING

        # now target disappears
        map_sim_stub.set_objects([])
        # 5s gap: still MITIGATING
        await d.tick(advance_s=5.0)
        assert d.registry.get_track("TRK-001").status is DetectionStatus.MITIGATING
        # 12s total: now NEUTRALIZED
        await d.tick(advance_s=7.0)
        assert d.registry.get_track("TRK-001").status is DetectionStatus.NEUTRALIZED
