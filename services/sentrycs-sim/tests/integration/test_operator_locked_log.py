"""T046 [US2]: operator_locked log event emitted on track creation."""

from __future__ import annotations

import json

from tests.integration.helpers import driver


async def test_operator_locked_event(map_sim_stub, uds_stub, scenario_yaml_factory, capsys) -> None:
    from sentrycs_sim.logging import configure_logging

    configure_logging(verbose=True)

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
    map_sim_stub.set_objects(
        [
            {
                "drone_id": "TRK-001",
                "lat": 25.04,
                "lon": 121.57,
                "alt_m": 100.0,
                "speed_ms": 12.0,
                "heading_deg": 180.0,
                "status": "FLYING_NORMAL",
                "is_lost": False,
            }
        ]
    )
    async with driver(cfg) as d:
        await d.tick()
        await d.tick(advance_s=1.0)
    out = capsys.readouterr().out.splitlines()
    events = [json.loads(ln) for ln in out if ln.strip().startswith("{")]
    locked = [e for e in events if e.get("event") == "operator_locked"]
    assert len(locked) == 1, locked
    e = locked[0]
    for key in ("uid", "operator_lat", "operator_lon", "bearing_deg", "distance_m"):
        assert key in e
    assert e["uid"] == "TRK-001"
    assert e["bearing_deg"] == 225.0
    assert e["distance_m"] == 300.0
