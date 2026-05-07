"""Unit tests for tak_connection — TakConnectionConfig + build_ssl_context.

Run BEFORE implementing config.py / ssl_context.py to confirm 100% RED (G1 gate).
"""

from __future__ import annotations

import ssl
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tak_connection import TakConnectionConfig, build_ssl_context


class TestTakConnectionConfig:
    def test_valid_config_all_fields(self):
        cfg = TakConnectionConfig(
            host="192.168.1.100",
            port=8089,
            use_ssl=True,
            use_ssl_verify=False,
            cert_file="cert.p12",
            cert_password="secret",
            ca_bundle="/etc/ssl/certs/ca-bundle.crt",
        )
        assert cfg.host == "192.168.1.100"
        assert cfg.port == 8089
        assert cfg.cert_password == "secret"

    def test_valid_config_defaults(self):
        cfg = TakConnectionConfig(host="myhost")
        assert cfg.port == 8089
        assert cfg.use_ssl is True
        assert cfg.use_ssl_verify is False
        assert cfg.cert_file is None
        assert cfg.cert_password is None
        assert cfg.ca_bundle is None

    def test_missing_host_raises(self):
        with pytest.raises(ValidationError):
            TakConnectionConfig()

    def test_extra_field_raises(self):
        with pytest.raises(ValidationError):
            TakConnectionConfig(host="h", unknown_field="x")

    def test_empty_host_raises(self):
        with pytest.raises(ValidationError):
            TakConnectionConfig(host="")

    def test_port_zero_raises(self):
        with pytest.raises(ValidationError):
            TakConnectionConfig(host="h", port=0)

    def test_port_65536_raises(self):
        with pytest.raises(ValidationError):
            TakConnectionConfig(host="h", port=65536)

    def test_frozen_raises(self):
        cfg = TakConnectionConfig(host="h")
        with pytest.raises((ValidationError, TypeError)):
            cfg.host = "other"

    def test_empty_cert_password_becomes_none(self):
        cfg = TakConnectionConfig(host="h", cert_password="")
        assert cfg.cert_password is None


class TestBuildSslContextPem:
    def test_pem_no_verify(self, tmp_pem_cert):
        cert_path, _key_path = tmp_pem_cert
        cfg = TakConnectionConfig(
            host="h",
            use_ssl_verify=False,
            cert_file=str(cert_path),
        )
        ctx = build_ssl_context(cfg)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_pem_with_verify(self, tmp_pem_cert):
        cert_path, _key_path = tmp_pem_cert
        cfg = TakConnectionConfig(
            host="h",
            use_ssl_verify=True,
            cert_file=str(cert_path),
            ca_bundle=str(cert_path),
        )
        ctx = build_ssl_context(cfg)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED


class TestBuildSslContextCaOnly:
    def test_cert_file_none_returns_ssl_context(self):
        cfg = TakConnectionConfig(host="h", use_ssl=True, cert_file=None)
        result = build_ssl_context(cfg)
        assert isinstance(result, ssl.SSLContext)

    def test_missing_cert_file_raises_file_not_found(self):
        cfg = TakConnectionConfig(host="h", cert_file="/nonexistent/path.p12")
        with pytest.raises(FileNotFoundError) as exc_info:
            build_ssl_context(cfg)
        assert "/nonexistent/path.p12" in str(exc_info.value)


class TestBuildSslContextP12:
    def test_p12_valid_returns_ssl_context(self, tmp_p12_cert):
        p12_path, password = tmp_p12_cert
        cfg = TakConnectionConfig(
            host="h",
            use_ssl_verify=False,
            cert_file=str(p12_path),
            cert_password=password,
        )
        ctx = build_ssl_context(cfg)
        assert isinstance(ctx, ssl.SSLContext)

    def test_p12_malformed_raises_value_error(self, tmp_malformed_p12):
        cfg = TakConnectionConfig(
            host="h",
            cert_file=str(tmp_malformed_p12),
        )
        with pytest.raises((ValueError, Exception)):
            build_ssl_context(cfg)

    def test_p12_cert_none_raises_value_error(self, tmp_p12_cert):
        p12_path, password = tmp_p12_cert
        cfg = TakConnectionConfig(
            host="h",
            cert_file=str(p12_path),
            cert_password=password,
        )
        with patch(
            "tak_connection.ssl_context.pkcs12.load_key_and_certificates",
            return_value=(None, None, []),
        ):
            with pytest.raises(ValueError, match="p12 missing cert or key"):
                build_ssl_context(cfg)
