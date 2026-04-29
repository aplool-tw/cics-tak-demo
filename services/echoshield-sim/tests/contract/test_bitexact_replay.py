"""T027/T038: bit-exact replay — same seed + frozen time → identical bytes."""

from __future__ import annotations


from echoshield_sim.config import RadarConfig
from echoshield_sim.geo.noise import make_noise
from echoshield_sim.loop import build_radar_track
from echoshield_sim.models.lifecycle import MapSimObject


def _cfg() -> RadarConfig:
    return RadarConfig(
        sensor_lat=24.0,
        sensor_lon=121.0,
        sensor_alt_m=10.0,
        noise_seed=42,
    )


def _obj() -> MapSimObject:
    return MapSimObject(drone_id="A", lat=24.01, lon=121.01, alt_m=100.0, speed_ms=12.5)


def _render_n(n: int) -> list[bytes]:
    cfg = _cfg()
    noise = make_noise(cfg)
    out = []
    obj = _obj()
    for i in range(n):
        track = build_radar_track(
            track_id="TRK-E01",
            obj=obj,
            sensor_lat=cfg.sensor_lat,
            sensor_lon=cfg.sensor_lon,
            sensor_alt_m=cfg.sensor_alt_m,
            noise=noise,
            status="Active",
            timestamp="2026-04-24T08:15:30.000Z",
        )
        out.append(track.to_wire_bytes())
    return out


def test_same_seed_produces_same_bytes():
    a = _render_n(3)
    b = _render_n(3)
    assert a == b


def test_different_seed_different_bytes():
    cfg1 = RadarConfig(sensor_lat=24.0, sensor_lon=121.0, noise_seed=1)
    cfg2 = RadarConfig(sensor_lat=24.0, sensor_lon=121.0, noise_seed=2)
    n1 = make_noise(cfg1)
    n2 = make_noise(cfg2)
    obj = _obj()
    t1 = build_radar_track(
        track_id="TRK-E01",
        obj=obj,
        sensor_lat=24.0,
        sensor_lon=121.0,
        sensor_alt_m=0.0,
        noise=n1,
        status="Active",
        timestamp="2026-04-24T08:15:30.000Z",
    ).to_wire_bytes()
    t2 = build_radar_track(
        track_id="TRK-E01",
        obj=obj,
        sensor_lat=24.0,
        sensor_lon=121.0,
        sensor_alt_m=0.0,
        noise=n2,
        status="Active",
        timestamp="2026-04-24T08:15:30.000Z",
    ).to_wire_bytes()
    assert t1 != t2


def test_golden_first_sample_schema_ok():
    """First rendered bytes at seed=42 match schema."""
    import json
    from jsonschema import Draft202012Validator
    from tests.contract.test_radar_track_schema import RADAR_TRACK_SCHEMA

    out = _render_n(1)[0]
    obj = json.loads(out[:-1])
    Draft202012Validator(RADAR_TRACK_SCHEMA).validate(obj)
