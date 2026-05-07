from __future__ import annotations

import logging
import os
import ssl
import tempfile
from contextlib import suppress
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from tak_connection.config import TakConnectionConfig

log = logging.getLogger(__name__)


def _unlink_if_present(path: str | None) -> None:
    with suppress(TypeError, FileNotFoundError):
        os.unlink(path)


def build_ssl_context(cfg: TakConnectionConfig) -> ssl.SSLContext:
    """Build SSL context for a TAK connection."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = cfg.use_ssl_verify
    ctx.verify_mode = ssl.CERT_REQUIRED if cfg.use_ssl_verify else ssl.CERT_NONE
    if cfg.ca_bundle and cfg.use_ssl_verify:
        ctx.load_verify_locations(cafile=cfg.ca_bundle)

    if cfg.cert_file is None:
        return ctx

    cert_path = Path(cfg.cert_file)
    if not cert_path.exists():
        raise FileNotFoundError(f"cert_file not found: {cert_path}")

    if cert_path.suffix.lower() in (".pem", ".crt"):
        ctx.load_cert_chain(certfile=str(cert_path), password=cfg.cert_password or None)
        return ctx

    p12_bytes = cert_path.read_bytes()
    pwd = cfg.cert_password.encode() if cfg.cert_password else None
    key, cert, chain = pkcs12.load_key_and_certificates(p12_bytes, pwd)
    if cert is None or key is None:
        raise ValueError("p12 missing cert or key")

    cert_tmp = None
    key_tmp = None
    try:
        with (
            tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cf,
            tempfile.NamedTemporaryFile(delete=False, suffix=".key") as kf,
        ):
            cf.write(
                cert.public_bytes(serialization.Encoding.PEM)
                + b"".join(
                    chain_cert.public_bytes(serialization.Encoding.PEM)
                    for chain_cert in chain or ()
                )
            )
            kf.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            cert_tmp = cf.name
            key_tmp = kf.name

        os.chmod(key_tmp, 0o600)
        ctx.load_cert_chain(certfile=cert_tmp, keyfile=key_tmp)
    finally:
        _unlink_if_present(cert_tmp)
        _unlink_if_present(key_tmp)

    return ctx
