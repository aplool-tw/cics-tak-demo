"""T031 [US1]: end-to-end lifecycle IDLE → DETECTED → MITIGATING → NEUTRALIZED → removed."""

from __future__ import annotations

from tests.integration.helpers import driver
from sentrycs_sim.models import DetectionStatus


def _obj(uid: str, status: str = "FLYING_NORMAL", is_lost: bool = False, alt: float = 100.0):
    return {
        "drone_id": uid,
        "lat": 25.04,
        "lon": 121.57,
        "alt_m": alt,
        "speed_ms": 12.0,
        "heading_deg": 180.0,
        "status": status,
        "is_lost": is_lost,
    }


async def test_full_lifecycle(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
    cfg = scenario_yaml_factory(
        {
            "map_sim_url": map_sim_stub.url,
            "uds_url": uds_stub.url,
            "neutralized_hold_s": 30.0,
            "drones": [
                {
                    "uid": "TRK-001",
                    "model": "DJI Mavic 3",
                    "detected_at_s": 5.0,
                    "mitigating_at_s": 20.0,
                    "neutralized_at_s": 35.0,
                    "operator_bearing_deg": 225.0,
                    "operator_distance_m": 300.0,
                }
            ],
        }
    )

    async with driver(cfg) as d:
        # t=0: no tracks
        map_sim_stub.set_objects([])
        await d.tick()
        assert len(d.registry) == 0

        # t=6: drone in Map Sim, past detected_at_s → DETECTED
        map_sim_stub.set_objects([_obj("TRK-001")])
        await d.tick(advance_s=6.0)
        track = d.registry.get_track("TRK-001")
        assert track is not None
        assert track.status is DetectionStatus.DETECTED

        # t=21: past mitigating_at_s → takeover → MITIGATING
        await d.tick(advance_s=15.0)
        assert len(uds_stub.calls) == 1
        assert uds_stub.calls[0]["drone_id"] == "TRK-001"
        assert d.registry.get_track("TRK-001").status is DetectionStatus.MITIGATING

        # t=36: Map Sim reports LANDED → NEUTRALIZED
        map_sim_stub.set_objects([_obj("TRK-001", status="LANDED", alt=0.0)])
        await d.tick(advance_s=15.0)
        track = d.registry.get_track("TRK-001")
        assert track is not None
        assert track.status is DetectionStatus.NEUTRALIZED

        # t=70: after neutralized_hold_s, track is removed
        await d.tick(advance_s=35.0)
        assert d.registry.get_track("TRK-001") is None


async def test_takeover_fires_exactly_once(map_sim_stub, uds_stub, scenario_yaml_factory) -> None:
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
        await d.tick()  # t=0: DETECTED
        for _ in range(5):
            await d.tick(advance_s=1.0)
        assert len(uds_stub.calls) == 1
