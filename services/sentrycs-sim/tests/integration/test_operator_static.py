"""T045 [US2]: operator_lat/lon stays bit-for-bit equal over scenario lifespan."""

from __future__ import annotations

from tests.integration.helpers import driver


async def test_operator_position_is_locked(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 0.0,
                    "mitigating_at_s": 999.0,
                    "neutralized_at_s": 9999.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                }
            ],
        }
    )
    async with driver(cfg) as d:
        # 15 different positions; operator must stay identical
        samples: list[tuple[float, float]] = []
        for i in range(15):
            map_sim_stub.set_objects(
                [
                    {
                        "drone_id": "TRK-001",
                        "lat": 25.04 + i * 0.001,
                        "lon": 121.57 + i * 0.001,
                        "alt_m": 100.0 + i,
                        "speed_ms": 12.0,
                        "heading_deg": 180.0,
                        "status": "FLYING_NORMAL",
                        "is_lost": False,
                    }
                ]
            )
            await d.tick(advance_s=1.0)
            r = d.registry.get("TRK-001")
            assert r is not None
            samples.append((r.operator_lat, r.operator_lon))
            # also echo of static scenario fields
            assert r.operator_distance_m == 300.0
            assert r.operator_bearing_deg == 225.0
        # bit-for-bit identical
        first = samples[0]
        for s in samples[1:]:
            assert s == first, (s, first)
