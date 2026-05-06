<!-- SPECKIT START -->
Active feature plan: `specs/014-sp-hp-cot/plan.md` (014-sp-hp-cot —
SP/HP CoT Broadcasting: periodic Cursor-on-Target broadcast of SP/HP site markers and SP
defense rings to cot-gateway so ATAK/WinTAK clients see fixed map annotations.
New: BroadcastConfig pydantic model (config.py, extra="forbid", all optional with defaults),
broadcast field on GatewayConfig (default_factory=BroadcastConfig → enabled=false).
New module cot/site_broadcaster.py: generate_sp_cot(), generate_hp_cot(),
generate_ring_cot() (all stdlib ET), SitesBroadcaster class.
GatewayMain: sp_hp_broadcast_loop() coroutine launched as asyncio.Task in run() when
broadcast.enabled=true; crash isolated by existing run() supervision.
CoT types: a-f-G-U-C (SP/HP point markers), u-d-c with <shape><ellipse minor=R major=R
angle=0/> (rings). UIDs: CICS-014-SP, CICS-014-HP, CICS-014-SP-RING-{int(r)}.
Stale = now + 2×interval_s. First broadcast at startup, then every interval_s.
G1 TDD: tests/unit/test_site_broadcaster.py written and failing before implementation.
G7: generate_cot() in cot/generator.py MUST NOT be modified.
Logger: get_logger("cot_gateway.broadcast"), INFO broadcast_cycle per cycle.
Related artifacts: `specs/014-sp-hp-cot/spec.md`, `specs/014-sp-hp-cot/research.md`,
`specs/014-sp-hp-cot/data-model.md`, `specs/014-sp-hp-cot/quickstart.md`.
<!-- SPECKIT END -->
