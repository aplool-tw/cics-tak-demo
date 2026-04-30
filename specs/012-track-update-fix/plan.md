# Implementation Plan: CoT Gateway Track Update Fix

**Branch**: `feature/012-track-update-fix` | **Date**: 2026-04-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/012-track-update-fix/spec.md`

## Summary

Fix four root causes (RC1–RC4) in `services/cot-gateway` that produce incorrect map display and
orphaned ATAK icons during EchoShield→FUSED source transitions and simultaneous multi-source
tracking. Changes are confined to five existing source files and four test files; no new runtime
dependencies (G7), no external wire contracts modified (G2).

| RC | Fix | File |
|----|-----|------|
| RC1 | JS `refreshTracks()` → uid-keyed incremental `droneMarkers` strategy | `web/server.py` |
| RC2 | `detect_source_switch` returns `(list[str], str)` — all distinct old uids | `cot/uid.py`, `loop.py` |
| RC3 | `TrackStore._serialize` accepts and embeds `uid` param | `web/track_store.py` |
| RC4 | `_within_match` normalises naïve timestamps to UTC before subtraction | `correlate/correlator.py` |

## Technical Context

**Language/Version**: Python 3.11+ (server-side), ES2020 vanilla JS (browser-side, inlined in aiohttp HTML template)
**Primary Dependencies**: aiohttp ≥3.9, pydantic ≥2.6, structlog ≥24.1, PyYAML, cryptography; Leaflet 1.9.4 (CDN, browser-side)
**Storage**: In-memory `TrackStore` (asyncio-locked dict); no persistent storage
**Testing**: pytest ≥8.0, pytest-asyncio ≥0.23, freezegun ≥1.4; ruff + black for lint/format
**Target Platform**: Linux server (asyncio daemon), aiohttp web on port 8092; Docker-compatible
**Project Type**: Asyncio background service (5 coroutines + 2 queues) with embedded Leaflet tactical map
**Performance Goals**: 2-second map refresh cycle; < 50 ms per-track processing; no visible flicker on marker update
**Constraints**: G2 — frozen external wire contracts (EchoShield TCP JSON, Sentrycs `/detections`, TAK CoT XML, UDS `/command/takeover`); G7 — no new third-party packages; `datetime.timezone` (stdlib, already imported) is sufficient
**Scale/Scope**: 1–10 simultaneous drone tracks; single-node demo deployment

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

> **Note**: The project constitution (`.specify/memory/constitution.md`) is a blank template — no principles have been ratified yet. Gates are evaluated against the two explicit design constraints declared in the spec (G2, G7) and the established architectural patterns visible in the existing codebase.

| Gate | Requirement | Status |
|------|-------------|--------|
| G2 — Frozen external wire contracts | `uid` field is additive-only to `/tracks` (internal UI endpoint). EchoShield TCP JSON, Sentrycs `/detections`, TAK CoT XML, and UDS `/command/takeover` body are not touched. Contract test fixtures unchanged. | ✅ PASS |
| G7 — No new dependencies | `datetime.timezone` already imported in `correlator.py`. `detect_source_switch` signature change uses stdlib `list`. `pyproject.toml` not modified. | ✅ PASS |
| No `UnifiedTrack` mutation | `_within_match` normalisation uses local variables `ts_radar`/`ts_rf`; `UnifiedTrack.timestamp` fields are never reassigned. | ✅ PASS |
| Single-service scope | All changes in `services/cot-gateway/`; no cross-service modifications, no new modules or packages. | ✅ PASS |
| Additive `/tracks` schema | New `uid` field added to JSON response. Existing 19 fields (source, lat, lon, takeover_issued, …) preserved with no renames or removals. JS panel reads named fields; ignores unknown fields silently. | ✅ PASS |

**Result**: All gates pass. No complexity violations requiring justification. ✅

**Post-Phase-1 re-check**: Design artifacts (data-model.md, contracts/tracks-api.md) confirm all gates remain satisfied — no additional fields added beyond `uid`; no new imports beyond `timezone` (already present); all four external wire schemas unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/012-track-update-fix/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/
│   └── tracks-api.md    # Phase 1 output — /tracks endpoint schema (updated)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
services/cot-gateway/
├── src/cot_gateway/
│   ├── cot/
│   │   └── uid.py                 ← RC2: detect_source_switch → (list[str], str)
│   ├── correlate/
│   │   └── correlator.py          ← RC4: _within_match timezone normalisation
│   ├── loop.py                    ← RC2: _emit_for_track iterates full old_uids list
│   └── web/
│       ├── track_store.py         ← RC1/RC3: _serialize adds uid param; get_all passes key
│       └── server.py              ← RC1: refreshTracks() → incremental droneMarkers strategy
│           (JS section in _HTML_TEMPLATE)
├── tests/
│   ├── contract/                  ← unchanged (G2 constraint): all 4 wire tests must pass as-is
│   │   ├── test_cot_xml_schema.py
│   │   ├── test_echodyne_wire.py
│   │   ├── test_sentrycs_poller.py
│   │   └── test_tak_uplink.py
│   ├── integration/
│   │   └── test_multi_uid_source_switch.py  ← new: FR-012-021 dual-uid _emit_for_track path
│   └── unit/
│       ├── test_uid_source_switch.py        ← updated: (list,str) unpack + FR-012-019/020
│       ├── test_correlator_tz.py            ← new: FR-012-022 all 4 tz combinations
│       └── test_track_store_uid.py          ← new: FR-012-001/002/003 uid in payload
└── pyproject.toml                           ← unchanged (no new dependencies)
```

**Structure Decision**: Single-service structure (existing `services/cot-gateway/`). All changes
are confined to 5 existing source files plus 4 test files (1 updated, 3 new). No new modules,
packages, or top-level directories are created.

## Complexity Tracking

> No violations — all gates pass. No complexity justification required.
