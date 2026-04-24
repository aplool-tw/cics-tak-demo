"""T036: bearing + elevation."""

from __future__ import annotations

from echoshield_sim.geo.bearing import azimuth_deg, elevation_deg, haversine_m

SENSOR_LAT = 24.0
SENSOR_LON = 121.0


def _offset_lat(dist_m: float) -> float:
    return SENSOR_LAT + dist_m / 111_320.0


def _offset_lon(dist_m: float) -> float:
    import math

    return SENSOR_LON + dist_m / (111_320.0 * math.cos(math.radians(SENSOR_LAT)))


def test_north_1km_azimuth_zero():
    lat = _offset_lat(1000.0)
    assert abs(azimuth_deg(SENSOR_LAT, SENSOR_LON, lat, SENSOR_LON) - 0.0) <= 0.1
    assert abs(elevation_deg(SENSOR_LAT, SENSOR_LON, 0.0, lat, SENSOR_LON, 0.0)) <= 0.1


def test_east_1km_azimuth_ninety():
    lon = _offset_lon(1000.0)
    az = azimuth_deg(SENSOR_LAT, SENSOR_LON, SENSOR_LAT, lon)
    assert abs(az - 90.0) <= 0.1


def test_south_1km_azimuth_one_eighty():
    lat = _offset_lat(-1000.0)
    az = azimuth_deg(SENSOR_LAT, SENSOR_LON, lat, SENSOR_LON)
    assert abs(az - 180.0) <= 0.1


def test_west_1km_azimuth_two_seventy():
    lon = _offset_lon(-1000.0)
    az = azimuth_deg(SENSOR_LAT, SENSOR_LON, SENSOR_LAT, lon)
    assert abs(az - 270.0) <= 0.1


def test_azimuth_in_range():
    lat = _offset_lat(500.0)
    lon = _offset_lon(500.0)
    az = azimuth_deg(SENSOR_LAT, SENSOR_LON, lat, lon)
    assert 0.0 <= az < 360.0


def test_overhead_elevation_plus_ninety():
    # target at ~same lat/lon, 100m above sensor
    el = elevation_deg(SENSOR_LAT, SENSOR_LON, 0.0, SENSOR_LAT, SENSOR_LON, 100.0)
    assert el == 90.0


def test_below_elevation_minus_ninety():
    el = elevation_deg(SENSOR_LAT, SENSOR_LON, 100.0, SENSOR_LAT, SENSOR_LON, 0.0)
    assert el == -90.0


def test_elevation_forty_five():
    # 1000m north, 1000m up
    lat = _offset_lat(1000.0)
    el = elevation_deg(SENSOR_LAT, SENSOR_LON, 0.0, lat, SENSOR_LON, 1000.0)
    assert abs(el - 45.0) <= 0.1


def test_haversine_approx_equal_to_meters_conversion():
    lat = _offset_lat(1000.0)
    d = haversine_m(SENSOR_LAT, SENSOR_LON, lat, SENSOR_LON)
    assert abs(d - 1000.0) <= 2.0
