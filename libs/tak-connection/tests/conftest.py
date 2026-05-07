"""Shared pytest fixtures for tak-connection tests."""

from __future__ import annotations

import datetime
import os

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


def _make_cert_and_key():
    """Generate a self-signed cert + key for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "test"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert, key


@pytest.fixture
def tmp_pem_cert(tmp_path):
    """Return (cert_path, key_path). cert_path is a combined PEM (cert + key)."""
    cert, key = _make_cert_and_key()
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + key_pem)
    key_path.write_bytes(key_pem)
    return cert_path, key_path


@pytest.fixture
def tmp_p12_cert(tmp_path):
    """Return (p12_path, password_str) for a P12 archive."""
    cert, key = _make_cert_and_key()
    p12_bytes = pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(b"test"),
    )
    p12_path = tmp_path / "cert.p12"
    p12_path.write_bytes(p12_bytes)
    return p12_path, "test"


@pytest.fixture
def tmp_malformed_p12(tmp_path):
    """Return path to a garbage file that will cause ValueError on P12 decode."""
    p12_path = tmp_path / "malformed.p12"
    p12_path.write_bytes(os.urandom(64))
    return p12_path
