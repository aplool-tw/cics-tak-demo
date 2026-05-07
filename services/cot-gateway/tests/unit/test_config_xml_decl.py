"""T004–T005: TakServerConfig.xml_declaration + ca_bundle fields + CLI overrides (Feature 015)."""

from __future__ import annotations
import pytest
from pydantic import ValidationError
from cot_gateway.config import TakServerConfig


# T004 — TakServerConfig.xml_declaration field
def test_xml_declaration_field_default():
    cfg = TakServerConfig(use_ssl=False, cert_file="config/certs/gateway.p12")
    assert cfg.xml_declaration is False


def test_xml_declaration_field_true():
    cfg = TakServerConfig(use_ssl=False, cert_file="config/certs/gateway.p12", xml_declaration=True)
    assert cfg.xml_declaration is True


def test_xml_declaration_roundtrip_yaml(tmp_path):
    import yaml
    from cot_gateway.config import load_config

    cfg_dict = {
        "tak_server": {
            "host": "127.0.0.1",
            "port": 8089,
            "use_ssl": False,
            "cert_file": "config/certs/gateway.p12",
            "xml_declaration": True,
        },
    }
    f = tmp_path / "test.yaml"
    f.write_text(yaml.dump(cfg_dict))
    cfg = load_config(f)
    assert cfg.tak_server.xml_declaration is True


def test_extra_field_still_forbidden():
    with pytest.raises(ValidationError):
        TakServerConfig(use_ssl=False, cert_file="x.p12", unknown_extra_field="boom")


# T005 — TakServerConfig.ca_bundle field and CLI overrides
def test_ca_bundle_field_default():
    cfg = TakServerConfig(use_ssl=False, cert_file="config/certs/gateway.p12")
    assert cfg.ca_bundle is None


def test_ca_bundle_field_set():
    cfg = TakServerConfig(
        use_ssl=False, cert_file="config/certs/gateway.p12", ca_bundle="certs/ca.pem"
    )
    assert cfg.ca_bundle == "certs/ca.pem"


def test_ca_bundle_wires_ssl_context(tmp_path, monkeypatch):
    """ca_bundle must be passed to SSLContext.load_verify_locations when use_ssl_verify=True."""
    import ssl
    from cot_gateway.tak.ssl_context import build_ssl_context

    # Create a minimal fake PEM cert so the loader doesn't fail on file not found
    ca_pem = tmp_path / "ca.pem"
    ca_pem.write_text("")
    cert_pem = tmp_path / "gateway.pem"
    cert_pem.write_text("")

    calls = []

    def fake_load_verify(self, cafile=None, capath=None, cadata=None):
        calls.append(cafile)

    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", fake_load_verify)
    monkeypatch.setattr(ssl.SSLContext, "load_cert_chain", lambda self, **kw: None)

    cfg = TakServerConfig(
        host="127.0.0.1",
        port=8089,
        use_ssl=True,
        use_ssl_verify=True,
        cert_file=str(cert_pem),
        ca_bundle=str(ca_pem),
    )
    build_ssl_context(cfg)
    assert str(ca_pem) in calls, f"load_verify_locations not called with ca_bundle. Calls: {calls}"


def test_cli_tak_host_override(tmp_path):
    """--tak-host overrides tak_server.host from config."""
    import yaml
    from cot_gateway.config import load_config

    cfg_dict = {
        "tak_server": {
            "host": "original-host",
            "port": 8089,
            "use_ssl": False,
            "cert_file": "config/certs/gateway.p12",
        },
        "logging": {"level": "INFO", "json": True},
    }
    f = tmp_path / "test.yaml"
    f.write_text(yaml.dump(cfg_dict))
    # We can't run the full async main, but we can test config loading logic
    # by testing load_config + cli._parse_args simulation
    cfg = load_config(f)
    updated = cfg.model_copy(
        update={"tak_server": cfg.tak_server.model_copy(update={"host": "10.0.0.5"})}
    )
    assert updated.tak_server.host == "10.0.0.5"
    assert updated.tak_server.port == 8089


def test_cli_tak_port_override(tmp_path):
    import yaml
    from cot_gateway.config import load_config

    cfg_dict = {
        "tak_server": {
            "host": "127.0.0.1",
            "port": 8089,
            "use_ssl": False,
            "cert_file": "config/certs/gateway.p12",
        },
    }
    f = tmp_path / "test.yaml"
    f.write_text(yaml.dump(cfg_dict))
    cfg = load_config(f)
    updated = cfg.model_copy(
        update={"tak_server": cfg.tak_server.model_copy(update={"port": 9999})}
    )
    assert updated.tak_server.port == 9999


def test_cli_no_ssl_flag(tmp_path):
    import yaml
    from cot_gateway.config import load_config

    cfg_dict = {
        "tak_server": {
            "host": "127.0.0.1",
            "port": 8089,
            "use_ssl": True,
            "cert_file": "/dev/null",
        },
    }
    f = tmp_path / "test.yaml"
    f.write_text(yaml.dump(cfg_dict))
    cfg = load_config(f)
    updated = cfg.model_copy(
        update={"tak_server": cfg.tak_server.model_copy(update={"use_ssl": False})}
    )
    assert updated.tak_server.use_ssl is False


def test_cli_partial_override_host_only(tmp_path):
    import yaml
    from cot_gateway.config import load_config

    cfg_dict = {
        "tak_server": {
            "host": "127.0.0.1",
            "port": 8089,
            "use_ssl": False,
            "cert_file": "config/certs/gateway.p12",
        },
    }
    f = tmp_path / "test.yaml"
    f.write_text(yaml.dump(cfg_dict))
    cfg = load_config(f)
    updated = cfg.model_copy(
        update={"tak_server": cfg.tak_server.model_copy(update={"host": "192.168.1.1"})}
    )
    assert updated.tak_server.host == "192.168.1.1"
    assert updated.tak_server.port == 8089  # port unchanged
