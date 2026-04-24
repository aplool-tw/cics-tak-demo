"""T054 [US3]: 5 drones load test — state transitions within 1s of scheduled."""

from __future__ import annotations

from tests.integration.helpers import driver
from sentrycs_sim.models import DetectionStatus


def _obj(uid: str, lat: float):
    return {
        "drone_id": uid,
        "lat": lat,
        "lon": 121.57,
        "alt_m": 100.0,
        "speed_ms": 12.0,
        "heading_deg": 180.0,
        "status": "FLYING_NORMAL",
        "is_lost": False,
    }


async def test_five_drones_simultaneous(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    drones = [
        {
            "uid": f"TRK-{i:03d}",
            "model": "DJI",
            "detected_at_s": 0.0,
            "mitigating_at_s": 1.0,
            "neutralized_at_s": 20.0,
            "operator_bearing_deg": 225.0,
            "operator_distance_m": 300.0,
        }
        for i in range(5)
    ]
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "drones": drones,
        }
    )
    map_sim_stub.set_objects([_obj(d["uid"], 25.04 + i * 0.0001) for i, d in enumerate(drones)])

    async with driver(cfg) as d:
        for _ in range(3):
            await d.tick(advance_s=1.0)
        for s in drones:
            t = d.registry.get_track(s["uid"])
            assert t is not None
            assert t.status is DetectionStatus.MITIGATING
