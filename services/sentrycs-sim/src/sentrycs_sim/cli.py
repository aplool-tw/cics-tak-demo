"""CLI entry: argparse + asyncio.run with signal handlers."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Optional

from .config import SentrycsConfig, load_scenario
from .logging import configure_logging, get_logger
from .loop import run


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="sentrycs-sim", description="Sentrycs Simulator")
    p.add_argument("--scenario", required=True, help="Path to scenario YAML")
    p.add_argument("--api-port", type=int, default=None, help="Override API port (default 17070)")
    p.add_argument("--verbose", action="store_true", help="Enable DEBUG structured logging")
    return p.parse_args(argv)


async def _run_with_signals(cfg: SentrycsConfig) -> None:
    task = asyncio.create_task(run(cfg))

    def _cancel(*_: object) -> None:
        if not task.done():
            task.cancel()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _cancel)
            except (NotImplementedError, RuntimeError):
                pass
    except RuntimeError:
        pass

    try:
        await task
    except asyncio.CancelledError:
        pass


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    configure_logging(verbose=args.verbose)
    log = get_logger("sentrycs_sim.cli")

    try:
        cfg = load_scenario(args.scenario)
    except Exception as exc:
        log.error("scenario_load_failed", path=args.scenario, error=repr(exc))
        return 2

    if args.api_port is not None:
        cfg = cfg.model_copy(update={"api_port": int(args.api_port)})

    log.info("cli_start", scenario=args.scenario, api_port=cfg.api_port, verbose=args.verbose)
    try:
        asyncio.run(_run_with_signals(cfg))
    except KeyboardInterrupt:
        pass
    log.info("cli_stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
