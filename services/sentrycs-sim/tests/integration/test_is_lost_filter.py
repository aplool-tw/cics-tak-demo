"""T032 [US1]: is_lost=true filters out objects entirely."""

from __future__ import annotations

from tests.integration.helpers import driver


async def test_is_lost_objects_never_detected(
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
                    "neutralized_at_s": 20.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                }
            ],
        }
    )
    # Map Sim sends this drone but with is_lost=true
    map_sim_stub.set_objects(
        [
            {
                "drone_id": "TRK-001",
                "lat": 25.04,
                "lon": 121.57,
                "alt_m": 100.0,
                "speed_ms": 12.0,
                "heading_deg": 180.0,
                "status": "LOST",
                "is_lost": True,
            }
        ]
    )
    async with driver(cfg) as d:
        for _ in range(10):
            await d.tick(advance_s=1.0)
        # 100% filtered: no track ever created, no takeover ever sent
        assert len(d.registry) == 0
        assert uds_stub.calls == []
