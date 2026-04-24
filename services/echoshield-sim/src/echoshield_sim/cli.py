"""EchoShield Simulator CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Optional

from .config import RadarConfig, load_config
from .logging import configure_logging, get_logger
from .loop import run


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="echoshield-sim", description="EchoShield radar simulator")
    p.add_argument("--config", required=True, help="Path to YAML config")
    p.add_argument("--verbose", action="store_true", help="DEBUG log level")
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override noise_seed from YAML (CLI wins)",
    )
    return p.parse_args(argv)


def _apply_seed_override(cfg: RadarConfig, seed: Optional[int]) -> RadarConfig:
    if seed is None:
        return cfg
    # frozen model: use model_copy
    return cfg.model_copy(update={"noise_seed": seed})


async def _run_with_signals(cfg: RadarConfig) -> None:
    loop_task = asyncio.create_task(run(cfg))

    def _cancel(*_):
        if not loop_task.done():
            loop_task.cancel()

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
        await loop_task
    except asyncio.CancelledError:
        pass


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    configure_logging(verbose=args.verbose)
    log = get_logger("echoshield_sim.cli")

    cfg = load_config(args.config)
    cfg = _apply_seed_override(cfg, args.seed)

    log.info("cli_start", config=args.config, seed=cfg.noise_seed, verbose=args.verbose)

    try:
        asyncio.run(_run_with_signals(cfg))
    except KeyboardInterrupt:
        pass
    log.info("cli_stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
