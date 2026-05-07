from __future__ import annotations

import argparse
import sys
from typing import Optional

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

log = structlog.get_logger(__name__)


class ClientConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = "tak-server"
    port: int = Field(default=18089, ge=1, le=65535)
    use_ssl: bool = True
    use_ssl_verify: bool = False
    ca_bundle: Optional[str] = None
    max_retries: int = Field(default=0, ge=0)
    backoff_initial_s: float = 1.0
    backoff_cap_s: float = 60.0
    filter_prefix: Optional[str] = None
    log_file: Optional[str] = None

    # Web map server (opt-in)
    web_enabled: bool = False
    web_host: str = "127.0.0.1"
    web_port: int = Field(default=18091, ge=1, le=65535)

    @field_validator("filter_prefix", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @field_validator("port", mode="before")
    @classmethod
    def _validate_port(cls, v: object) -> object:
        try:
            port = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"port must be an integer, got {v!r}")
        if not (1 <= port <= 65535):
            raise ValueError(f"port must be between 1 and 65535, got {port}")
        return port


def load_config(args: argparse.Namespace) -> ClientConfig:
    """Load ClientConfig from optional YAML file, then apply CLI overrides."""
    base: dict[str, object] = {}

    config_path: str | None = getattr(args, "config", None)
    if config_path:
        try:
            with open(config_path) as f:
                loaded = yaml.safe_load(f) or {}
            if not isinstance(loaded, dict):
                log.error("config_file_not_mapping", config_path=config_path)
                sys.exit(2)
            base.update(loaded)
        except OSError as exc:
            log.error("config_file_read_failed", config_path=config_path, error=str(exc))
            sys.exit(2)

    # CLI overrides
    if getattr(args, "host", None) is not None:
        base["host"] = args.host
    if getattr(args, "port", None) is not None:
        base["port"] = args.port
    if getattr(args, "ssl", False):
        base["use_ssl"] = True
    if getattr(args, "no_ssl", False):
        base["use_ssl"] = False
    if getattr(args, "no_ssl_verify", False):
        base["use_ssl_verify"] = False
    if getattr(args, "filter", None) is not None:
        base["filter_prefix"] = args.filter
    if getattr(args, "log_file", None) is not None:
        base["log_file"] = args.log_file
    if getattr(args, "max_retries", None) is not None:
        base["max_retries"] = args.max_retries
    if getattr(args, "web", False):
        base["web_enabled"] = True
    if getattr(args, "no_web", False):
        base["web_enabled"] = False
    if getattr(args, "web_host", None) is not None:
        base["web_host"] = args.web_host
    if getattr(args, "web_port", None) is not None:
        base["web_port"] = args.web_port

    try:
        return ClientConfig(**base)
    except Exception as exc:
        log.error("configuration_error", error=str(exc))
        sys.exit(2)


def validate_log_file_writable(path: str) -> None:
    """Fail-fast if the log file path is not writable."""
    try:
        with open(path, "a"):
            pass
    except OSError as exc:
        log.error("log_file_not_writable", path=path, error=str(exc))
        sys.exit(2)
