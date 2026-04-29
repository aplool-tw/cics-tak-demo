#!/usr/bin/env bash
# Smoke test: verify tak-client-sim CLI starts and shows help
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m tak_client_sim --help
echo "smoke test passed"
