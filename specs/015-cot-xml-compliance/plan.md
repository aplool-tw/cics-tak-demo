# Implementation Plan: Feature 015 — CoT XML Standard Format Compliance + Remote TAK Server Support

**Branch**: `feature/015-cot-xml-compliance` | **Date**: 2025-07-14 | **Spec**: [`specs/015-cot-xml-compliance/spec.md`](spec.md)  
**Input**: Feature specification from `specs/015-cot-xml-compliance/spec.md`

---

## Summary

Add `<uid Droid>` to every CoT XML event and an optional XML declaration header for real-TAK-server
compliance (RC1); expose `--tak-host`/`--tak-port` CLI flags and `remote-tak.yaml` example configs
(RC2); create remote-TAK demo scripts driven by env-vars (RC3); clarify log-vs-wire-format in
READMEs and `AGENTS.md` (RC4).  No new data model, no new REST/WebSocket endpoints, no new package
dependencies.  All 279 existing tests must continue passing after every commit.

---

## Technical Context

**Language/Version**: Python 3.11+ (tested on 3.12)  
**Primary Dependencies**: `pydantic v2`, `structlog`, `PyYAML`, `xml.etree.ElementTree` (stdlib)  
**Storage**: N/A — G6 no persistence; all state is in-memory  
**Testing**: `pytest`, `pytest-asyncio`, `freezegun`; TDD mandatory (G1)  
**Target Platform**: Linux server (`cot-gateway` asyncio service)  
**Project Type**: CLI / asyncio service (single-process, long-running)  
**Performance Goals**: Sub-millisecond CoT XML serialisation; existing throughput unchanged  
**Constraints**:
- G2 — no breaking changes to existing CoT XML wire contract (`<uid Droid>` is additive; `xml_declaration=False` default preserves byte structure)
- G7 — `xml.etree.ElementTree` (stdlib) only; `lxml` prohibited
- Pydantic `extra="forbid"` — new config fields must be declared as proper model fields
- Frozen pydantic models — CLI overrides use `model_copy(update=…)`, never direct mutation  

**Scale/Scope**: Single gateway instance; 279 existing tests must keep passing (180 cot-gateway + 99 tak-client-sim)

---

## Constitution Check

*Source: `AGENTS.md` §3.1 PoC self-discipline guidelines G1–G7  
(`constitution.md` is currently a placeholder template; these guidelines are authoritative.)*

*GATE: Must pass before Phase 0 research. Re-checked post-design (Phase 1 complete — see ✅ below).*

| ID | Guideline | Pre-Design | Post-Design | Notes |
|----|-----------|-----------|-------------|-------|
| **G1** | Test-First — tests written & confirmed FAIL before implementation | ✅ | ✅ | `test_generator_xml_decl.py` and `test_config_xml_decl.py` created and run to red before any source edit |
| **G2** | Contract Freeze — no breaking changes to wire contract | ✅ | ✅ | `<uid Droid>` is additive; `xml_declaration=False` preserves current byte output; contract doc updated (not breaking) |
| **G3** | Structured Logging — structlog JSON, min 4 fields | ✅ | ✅ | No new log calls deviate; log-vs-wire clarification is documentation only |
| **G4** | Observability — lifecycle/error/retry events named | ✅ | ✅ | No new async coroutine paths; existing observability unchanged |
| **G5** | Structural Symmetry — `services/<name>/` layout consistent | ✅ | ✅ | New test files go to `tests/unit/`; `remote-tak.yaml` mirrors existing `demo.yaml` pattern |
| **G6** | No Persistence — memory only | ✅ | ✅ | No new storage introduced |
| **G7** | Minimal Dependencies — stdlib first | ✅ | ✅ | ET already in use; no new deps |

**Gate result: ✅ ALL CLEAR — proceed.**

---

## Project Structure

### Documentation (this feature)

```text
specs/015-cot-xml-compliance/
├── plan.md         ← this file  (/speckit.plan output)
├── research.md     ← Phase 0 output  (/speckit.plan output)
├── quickstart.md   ← Phase 1 output  (/speckit.plan output)
└── tasks.md        ← Phase 2 output  (/speckit.tasks — NOT created by /speckit.plan)
```

> `data-model.md` — **omitted**: no new entities, no new DB/state, no new in-memory data structures.  
> `contracts/` sub-dir — **omitted**: no new service-to-service endpoints.  The one contract change
> (`<uid Droid>`) updates the *existing* file `specs/005-cot-gateway/contracts/cot-xml.md`.

### Source Code (affected paths)

```text
services/cot-gateway/
├── src/cot_gateway/
│   ├── config.py                      ← add xml_declaration: bool = False
│   │                                     add ca_bundle: str | None = None
│   │                                     to TakServerConfig
│   ├── cot/
│   │   └── generator.py               ← add <uid Droid> as first <detail> child;
│   │                                     add xml_declaration: bool = False param
│   ├── loop.py                        ← thread xml_declaration from config to generate_cot()
│   │                                     (3 call-sites: lines 134, 148, 189)
│   └── cli.py                         ← add --tak-host HOST, --tak-port PORT flags;
│                                         apply via nested model_copy pattern
├── config/
│   └── remote-tak.yaml                ← NEW: documented example for real TAK server
├── README.md                          ← add "Connecting to Real TAK Server" section;
│                                         add log-vs-wire clarification note
└── tests/unit/
    ├── test_generator_xml_decl.py     ← NEW: G1-first unit tests (xml_declaration,
    │                                     uid Droid element, 8-scenario regression)
    └── test_config_xml_decl.py        ← NEW: G1-first unit tests (TakServerConfig
                                          xml_declaration field, CLI override)

services/tak-client-sim/
├── config/
│   └── remote-tak.yaml                ← NEW: documented example for remote TAK server
└── README.md                          ← add "Connecting to Real TAK Server" section;
                                          add log-vs-wire clarification note

scripts/
├── demo-1drone-remote-tak.sh          ← NEW: 1-drone demo with TAK_HOST/TAK_PORT/TAK_USE_SSL
└── demo-3drone-remote-tak.sh          ← NEW: 3-drone demo with same env-var logic

specs/005-cot-gateway/contracts/
└── cot-xml.md                         ← update §1 wire-format note + §2 XML schema
                                          to include <uid Droid/>

AGENTS.md                              ← add log ≠ wire format note to logging section
```

**Structure Decision**: Single-service (Option 1) — all changes confined to two existing services,
shared `scripts/`, spec `contracts/`, and `AGENTS.md`.  No new service, no new Python package.

---

## Implementation Phases

### Phase 0 (Research) — complete; see `research.md`

All NEEDS CLARIFICATION items resolved:
- R-001 → XML declaration approach (manual string prefix)
- R-002 → `<uid Droid>` placement (first child of `<detail>`)
- R-003 → `ca_bundle` field in `TakServerConfig`
- R-004 → CLI override pattern (`model_copy`)
- R-005 → Demo script branching logic (env-var `TAK_HOST` presence test)

### Phase 1 (Design & Contracts) — complete; see `quickstart.md`

- No new data model (no entities, no state transitions)
- Contract update: `specs/005-cot-gateway/contracts/cot-xml.md` §1 + §2 (additive)
- Agent context updated (see `.github/copilot-instructions.md`)

### Phase 2 (Tasks) — pending `/speckit.tasks`

See `tasks.md` (not yet generated).

---

## Complexity Tracking

> No constitution violations — this section is intentionally blank.
