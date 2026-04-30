from __future__ import annotations

import argparse
import asyncio
import sys

from tak_client_sim.config import load_config, validate_log_file_writable
from tak_client_sim.runner import configure_logging, main


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tak-client-sim",
        description="TAK Client Simulator — receives CoT XML from TAK Server for PoC verification",
    )
    p.add_argument("--host", default=None, help="TAK Server host (default: tak-server)")
    p.add_argument("--port", type=int, default=None, help="TAK Server port (default: 8089)")
    p.add_argument(
        "--no-ssl-verify",
        action="store_true",
        dest="no_ssl_verify",
        help="Skip SSL certificate verification (PoC mode)",
    )
    p.add_argument(
        "--filter", default=None, metavar="PREFIX", help="Only display CoT events whose UID starts with PREFIX"
    )
    p.add_argument(
        "--log-file", default=None, metavar="PATH", help="Write structlog JSON to this file in addition to stderr"
    )
    p.add_argument("--max-retries", type=int, default=None, metavar="N", help="Max reconnect attempts (0 = unlimited)")
    p.add_argument("--config", default=None, metavar="PATH", help="YAML config file path (CLI args take precedence)")
    p.add_argument("--web", action="store_true", dest="web", help="Enable the web map server (default: off)")
    p.add_argument("--no-web", action="store_true", dest="no_web", help="Disable the web map server")
    p.add_argument("--web-host", default=None, metavar="HOST", help="Web map server bind host (default: 127.0.0.1)")
    p.add_argument("--web-port", type=int, default=None, metavar="PORT", help="Web map server port (default: 8091)")
    return p


def _run() -> None:
    args = _build_parser().parse_args()
    config = load_config(args)

    if config.log_file:
        validate_log_file_writable(config.log_file)

    configure_logging(config.log_file)

    try:
        asyncio.run(main(config))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    _run()
