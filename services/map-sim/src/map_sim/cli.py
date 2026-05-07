"""Map Sim CLI entry point."""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from aiohttp import web

from .api.server import build_app
from .config import Settings
from .logging import get_logger, setup_logging


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="map-sim", description="Map Simulator")
    p.add_argument("--port", type=int, default=18090, help="HTTP port (default 18090)")
    p.add_argument("--ttl-warn-s", type=float, default=5.0, help="Warn TTL seconds (default 5.0)")
    p.add_argument(
        "--ttl-remove-s", type=float, default=10.0, help="Remove TTL seconds (default 10.0)"
    )
    p.add_argument("--verbose", action="store_true", help="DEBUG log level")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    setup_logging(verbose=args.verbose)
    log = get_logger("map_sim.cli")

    settings = Settings(
        port=args.port,
        ttl_warn_s=args.ttl_warn_s,
        ttl_remove_s=args.ttl_remove_s,
        verbose=args.verbose,
    )

    app = build_app(settings)
    log.info(
        "server.started",
        port=settings.port,
        ttl_warn_s=settings.ttl_warn_s,
        ttl_remove_s=settings.ttl_remove_s,
    )
    try:
        web.run_app(app, host="127.0.0.1", port=settings.port, access_log=None)
    finally:
        log.info("server.shutdown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
