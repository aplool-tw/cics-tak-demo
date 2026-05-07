"""CLI entry point: argparse + asyncio + signal handlers."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Optional

from .config import GatewayConfig, load_config
from .logging import configure_logging, get_logger
from .loop import GatewayMain
from .tak.ssl_context import build_ssl_context
from .web.track_store import TrackStore


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="cot-gateway", description="CoT Gateway")
    p.add_argument("--config", required=True, help="Path to gateway.yaml")
    p.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")
    p.add_argument(
        "--web", action="store_true", default=None, help="Enable web map UI (overrides config)"
    )
    p.add_argument("--no-web", action="store_true", help="Disable web map UI")
    p.add_argument("--web-host", metavar="HOST", help="Web server bind host")
    p.add_argument("--web-port", type=int, metavar="PORT", help="Web server bind port")
    p.add_argument("--sites-file", metavar="PATH", help="Path to sites.yaml")
    p.add_argument("--tak-host", metavar="HOST", help="TAK Server host (overrides config)")
    p.add_argument(
        "--tak-port", type=int, metavar="PORT", help="TAK Server port (overrides config)"
    )
    p.add_argument("--no-ssl", action="store_true", help="Use plaintext TCP to TAK Server")
    return p.parse_args(argv)


async def _run_with_signals(config: GatewayConfig) -> int:
    ssl_ctx = None
    if config.tak_server.use_ssl:
        ssl_ctx = build_ssl_context(config.tak_server)

    track_store: TrackStore | None = None
    if config.web.enabled:
        track_store = TrackStore()

    gw = GatewayMain(config, ssl_context=ssl_ctx, track_store=track_store)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, gw.request_stop)
        except NotImplementedError:
            pass
    try:
        return await gw.run()
    except asyncio.CancelledError:
        return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    try:
        cfg = load_config(args.config)
    except Exception as exc:  # pragma: no cover
        print(f"config_load_failed: {exc!r}", file=sys.stderr)
        return 2

    # Apply CLI overrides to web config (rebuild via model_copy)
    web_overrides: dict = {}
    if getattr(args, "web", None):
        web_overrides["enabled"] = True
    if getattr(args, "no_web", None):
        web_overrides["enabled"] = False
    if getattr(args, "web_host", None):
        web_overrides["host"] = args.web_host
    if getattr(args, "web_port", None):
        web_overrides["port"] = args.web_port
    if getattr(args, "sites_file", None):
        web_overrides["sites_file"] = args.sites_file
    if web_overrides:
        cfg = cfg.model_copy(update={"web": cfg.web.model_copy(update=web_overrides)})

    # Apply CLI overrides to tak_server config
    tak_overrides: dict = {}
    if getattr(args, "tak_host", None):
        tak_overrides["host"] = args.tak_host
    if getattr(args, "tak_port", None):
        tak_overrides["port"] = args.tak_port
    if getattr(args, "no_ssl", False):
        tak_overrides["use_ssl"] = False
    if tak_overrides:
        cfg = cfg.model_copy(update={"tak_server": cfg.tak_server.model_copy(update=tak_overrides)})

    configure_logging(level=cfg.logging.level, json=cfg.logging.json, verbose=args.verbose)
    log = get_logger("cot_gateway.cli")
    log.info("cli_start", config=args.config, verbose=args.verbose, web_enabled=cfg.web.enabled)

    try:
        rc = asyncio.run(_run_with_signals(cfg))
    except KeyboardInterrupt:
        rc = 0
    log.info("cli_stop", exit_code=rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
