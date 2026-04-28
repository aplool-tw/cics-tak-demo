"""Pydantic v2 GatewayConfig with YAML loader + ${ENV} expansion + fail-fast validation."""

from __future__ import annotations

import os
import re
import warnings
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Silence "json shadows BaseModel attribute" benign warning (we use `logging.json` YAML key).
warnings.filterwarnings(
    "ignore",
    message=r'Field name "json" in "LoggingConfig" shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)


class EchoshieldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "echoshield-sim"
    port: int = Field(default=9000, gt=0, le=65535)
    reconnect_interval_s: float = Field(default=5.0, gt=0.0)


class SentrycsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    host: str = "sentrycs-sim"
    port: int = Field(default=7070, gt=0, le=65535)
    poll_interval_s: float = Field(default=1.0, gt=0.0)
    timeout_s: float = Field(default=2.0, gt=0.0)


class CorrelatorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    distance_threshold_m: float = Field(default=50.0, gt=0.0)
    time_window_s: float = Field(default=3.0, gt=0.0)
    ttl_s: float = Field(default=10.0, gt=0.0)


class TakServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "tak-server"
    port: int = Field(default=8089, gt=0, le=65535)
    use_ssl: bool = True
    use_ssl_verify: bool = False
    cert_file: str = "config/certs/gateway.p12"
    cert_password: str | None = None
    max_retries: int = Field(default=5, ge=1)
    backoff_initial_s: float = Field(default=1.0, gt=0.0)
    backoff_cap_s: float = Field(default=60.0, gt=0.0)
    queue_maxsize: int = Field(default=500, ge=1)

    @model_validator(mode="after")
    def _check_backoff(self) -> "TakServerConfig":
        if self.backoff_initial_s > self.backoff_cap_s:
            raise ValueError(
                f"backoff_initial_s ({self.backoff_initial_s}) must be <= "
                f"backoff_cap_s ({self.backoff_cap_s})"
            )
        return self


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json: bool = True  # noqa: A003

    # Silence "json shadows BaseModel" warning without changing the public field name.


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    echoshield: EchoshieldConfig = Field(default_factory=EchoshieldConfig)
    sentrycs: SentrycsConfig = Field(default_factory=SentrycsConfig)
    correlator: CorrelatorConfig = Field(default_factory=CorrelatorConfig)
    tak_server: TakServerConfig = Field(default_factory=TakServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @model_validator(mode="after")
    def _check_cert_file(self) -> "GatewayConfig":
        if self.tak_server.use_ssl:
            cf = self.tak_server.cert_file
            if not Path(cf).exists():
                raise ValueError(f"tak_server.cert_file not found: {cf}")
        return self


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} in strings; unset vars → empty string."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config(path: str | Path) -> GatewayConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping (got {type(raw).__name__})")
    expanded = _expand_env(raw)
    # Empty string for cert_password means unset → convert to None
    ts = expanded.get("tak_server") if isinstance(expanded.get("tak_server"), dict) else None
    if ts and ts.get("cert_password") == "":
        ts["cert_password"] = None
    return GatewayConfig.model_validate(expanded)
