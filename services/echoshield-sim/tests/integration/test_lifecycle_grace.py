"""T029: lifecycle/grace integration against real LoopRunner (using registry directly).

Uses TrackRegistry via a thin driver to verify data-model §4 transitions without
the full asyncio server.
"""

from __future__ import annotations

from echoshield_sim.models.lifecycle import MapSimObject, TrackRegistry


def _obj(did="A"):
    return MapSimObject(drone_id=did, lat=24.0, lon=121.0, alt_m=100.0, speed_ms=10.0)


def test_scenario_a_grace_absorbs_flicker():
    reg = TrackRegistry(lost_grace_sec=2.0)
    a1, _ = reg.update_from_tick([_obj()], now_mono=0.0)
    # silent 1.5s — within grace
    _, l1 = reg.update_from_tick([], now_mono=1.5)
    # reappear
    a2, l2 = reg.update_from_tick([_obj()], now_mono=1.6)
    assert not l1 and not l2
    assert a2[0].track_id == a1[0].track_id


def test_scenario_b_lost_emitted_once_after_grace():
    reg = TrackRegistry(lost_grace_sec=2.0)
    a1, _ = reg.update_from_tick([_obj()], now_mono=0.0)
    _, lost = reg.update_from_tick([], now_mono=2.5)
    assert len(lost) == 1
    assert lost[0].track_id == a1[0].track_id
    # continuing to disappear: no more lost
    for i in range(5):
        _, lost_ev = reg.update_from_tick([], now_mono=3.0 + i * 0.1)
        assert not lost_ev


def test_scenario_c_reappear_same_track_id():
    """After Lost, re-appearing drone reuses same track_id (= drone_id) per spec."""
    reg = TrackRegistry(lost_grace_sec=2.0)
    a1, _ = reg.update_from_tick([_obj()], now_mono=0.0)
    _, lost = reg.update_from_tick([], now_mono=3.0)
    assert lost
    a2, _ = reg.update_from_tick([_obj()], now_mono=10.0)
    assert a2[0].track_id == a1[0].track_id
