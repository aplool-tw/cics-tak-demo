"""TrackCorrelator: maintains radar_tracks, rf_tracks, fused_tracks registries.

Implements:
- correlate(track) -> UnifiedTrack (or FUSED)
- update_ttl(now) -> list[str] (uids of Lost tracks; caller emits final CoT)
- build_fused(radar, rf) -> UnifiedTrack

Matching rule (FR-GW-010): candidates = rf tracks with distance<=50m AND |Δt|<=3s; pick min
distance; one-to-many forbidden (an rf already paired with another radar is skipped).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Optional

from cot_gateway.correlate.haversine import haversine_m
from cot_gateway.models.track import TrackSource, UnifiedTrack


class TrackCorrelator:
    def __init__(
        self,
        distance_threshold_m: float = 50.0,
        time_window_s: float = 3.0,
        ttl_s: float = 10.0,
    ) -> None:
        self.distance_threshold_m = distance_threshold_m
        self.time_window_s = time_window_s
        self.ttl_s = ttl_s
        self.radar_tracks: dict[str, UnifiedTrack] = {}
        self.rf_tracks: dict[str, UnifiedTrack] = {}
        self.fused_tracks: dict[str, UnifiedTrack] = {}  # key=rf_track_id
        # radar_track_id → rf_track_id it's paired with (for one-to-many prevention)
        self._radar_to_rf: dict[str, str] = {}
        self._rf_to_radar: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def correlate(self, track: UnifiedTrack) -> UnifiedTrack:
        """Ingest a track; return the final track to emit (possibly FUSED)."""
        if track.source == TrackSource.ECHOSHIELD:
            return self._on_radar(track)
        if track.source == TrackSource.SENTRYCS:
            return self._on_rf(track)
        return track

    def update_ttl(self, now: datetime) -> list[UnifiedTrack]:
        """Mark tracks older than ttl_s as Lost; remove + return them (caller emits final CoT)."""
        threshold = now - timedelta(seconds=self.ttl_s)
        lost: list[UnifiedTrack] = []

        # Radar tracks
        for rid in list(self.radar_tracks.keys()):
            tr = self.radar_tracks[rid]
            if tr.last_updated < threshold:
                lost_track = replace(tr, track_status="Lost", last_updated=now)
                lost.append(lost_track)
                del self.radar_tracks[rid]
                # Break pairing
                if rid in self._radar_to_rf:
                    rf_id = self._radar_to_rf.pop(rid)
                    self._rf_to_radar.pop(rf_id, None)
                    self.fused_tracks.pop(rf_id, None)

        # RF tracks
        for rf_id in list(self.rf_tracks.keys()):
            tr = self.rf_tracks[rf_id]
            if tr.last_updated < threshold:
                lost_track = replace(tr, track_status="Lost", last_updated=now)
                lost.append(lost_track)
                del self.rf_tracks[rf_id]
                if rf_id in self._rf_to_radar:
                    radar_id = self._rf_to_radar.pop(rf_id)
                    self._radar_to_rf.pop(radar_id, None)
                    self.fused_tracks.pop(rf_id, None)

        return lost

    def get_all_active_tracks(self) -> list[UnifiedTrack]:
        out: list[UnifiedTrack] = []
        # Prefer fused over radar/rf when paired
        for rf_id, ft in self.fused_tracks.items():
            out.append(ft)
        for rid, tr in self.radar_tracks.items():
            if rid not in self._radar_to_rf:
                out.append(tr)
        for rf_id, tr in self.rf_tracks.items():
            if rf_id not in self._rf_to_radar:
                out.append(tr)
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_radar(self, radar: UnifiedTrack) -> UnifiedTrack:
        assert radar.radar_track_id is not None
        self.radar_tracks[radar.radar_track_id] = radar

        # If this radar was already paired to an rf, check if rf is still live
        prev_rf = self._radar_to_rf.get(radar.radar_track_id)
        if prev_rf and prev_rf in self.rf_tracks:
            # Refresh fused with latest radar position + latest rf metadata
            rf = self.rf_tracks[prev_rf]
            if self._within_match(radar, rf):
                fused = self.build_fused(radar, rf)
                self.fused_tracks[prev_rf] = fused
                return fused
            else:
                # No longer matching → break pairing, fall through to try new match
                self._radar_to_rf.pop(radar.radar_track_id, None)
                self._rf_to_radar.pop(prev_rf, None)
                self.fused_tracks.pop(prev_rf, None)

        # Find best new match among unpaired rf tracks
        best: Optional[UnifiedTrack] = None
        best_dist = float("inf")
        for rf in self.rf_tracks.values():
            assert rf.rf_track_id is not None
            if (
                rf.rf_track_id in self._rf_to_radar
                and self._rf_to_radar[rf.rf_track_id] != radar.radar_track_id
            ):
                continue  # already paired to another radar
            if rf.track_status != "Active":
                continue
            if not self._within_match(radar, rf):
                continue
            d = haversine_m(radar.lat, radar.lon, rf.lat, rf.lon)
            if d < best_dist:
                best_dist = d
                best = rf
        if best is not None and best.rf_track_id is not None:
            fused = self.build_fused(radar, best)
            self._radar_to_rf[radar.radar_track_id] = best.rf_track_id
            self._rf_to_radar[best.rf_track_id] = radar.radar_track_id
            self.fused_tracks[best.rf_track_id] = fused
            return fused
        return radar

    def _on_rf(self, rf: UnifiedTrack) -> UnifiedTrack:
        assert rf.rf_track_id is not None
        self.rf_tracks[rf.rf_track_id] = rf

        # If already paired, refresh fused using the latest radar for this pairing
        paired_radar_id = self._rf_to_radar.get(rf.rf_track_id)
        if paired_radar_id and paired_radar_id in self.radar_tracks:
            radar = self.radar_tracks[paired_radar_id]
            if self._within_match(radar, rf):
                fused = self.build_fused(radar, rf)
                self.fused_tracks[rf.rf_track_id] = fused
                return fused
            # No longer matching → break pairing, return plain SENTRYCS
            self._rf_to_radar.pop(rf.rf_track_id, None)
            self._radar_to_rf.pop(paired_radar_id, None)
            self.fused_tracks.pop(rf.rf_track_id, None)
        return rf

    def _within_match(self, radar: UnifiedTrack, rf: UnifiedTrack) -> bool:
        if haversine_m(radar.lat, radar.lon, rf.lat, rf.lon) > self.distance_threshold_m:
            return False
        dt = abs((radar.timestamp - rf.timestamp).total_seconds())
        return dt <= self.time_window_s

    @staticmethod
    def build_fused(radar: UnifiedTrack, rf: UnifiedTrack) -> UnifiedTrack:
        assert radar.radar_track_id is not None
        assert rf.rf_track_id is not None
        now = datetime.now(timezone.utc)
        return UnifiedTrack(
            source=TrackSource.FUSED,
            track_id=f"FUSED-{rf.rf_track_id}",
            radar_track_id=radar.radar_track_id,
            rf_track_id=rf.rf_track_id,
            correlation_id=f"FUSED-{rf.rf_track_id}",
            lat=radar.lat,
            lon=radar.lon,
            alt_m=radar.alt_m,
            velocity_ms=radar.velocity_ms,
            azimuth_deg=radar.azimuth_deg,
            elevation_deg=radar.elevation_deg,
            timestamp=radar.timestamp,
            received_at=now,
            last_updated=now,
            track_status="Active",
            classification=radar.classification or "DRONE",
            detection_status=rf.detection_status,
            drone_model=rf.drone_model,
            operator_lat=rf.operator_lat,
            operator_lon=rf.operator_lon,
        )
