"""
validate_scenario.py — validates UDS/Sentrycs/EchoShield scenario YAML files.

Usage (standalone):
    python3 validate_scenario.py --uds   services/uds/scenarios/e2e_single_drone.yaml
    python3 validate_scenario.py --sntr  services/sentrycs-sim/config/e2e_single_drone.yaml
    python3 validate_scenario.py --echo  services/echoshield-sim/config/e2e_scenario.yaml

Exit 0 = all checks pass, 1 = at least one violation found.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def __str__(self) -> str:
        lines: list[str] = []
        for e in self.errors:
            lines.append(f"  [ERROR]   {e}")
        for w in self.warnings:
            lines.append(f"  [WARN]    {w}")
        return "\n".join(lines) if lines else "  (no issues)"


# ---------------------------------------------------------------------------
# UDS scenario validation
# ---------------------------------------------------------------------------

def validate_uds_scenario(data: dict[str, Any]) -> ValidationResult:
    """Validate a parsed UDS scenario YAML dict."""
    r = ValidationResult()

    sc = data.get("scenario")
    if not isinstance(sc, dict):
        r.error("Top-level 'scenario' key missing or not a mapping")
        return r

    if "name" not in sc:
        r.error("scenario.name is required")
    if "drones" not in sc or not isinstance(sc["drones"], list):
        r.error("scenario.drones must be a non-empty list")
        return r
    if len(sc["drones"]) == 0:
        r.error("scenario.drones is empty")
        return r

    required_drone_fields = {
        "drone_id", "start_lat", "start_lon", "start_alt_m",
        "speed_ms", "heading_deg",
    }
    seen_ids: set[str] = set()
    for drone in sc["drones"]:
        did = drone.get("drone_id", "<unknown>")
        if did in seen_ids:
            r.error(f"Duplicate drone_id: {did}")
        seen_ids.add(did)
        for f in required_drone_fields:
            if f not in drone:
                r.error(f"drone {did}: missing required field '{f}'")
        if "speed_ms" in drone and drone["speed_ms"] <= 0:
            r.error(f"drone {did}: speed_ms must be positive (got {drone['speed_ms']})")
        if "start_alt_m" in drone and drone["start_alt_m"] < 0:
            r.error(f"drone {did}: start_alt_m must be ≥ 0 (got {drone['start_alt_m']})")

    return r


# ---------------------------------------------------------------------------
# Sentrycs scenario validation
# ---------------------------------------------------------------------------

def validate_sentrycs_scenario(data: dict[str, Any]) -> ValidationResult:
    """Validate a parsed Sentrycs scenario YAML dict."""
    r = ValidationResult()

    for key in ("sensor_lat", "sensor_lon", "drones"):
        if key not in data:
            r.error(f"Missing required top-level key: '{key}'")

    if "drones" not in data:
        return r
    if not isinstance(data["drones"], list) or len(data["drones"]) == 0:
        r.error("'drones' must be a non-empty list")
        return r

    for drone in data["drones"]:
        uid = drone.get("uid", "<unknown>")
        for key in ("detected_at_s", "mitigating_at_s", "neutralized_at_s"):
            if key not in drone:
                r.error(f"drone {uid}: missing '{key}'")

        d = drone.get("detected_at_s")
        m = drone.get("mitigating_at_s")
        n = drone.get("neutralized_at_s")
        if d is not None and m is not None and d >= m:
            r.error(f"drone {uid}: detected_at_s ({d}) must be < mitigating_at_s ({m})")
        if m is not None and n is not None and m >= n:
            r.error(f"drone {uid}: mitigating_at_s ({m}) must be < neutralized_at_s ({n})")

    return r


# ---------------------------------------------------------------------------
# EchoShield config validation
# ---------------------------------------------------------------------------

def validate_echoshield_config(data: dict[str, Any]) -> ValidationResult:
    """Validate a parsed EchoShield sensor config YAML dict."""
    r = ValidationResult()

    for key in ("sensor_lat", "sensor_lon", "max_range_m"):
        if key not in data:
            r.error(f"Missing required key: '{key}'")

    if "max_range_m" in data and data["max_range_m"] < 3_000:
        r.warn(
            f"max_range_m={data['max_range_m']} is below 3000m — "
            "EchoShield may not trigger M2 milestone reliably"
        )
    if "update_rate_hz" in data and data["update_rate_hz"] <= 0:
        r.error(f"update_rate_hz must be positive (got {data['update_rate_hz']})")

    return r


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _print_result(label: str, path: Path, result: ValidationResult) -> None:
    status = "PASS" if result.ok else "FAIL"
    print(f"[{status}] {label}: {path}")
    if result.errors or result.warnings:
        print(str(result))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate e2e scenario YAML files")
    parser.add_argument("--uds",  metavar="FILE", help="UDS scenario YAML")
    parser.add_argument("--sntr", metavar="FILE", help="Sentrycs scenario YAML")
    parser.add_argument("--echo", metavar="FILE", help="EchoShield config YAML")
    args = parser.parse_args(argv)

    overall_ok = True

    if args.uds:
        p = Path(args.uds)
        data = yaml.safe_load(p.read_text())
        res = validate_uds_scenario(data)
        _print_result("UDS scenario", p, res)
        overall_ok = overall_ok and res.ok

    if args.sntr:
        p = Path(args.sntr)
        data = yaml.safe_load(p.read_text())
        res = validate_sentrycs_scenario(data)
        _print_result("Sentrycs scenario", p, res)
        overall_ok = overall_ok and res.ok

    if args.echo:
        p = Path(args.echo)
        data = yaml.safe_load(p.read_text())
        res = validate_echoshield_config(data)
        _print_result("EchoShield config", p, res)
        overall_ok = overall_ok and res.ok

    if not (args.uds or args.sntr or args.echo):
        parser.print_help()
        return 0

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
