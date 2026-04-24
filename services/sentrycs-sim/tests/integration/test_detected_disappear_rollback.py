"""T036 [US1]: DETECTED + target disappears → track removed; no takeover sent."""

from __future__ import annotations

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


async def test_detected_disappear_rollback(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 30.0,
                    "neutralized_at_s": 60.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                }
            ],
        }
    )
    map_sim_stub.set_objects([_obj("TRK-001")])
    async with driver(cfg) as d:
        await d.tick()
        await d.tick(advance_s=1.0)
        assert d.registry.get_track("TRK-001") is not None

        # target disappears during DETECTED
        map_sim_stub.set_objects([])
        await d.tick(advance_s=1.0)
        # rollback: track removed, no takeover
        assert d.registry.get_track("TRK-001") is None
        assert uds_stub.calls == []
