"""TAK SSL context — thin wrapper delegating to libs/tak-connection."""

from __future__ import annotations

import ssl

from cot_gateway.config import TakServerConfig
from tak_connection.config import TakConnectionConfig
from tak_connection.ssl_context import build_ssl_context as _build


def build_ssl_context(cfg: TakServerConfig) -> ssl.SSLContext:
    """Thin wrapper: build TakConnectionConfig and delegate to shared lib."""
    tak_cfg = TakConnectionConfig(
        host=cfg.host,
        port=cfg.port,
        use_ssl=cfg.use_ssl,
        use_ssl_verify=cfg.use_ssl_verify,
        cert_file=cfg.cert_file,
        cert_password=cfg.cert_password,
        ca_bundle=cfg.ca_bundle,
    )
    return _build(tak_cfg)
