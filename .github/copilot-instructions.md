<!-- SPECKIT START -->
Active feature plan: `specs/015-cot-xml-compliance/plan.md` (015-cot-xml-compliance —
CoT XML Standard Format Compliance + Remote TAK Server Support).
RC1: Add <uid Droid="{callsign}"/> as first <detail> child in generate_cot(); add
xml_declaration: bool = False and ca_bundle: str|None = None to TakServerConfig; thread
xml_declaration from config through all 3 generate_cot() call sites in loop.py.
RC2: Add --tak-host HOST and --tak-port PORT CLI flags to cli.py (model_copy pattern);
new config/remote-tak.yaml for cot-gateway; new config/remote-tak.yaml for tak-client-sim.
RC3: New scripts/demo-1drone-remote-tak.sh and demo-3drone-remote-tak.sh with TAK_HOST /
TAK_PORT / TAK_USE_SSL env-var branching (remote TAK if TAK_HOST set, else local relay).
RC4: Add log-vs-wire clarification to cot-gateway README, tak-client-sim README, AGENTS.md;
update specs/005-cot-gateway/contracts/cot-xml.md §1+§2 with <uid Droid>.
G1 TDD: tests/unit/test_generator_xml_decl.py and test_config_xml_decl.py written BEFORE
any source changes. G2: xml_declaration=False default preserves current byte structure.
G7: xml.etree.ElementTree only; no new deps. 279 existing tests must stay green.
Related artifacts: `specs/015-cot-xml-compliance/spec.md`,
`specs/015-cot-xml-compliance/research.md`, `specs/015-cot-xml-compliance/quickstart.md`.
<!-- SPECKIT END -->
