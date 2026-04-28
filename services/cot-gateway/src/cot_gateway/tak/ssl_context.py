"""SSL context for TAK Server connection (p12 → PEM → SSLContext)."""

from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path

from cot_gateway.config import TakServerConfig


def build_ssl_context(cfg: TakServerConfig) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = cfg.use_ssl_verify
    ctx.verify_mode = ssl.CERT_REQUIRED if cfg.use_ssl_verify else ssl.CERT_NONE

    cert_path = Path(cfg.cert_file)
    if not cert_path.exists():
        raise FileNotFoundError(f"cert_file not found: {cert_path}")

    if cert_path.suffix.lower() in (".pem", ".crt"):
        # Direct PEM load (no cryptography dep needed)
        ctx.load_cert_chain(certfile=str(cert_path), password=cfg.cert_password or None)
        return ctx

    # p12 path → decode via cryptography → temp PEM files
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import pkcs12

    p12_bytes = cert_path.read_bytes()
    pwd = cfg.cert_password.encode() if cfg.cert_password else None
    key, cert, chain = pkcs12.load_key_and_certificates(p12_bytes, pwd)

    with (
        tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cf,
        tempfile.NamedTemporaryFile(delete=False, suffix=".key") as kf,
    ):
        if cert is None or key is None:
            raise ValueError("p12 missing cert or key")
        cf.write(cert.public_bytes(serialization.Encoding.PEM))
        if chain:
            for c in chain:
                cf.write(c.public_bytes(serialization.Encoding.PEM))
        kf.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        cert_file, key_file = cf.name, kf.name

    os.chmod(key_file, 0o600)
    ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
    return ctx
