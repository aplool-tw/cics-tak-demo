"""T045: compressed memory smoke — registry size bounded, no leak."""

from __future__ import annotations

import tracemalloc

from echoshield_sim.models.lifecycle import MapSimObject, TrackRegistry


def test_registry_does_not_grow_unbounded():
    reg = TrackRegistry(lost_grace_sec=2.0)
    # Simulate 3000 ticks, 5 active + churn: drone_id cycled
    tracemalloc.start()
    _snap0 = tracemalloc.take_snapshot()
    for tick in range(3000):
        now = tick * 0.1
        # rotate drone ids every 30 ticks
        batch = [
            MapSimObject(
                drone_id=f"D{(tick // 30) % 10}-{i}",
                lat=24.0,
                lon=121.0,
                alt_m=100.0,
                speed_ms=10.0,
            )
            for i in range(5)
        ]
        reg.update_from_tick(batch, now_mono=now)
    # Without further updates, lost items should be reaped next tick.
    reg.update_from_tick([], now_mono=3000 * 0.1 + 10.0)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 100 * 1024 * 1024, peak
    assert len(reg) == 0


def test_lost_fires_exactly_once_over_many_cycles():
    reg = TrackRegistry(lost_grace_sec=2.0)
    lost_count = 0
    for cycle in range(100):
        base = cycle * 10.0
        reg.update_from_tick(
            [MapSimObject(drone_id=f"C{cycle}", lat=0, lon=0, alt_m=0, speed_ms=0)],
            now_mono=base,
        )
        # silent past grace
        _, lost_ev = reg.update_from_tick([], now_mono=base + 3.0)
        lost_count += len(lost_ev)
    assert lost_count == 100
