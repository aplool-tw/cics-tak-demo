<!-- SPECKIT START -->
Active feature plan: `specs/012-track-update-fix/plan.md` (012-track-update-fix —
CoT Gateway Track Update Fix. Four RC bug-fixes in services/cot-gateway:
RC1 JS refreshTracks() → uid-keyed incremental droneMarkers (no clearLayers());
RC2 detect_source_switch returns (list[str],str) — all distinct old uids — and
_emit_for_track iterates full list emitting stale CoT + removing TrackStore entry
for each; RC3 TrackStore._serialize accepts uid param, get_all() passes key,
/tracks JSON gains "uid" field (additive, not G2 frozen); RC4 _within_match
normalises naïve datetimes to UTC before subtraction (local vars only, no mutation).
G2: EchoShield TCP JSON, Sentrycs /detections, TAK CoT XML, UDS /command/takeover
unchanged; contract fixtures unmodified. G7: no new dependencies.
Modified files: cot/uid.py, correlate/correlator.py, loop.py,
web/track_store.py, web/server.py (JS section).
New tests: test_uid_source_switch.py (updated), test_correlator_tz.py,
test_track_store_uid.py, test_multi_uid_source_switch.py.
Related artifacts: `specs/012-track-update-fix/spec.md`,
`specs/012-track-update-fix/research.md`,
`specs/012-track-update-fix/data-model.md`,
`specs/012-track-update-fix/quickstart.md`,
`specs/012-track-update-fix/contracts/tracks-api.md`.
<!-- SPECKIT END -->
