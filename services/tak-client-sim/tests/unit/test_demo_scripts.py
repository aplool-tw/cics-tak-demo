from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).parents[4]


def test_demo_1drone_missing_config() -> None:
    script_path = REPO_ROOT / "scripts" / "demo-1drone.sh"

    assert script_path.exists(), "scripts/demo-1drone.sh must exist"
    assert os.access(script_path, os.X_OK), "scripts/demo-1drone.sh must be executable"


def test_demo_1drone_scenario_paths() -> None:
    script_path = REPO_ROOT / "scripts" / "demo-1drone.sh"
    content = script_path.read_text()

    assert "demo_single_drone.yaml" in content


def test_demo_3drone_scenario_paths() -> None:
    script_path = REPO_ROOT / "scripts" / "demo-3drone.sh"
    content = script_path.read_text()

    assert "demo_three_drones.yaml" in content
