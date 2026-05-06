from __future__ import annotations

import asyncio
import ssl
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from pydantic import ValidationError

from tak_client_sim.__main__ import _build_parser
from tak_client_sim.config import ClientConfig, load_config
from tak_client_sim.connection import connect_with_retry
from tak_client_sim.models import ConnectionStats


def _parse_args(*argv: str):
    return _build_parser().parse_args(list(argv))


def test_client_config_use_ssl_defaults_true(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("host: demo-host\n")

    cfg = load_config(_parse_args("--config", str(cfg_file)))

    assert cfg.use_ssl is True


def test_client_config_use_ssl_false_loads_from_yaml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("use_ssl: false\n")

    cfg = load_config(_parse_args("--config", str(cfg_file)))

    assert cfg.use_ssl is False


def test_client_config_use_ssl_true_round_trips() -> None:
    cfg = ClientConfig(use_ssl=True)

    assert cfg.use_ssl is True
    assert cfg.model_dump()["use_ssl"] is True


def test_client_config_use_ssl_still_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ClientConfig(use_ssl=True, extra_field="bad")  # type: ignore[call-arg]


def test_load_config_no_ssl_cli_override(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("use_ssl: true\n")

    cfg = load_config(_parse_args("--config", str(cfg_file), "--no-ssl"))

    assert cfg.use_ssl is False


def test_load_config_ssl_cli_override(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("use_ssl: false\n")

    cfg = load_config(_parse_args("--config", str(cfg_file), "--ssl"))

    assert cfg.use_ssl is True


def test_load_config_without_ssl_flags_keeps_yaml_value(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("use_ssl: false\n")

    cfg = load_config(_parse_args("--config", str(cfg_file)))

    assert cfg.use_ssl is False


@pytest.mark.asyncio
async def test_connect_with_retry_uses_plaintext_when_use_ssl_false() -> None:
    stats = ConnectionStats()
    stop = asyncio.Event()
    reader = MagicMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    open_connection = AsyncMock(return_value=(reader, writer))

    with patch("tak_client_sim.connection.asyncio.open_connection", open_connection):
        await connect_with_retry(ClientConfig(use_ssl=False), stats, stop)

    assert open_connection.await_args.kwargs["ssl"] is None


@pytest.mark.asyncio
async def test_connect_with_retry_uses_ssl_context_when_use_ssl_true() -> None:
    stats = ConnectionStats()
    stop = asyncio.Event()
    reader = MagicMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    open_connection = AsyncMock(return_value=(reader, writer))

    with patch("tak_client_sim.connection.asyncio.open_connection", open_connection):
        await connect_with_retry(ClientConfig(use_ssl=True), stats, stop)

    assert isinstance(open_connection.await_args.kwargs["ssl"], ssl.SSLContext)


def test_demo_yaml_smoke_loads_client_config() -> None:
    config_path = Path(__file__).parents[2] / "config" / "demo.yaml"
    with config_path.open() as fh:
        loaded = yaml.safe_load(fh)

    cfg = ClientConfig(**loaded)

    assert cfg.use_ssl is False
