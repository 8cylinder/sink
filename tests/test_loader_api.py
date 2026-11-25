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
        config.project.name = "other"  # ty: ignore[invalid-assignment] - frozen test
    with pytest.raises(TypeError):
        config.servers["prod"] = server  # ty: ignore[invalid-assignment] - frozen mapping


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
    project = config.raw["project"]
    assert isinstance(project, dict)
    assert project["name"] == "expanded"


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


def _copy_document() -> dict[str, Any]:
    import copy

    return copy.deepcopy(document())


def test_loader_rejects_invalid_document_shapes(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    empty_path = empty / "sink.yaml"
    empty_path.write_text("")
    with pytest.raises(ConfigError):
        load(empty_path)

    list_path = tmp_path / "list"
    list_path.mkdir()
    (list_path / "sink.yaml").write_text("- one\n- two\n")
    with pytest.raises(ConfigError):
        load(list_path / "sink.yaml")

    data = _copy_document()
    data["project"] = []
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="project-list.yaml"))


def test_loader_rejects_invalid_project_values(tmp_path: Path) -> None:
    data = _copy_document()
    data["project"]["root"] = 1
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="root-int.yaml"))

    data = _copy_document()
    data["project"]["root"] = "does-not-exist"
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="root-missing.yaml"))

    data = _copy_document()
    data["project"]["pulls_dir"] = []
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="pulls-list.yaml"))

    data = _copy_document()
    data["project"]["exclude"] = 1
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="exclude-int.yaml"))

    data = _copy_document()
    data["project"]["actions"] = []
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="actions-list.yaml"))


def test_loader_rejects_invalid_server_values(tmp_path: Path) -> None:
    data = _copy_document()
    data["servers"] = []
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="servers-list.yaml"))

    data = _copy_document()
    data["servers"]["dev"] = []
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="server-list.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["ssh"] = {}
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="ssh-map.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["ssh"] = [[]]
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="ssh-item-list.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["mysql"] = {}
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="mysql-map.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["mysql"] = [[]]
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="mysql-item-list.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["urls"] = {}
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="urls-map.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["urls"] = [[]]
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="urls-item-list.yaml"))


def test_loader_rejects_invalid_scalar_values(tmp_path: Path) -> None:
    data = _copy_document()
    data["servers"]["dev"]["warn"] = "sometimes"
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="warn-invalid.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["ssh"][0]["port"] = "not-a-port"
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="port-invalid.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["type"] = 1
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="type-int.yaml"))

    data = _copy_document()
    data["servers"]["dev"]["hosting"] = []
    with pytest.raises(ConfigError):
        load(write_config(tmp_path, data, name="hosting-list.yaml"))


def test_loader_resolves_keys_against_project_root(tmp_path: Path) -> None:
    data = _copy_document()
    data["servers"]["dev"]["ssh"][0]["key"] = "project/id_rsa"
    path = write_config(tmp_path, data, name="project-key.yaml")
    (path.parent / "project" / "id_rsa").write_text("key\n")

    config = load(path)

    assert config.server().ssh[0].key == str(
        (path.parent / "project" / "id_rsa").resolve()
    )


def test_loader_expands_nested_env_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINK_ROOT", "project")
    data = _copy_document()
    data["project"]["root"] = "${SINK_ROOT}"
    data["project"]["exclude"] = ["${SINK_ROOT}"]
    path = write_config(tmp_path, data, name="env-nested.yaml")

    config = load(path)

    assert config.project.root == (path.parent / "project").resolve()
    assert config.project.exclude == ("project",)


def test_loader_supports_platform_rsync_mapping(tmp_path: Path) -> None:
    data = _copy_document()
    data["project"]["rsync_binary"] = {"linux": "rsync", "osx": "rsync"}
    path = write_config(tmp_path, data, name="rsync-map.yaml")

    assert load(path).project.rsync_binary == "rsync"


def test_config_excluded_rejects_unknown_server(tmp_path: Path) -> None:
    config = load(write_config(tmp_path, _copy_document(), name="exclude.yaml"))

    with pytest.raises(UnknownServer):
        config.excluded("missing")
