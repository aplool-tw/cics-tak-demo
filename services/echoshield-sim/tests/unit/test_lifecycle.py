"""T025: TrackRegistry state machine (data-model.md §4)."""

from __future__ import annotations

from echoshield_sim.models.lifecycle import MapSimObject, TrackRegistry


def _obj(drone_id: str, lat: float = 24.0, lon: float = 121.0) -> MapSimObject:
    return MapSimObject(drone_id=drone_id, lat=lat, lon=lon, alt_m=100.0, speed_ms=10.0)


def test_first_appearance_allocates_track_id():
    reg = TrackRegistry(lost_grace_sec=2.0)
    active, lost = reg.update_from_tick([_obj("A")], now_mono=0.0)
    assert len(active) == 1
    assert not lost
    assert active[0].track_id.startswith("echo-")
    assert len(active[0].track_id) == 5 + 8


def test_active_to_active_same_id():
    reg = TrackRegistry(lost_grace_sec=2.0)
    a1, _ = reg.update_from_tick([_obj("A")], now_mono=0.0)
    a2, _ = reg.update_from_tick([_obj("A")], now_mono=0.1)
    assert a1[0].track_id == a2[0].track_id


def test_grace_recovers_without_lost():
    reg = TrackRegistry(lost_grace_sec=2.0)
    a1, _ = reg.update_from_tick([_obj("A")], now_mono=0.0)
    # disappears for 1.5s
    _, lost1 = reg.update_from_tick([], now_mono=1.5)
    assert not lost1
    # reappears within grace
    a3, lost2 = reg.update_from_tick([_obj("A")], now_mono=1.6)
    assert not lost2
    assert a3[0].track_id == a1[0].track_id


def test_grace_timeout_emits_lost_exactly_once():
    reg = TrackRegistry(lost_grace_sec=2.0)
    a1, _ = reg.update_from_tick([_obj("A")], now_mono=0.0)
    # silent past grace
    _, lost1 = reg.update_from_tick([], now_mono=3.0)
    assert len(lost1) == 1
    assert lost1[0].track_id == a1[0].track_id
    # next tick: no more lost
    _, lost2 = reg.update_from_tick([], now_mono=4.0)
    assert not lost2
    assert len(reg) == 0


def test_after_lost_new_id_assigned():
    reg = TrackRegistry(lost_grace_sec=2.0)
    a1, _ = reg.update_from_tick([_obj("A")], now_mono=0.0)
    _, lost = reg.update_from_tick([], now_mono=3.0)
    assert lost
    a2, _ = reg.update_from_tick([_obj("A")], now_mono=10.0)
    assert a2[0].track_id != a1[0].track_id


def test_grace_at_exactly_threshold_is_still_grace():
    reg = TrackRegistry(lost_grace_sec=2.0)
    reg.update_from_tick([_obj("A")], now_mono=0.0)
    _, lost = reg.update_from_tick([], now_mono=2.0)  # <=, not >
    assert not lost


def test_multiple_drones_independent():
    reg = TrackRegistry(lost_grace_sec=2.0)
    a, _ = reg.update_from_tick([_obj("A"), _obj("B")], now_mono=0.0)
    assert len(a) == 2
    a2, lost = reg.update_from_tick([_obj("A")], now_mono=3.0)
    # B lost
    assert len(lost) == 1
    assert lost[0].drone_id == "B"
    assert len(a2) == 1
    assert a2[0].drone_id == "A"
