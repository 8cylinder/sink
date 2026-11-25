"""Direct tests for the immutable models and the pure loader."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from sink.config.loader import find_config, load
from sink.config.models import Config, Server
from sink.errors import ConfigError, NoDefaultServer, UnknownServer


def document(**server_overrides: Any) -> dict[str, Any]:
    server = {
        "root": "/var/www/demo",
        "default": True,
        "automatic": True,
        "exclude": ["storage/logs"],
        "ssh": [
            {
                "name": "deploy",
                "username": "deploy",
                "server": "example.com",
                "key": "id_rsa",
                "port": 2222,
            }
        ],
        "mysql": [
            {
                "username": "dbuser",
                "password": "secret",
                "db": "demo",
                "hostname": "localhost",
            }
        ],
        "urls": [{"url": "https://example.com"}],
        "actions": {"files": "ls -al"},
    }
    server.update(server_overrides)
    return {
        "project": {
            "name": "demo",
            "root": "project",
            "pulls_dir": "pulls",
            "exclude": [".git", ".env"],
            "actions": {"hello": "echo hi"},
        },
        "servers": {"dev": server},
    }


def write_config(
    tmp_path: Path, data: dict[str, Any], *, name: str = "sink.yaml"
) -> Path:
    root = tmp_path / name.replace(".yaml", "")
    (root / "project").mkdir(parents=True)
    (root / "pulls").mkdir()
    (root / "id_rsa").write_text("key\n")
    path = root / name
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_find_config_walks_up_from_a_subdirectory(tmp_path: Path) -> None:
    path = write_config(tmp_path, document())
    nested = path.parent / "project" / "deeply" / "nested"
    nested.mkdir(parents=True)

    assert find_config(nested) == path
    assert find_config(tmp_path) is None


def test_load_builds_frozen_models(tmp_path: Path) -> None:
    config = load(write_config(tmp_path, document()))

    assert isinstance(config, Config)
    assert config.project.name == "demo"
    assert config.project.root == (config.path.parent / "project").resolve()
    assert config.default_server == "dev"

    server = config.server()
    assert isinstance(server, Server)
    assert server.name == "dev"
    assert server.ssh[0].username == "deploy"
    assert server.ssh[0].port == 2222
    assert server.databases[0].db == "demo"
    assert server.databases[0].port == 3306
    assert server.urls[0].url == "https://example.com"
    assert server.exclude == ("storage/logs",)
    assert server.actions["files"] == "ls -al"
    assert isinstance(server.ssh, tuple)
    assert isinstance(server.databases, tuple)

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.project.name = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        config.servers["prod"] = server  # type: ignore[index]


def test_relative_ssh_key_is_resolved(tmp_path: Path) -> None:
    config = load(write_config(tmp_path, document()))

    assert config.server().ssh[0].key == str(
        (config.path.parent / "id_rsa").resolve()
    )


def test_excluded_combines_project_and_server(tmp_path: Path) -> None:
    config = load(write_config(tmp_path, document()))

    assert config.excluded("dev") == (
        ".env",
        ".git",
        "storage/logs",
    )


def test_server_lookup_errors(tmp_path: Path) -> None:
    config = load(write_config(tmp_path, document()))

    with pytest.raises(UnknownServer) as error:
        config.server("nope")
    assert "dev" in str(error.value)

    no_default = load(
        write_config(tmp_path, document(default=False), name="nodefault.yaml")
    )
    with pytest.raises(NoDefaultServer):
        no_default.server()


def test_multiple_defaults_are_rejected(tmp_path: Path) -> None:
    data = document(
        default=True,
        ssh=[{"username": "deploy", "server": "example.com"}],
    )
    data["servers"]["prod"] = dict(data["servers"]["dev"])

    with pytest.raises(ConfigError) as error:
        load(write_config(tmp_path, data))
    assert "dev" in str(error.value)
    assert "prod" in str(error.value)


def test_missing_root_is_a_config_error(tmp_path: Path) -> None:
    data = document()
    del data["project"]["root"]

    with pytest.raises(ConfigError) as error:
        load(write_config(tmp_path, data))
    assert "project.root" in str(error.value)
    assert "sink.yaml" in str(error.value)


def test_bad_yaml_is_a_config_error(tmp_path: Path) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    path = root / "sink.yaml"
    path.write_text("project: [unterminated\n")

    with pytest.raises(ConfigError) as error:
        load(path)
    assert "sink.yaml" in str(error.value)


def test_unknown_keys_are_collected_as_warnings(tmp_path: Path) -> None:
    data = document()
    data["bogus"] = True
    data["project"]["other"] = "ignored"

    config = load(write_config(tmp_path, data))

    assert any('"bogus"' in warning for warning in config.warnings)
    assert any('"other"' in warning for warning in config.warnings)


def test_environment_variables_expand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINK_TEST_NAME", "expanded")
    data = document()
    data["project"]["name"] = "${SINK_TEST_NAME}"

    config = load(write_config(tmp_path, data))

    assert config.project.name == "expanded"
    assert config.raw["project"]["name"] == "expanded"


def test_missing_environment_variable_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SINK_MISSING_ROOT", raising=False)
    data = document()
    data["project"]["root"] = "${SINK_MISSING_ROOT}"

    with pytest.raises(ConfigError) as error:
        load(write_config(tmp_path, data))
    assert "SINK_MISSING_ROOT" in str(error.value)


def test_missing_ssh_key_warns_and_is_not_fatal(tmp_path: Path) -> None:
    data = document(ssh=[{"username": "deploy", "server": "e", "key": "gone"}])

    config = load(write_config(tmp_path, data))

    assert config.server().ssh[0].key is None
    assert any("gone" in warning for warning in config.warnings)
