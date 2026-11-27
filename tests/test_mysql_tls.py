"""SEC-11: MySQL TLS defaults, defaults-file isolation, and deprecation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sink.config.loader import load
from sink.config.models import DatabaseConfig
from sink.credentials import RemoteCredentials, local_mysql_credentials
from sink.db import _client_options
from sink.errors import ConfigError


def _database(**overrides: object) -> DatabaseConfig:
    """Return a database config with sensible defaults."""
    values: dict[str, object] = {
        "db": "demo",
        "username": "deploy",
        "password": "secret",
        "hostname": "db.example.com",
    }
    values.update(overrides)
    return DatabaseConfig(**values)  # ty: ignore[invalid-argument-type]


def test_remote_host_defaults_to_verify_identity() -> None:
    options = _client_options(_database())

    assert "--ssl-mode" in options
    assert "VERIFY_IDENTITY" in options


def test_local_hosts_do_not_force_tls() -> None:
    for hostname in ("localhost", "127.0.0.1", "::1", "", "/run/mysqld.sock"):
        options = _client_options(_database(hostname=hostname))
        assert "--ssl-mode" not in options


def test_configured_tls_options_are_used() -> None:
    options = _client_options(
        _database(
            ssl_mode="REQUIRED",
            ssl_ca="/etc/mysql/ca.pem",
            ssl_cert="/etc/mysql/client.pem",
            ssl_key="/etc/mysql/client-key.pem",
        )
    )

    assert options[options.index("--ssl-mode") + 1] == "REQUIRED"
    assert options[options.index("--ssl-ca") + 1] == "/etc/mysql/ca.pem"
    assert options[options.index("--ssl-cert") + 1] == "/etc/mysql/client.pem"
    assert (
        options[options.index("--ssl-key") + 1] == "/etc/mysql/client-key.pem"
    )


def test_remote_credentials_use_defaults_file_and_tls() -> None:
    credentials = RemoteCredentials(
        ssh=SimpleNamespace(),
        password="secret",  # noqa: S106 - test fixture
        user="deploy",
        host="db.example.com",
        ssl_mode="VERIFY_IDENTITY",
        ssl_ca="/etc/mysql/ca.pem",
    )

    assert credentials.option.startswith("--defaults-file=")
    content = credentials.content
    assert "ssl-mode=VERIFY_IDENTITY" in content
    assert 'ssl-ca="/etc/mysql/ca.pem"' in content


def test_local_credentials_include_tls_options() -> None:
    with local_mysql_credentials(
        password="secret",  # noqa: S106 - test fixture
        host="db.example.com",
        ssl_mode="REQUIRED",
        ssl_ca="/etc/mysql/ca.pem",
        real=True,
    ) as credentials:
        content = credentials.path.read_text()
    assert "ssl-mode=REQUIRED" in content
    assert 'ssl-ca="/etc/mysql/ca.pem"' in content


def test_invalid_ssl_mode_is_rejected(project_factory) -> None:
    project = project_factory(
        server_overrides={
            "mysql": [
                {
                    "username": "u",
                    "password": "p",
                    "db": "demo",
                    "hostname": "db",
                    "ssl_mode": "BOGUS",
                }
            ]
        }
    )

    with pytest.raises(ConfigError, match="ssl_mode"):
        load(project.path / "sink.yaml")


def test_skip_secure_auth_is_deprecated(project_factory) -> None:
    project = project_factory(
        server_overrides={
            "mysql": [
                {
                    "username": "u",
                    "password": "p",
                    "db": "demo",
                    "hostname": "db",
                    "ssl_mode": "DISABLED",
                    "skip_secure_auth": "yes",
                }
            ]
        }
    )

    config = load(project.path / "sink.yaml")

    assert any("skip_secure_auth" in warning for warning in config.warnings)
    assert any("deprecated" in warning for warning in config.warnings)
