"""
validate_cot.py — parses and validates CoT XML messages against spec rules.

Rules enforced:
  - UID prefix: ECHO- / SENTRYCS- / FUSED-
  - CoT type: single-source → a-u-A-M-F-Q-r (gray); fused → a-h-A-M-F-Q-r (red)
  - Stale duration: Lost → stale==time; NEUTRALIZED → stale==time+30s; others → stale==time+11s

Usage (standalone):
    echo '<event ...>...</event>' | python3 validate_cot.py
    python3 validate_cot.py --file /tmp/stream.ndjson
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CotEvent:
    uid: str
    cot_type: str
    lat: float
    lon: float
    hae: float
    time: datetime
    start: datetime
    stale: datetime
    remarks: str


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_DT_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
)


def _parse_dt(s: str) -> datetime:
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # fallback: fromisoformat with manual Z→+00:00 substitution
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_cot(xml_str: str) -> CotEvent:
    """Parse a CoT XML string into a CotEvent."""
    root = ET.fromstring(xml_str)
    uid      = root.attrib["uid"]
    cot_type = root.attrib["type"]
    time_dt  = _parse_dt(root.attrib["time"])
    start_dt = _parse_dt(root.attrib["start"])
    stale_dt = _parse_dt(root.attrib["stale"])

    pt = root.find("point")
    if pt is None:
        raise ValueError("CoT XML missing <point> element")
    lat = float(pt.attrib["lat"])
    lon = float(pt.attrib["lon"])
    hae = float(pt.attrib["hae"])

    detail  = root.find("detail")
    remarks = ""
    if detail is not None:
        rm = detail.find("remarks")
        if rm is not None and rm.text:
            remarks = rm.text.strip()

    return CotEvent(
        uid=uid,
        cot_type=cot_type,
        lat=lat,
        lon=lon,
        hae=hae,
        time=time_dt,
        start=start_dt,
        stale=stale_dt,
        remarks=remarks,
    )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

_GRAY_TYPE = "a-u-A-M-F-Q-r"
_RED_TYPE  = "a-h-A-M-F-Q-r"


def classify_source(ev: CotEvent) -> str:
    """Return 'ECHO', 'SENTRYCS', 'FUSED', or 'UNKNOWN'."""
    uid = ev.uid
    if uid.startswith("ECHO-"):
        return "ECHO"
    if uid.startswith("SENTRYCS-"):
        return "SENTRYCS"
    if uid.startswith("FUSED-"):
        return "FUSED"
    return "UNKNOWN"


def check_cot_type_rule(ev: CotEvent) -> bool:
    """
    Return True if the CoT type is correct for the source:
      ECHO / SENTRYCS → gray (a-u-A-M-F-Q-r)
      FUSED           → red  (a-h-A-M-F-Q-r)
    """
    source = classify_source(ev)
    if source in ("ECHO", "SENTRYCS"):
        return ev.cot_type == _GRAY_TYPE
    if source == "FUSED":
        return ev.cot_type == _RED_TYPE
    return True  # UNKNOWN — no rule applies


def check_stale_rule(ev: CotEvent) -> tuple[bool, str]:
    """
    Return (ok, reason).

    Stale rules (tolerances ±1 s):
      - remarks contains "status=Lost"         → stale == time         (tol ±1s)
      - remarks contains "status=NEUTRALIZED"  → stale == time + 30s   (tol ±1s)
      - all other                              → stale == time + 11s   (tol ±1s)
    """
    delta = (ev.stale - ev.time).total_seconds()

    if "status=Lost" in ev.remarks or "Lost" in ev.remarks.split("status=")[-1].split(",")[0]:
        if abs(delta) <= 1.0:
            return True, ""
        return False, f"Lost stale delta={delta:.1f}s; expected 0 (±1s)"

    if "status=NEUTRALIZED" in ev.remarks:
        if abs(delta - 30.0) <= 1.0:
            return True, ""
        return False, f"NEUTRALIZED stale delta={delta:.1f}s; expected 30 (±1s)"

    # default: +11s
    if abs(delta - 11.0) <= 1.0:
        return True, ""
    return False, f"Normal stale delta={delta:.1f}s; expected 11 (±1s)"


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _validate_stream(lines: list[str]) -> int:
    violations = 0
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or not line.startswith("<"):
            continue
        try:
            ev = parse_cot(line)
        except Exception as exc:
            print(f"[{i}] PARSE ERROR: {exc}", file=sys.stderr)
            violations += 1
            continue

        issues: list[str] = []
        if not check_cot_type_rule(ev):
            issues.append(f"CoT type mismatch (uid={ev.uid}, type={ev.cot_type})")
        ok, msg = check_stale_rule(ev)
        if not ok:
            issues.append(f"Stale violation (uid={ev.uid}): {msg}")

        if issues:
            for iss in issues:
                print(f"[{i}] FAIL  {iss}")
            violations += 1
        else:
            print(f"[{i}] OK    uid={ev.uid} type={ev.cot_type}")

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate CoT XML messages against spec rules")
    parser.add_argument("--file", metavar="FILE", help="NDJSON file of CoT XML messages (one per line)")
    args = parser.parse_args(argv)

    if args.file:
        lines = Path(args.file).read_text().splitlines()
    else:
        if sys.stdin.isatty():
            parser.print_help()
            return 0
        lines = sys.stdin.read().splitlines()

    violations = _validate_stream(lines)
    if violations:
        print(f"\n{violations} violation(s) found.")
        return 1
    print("\nAll CoT messages pass validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
