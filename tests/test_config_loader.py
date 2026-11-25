"""Loader behavior, expressed through the public CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from helpers import combined, commands_named, unwrap

from sink.cli import cli as sink


def test_valid_config_resolves_relative_paths_and_ssh_key(
    project_factory,
) -> None:
    project = project_factory()
    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    args = rsync[0].args

    assert f"{project.path / 'project'}/" in args
    assert "--rsh" in args
    rsh = args[args.index("--rsh") + 1]
    assert f"-i {project.path / 'id_rsa'}" in rsh
    assert "-p 2222" in rsh
    assert "deploy@example.com:/var/www/demo" in args
    assert rsync[0].dry_run


def test_db_pull_uses_the_configured_pulls_dir(project_factory) -> None:
    project = project_factory()
    result = project.invoke("db", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    assert "pulls/demo-dev-" in unwrap_output(result)


def test_missing_ssh_key_warns_but_keeps_the_config(project_factory) -> None:
    project = project_factory(
        server_overrides={
            "ssh": [
                {
                    "username": "deploy",
                    "server": "example.com",
                    "key": "missing_key",
                }
            ]
        }
    )
    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert "ssh key does not exist: missing_key" in combined(result)


def test_missing_project_root_is_a_clear_config_error(project_factory) -> None:
    project = project_factory(project_overrides={"root": None})
    result = project.invoke("file", "put", "dev")

    assert result.exit_code != 0
    text = combined(result)
    assert "ConfigError" in text
    assert "project.root" in text
    assert "sink.yaml" in text


def test_bad_yaml_is_reported_as_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "bad-yaml"
    root.mkdir()
    (root / "sink.yaml").write_text("project: [unterminated\n")
    monkeypatch.chdir(root)

    result = CliRunner().invoke(sink, ["misc", "api", "project", "name"])

    assert result.exit_code != 0
    text = combined(result)
    assert "ConfigError" in text
    assert "sink.yaml" in text


def test_unknown_keys_warn_and_are_ignored(project_factory) -> None:
    project = project_factory()
    with (project.path / "sink.yaml").open("a") as file:
        file.write("bogus: true\n")

    result = project.invoke("misc", "api", "project", "name")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "Warning" in text
    assert "bogus" in text


def test_environment_variables_are_expanded(
    project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINK_TEST_NAME", "expanded")
    project = project_factory(project_overrides={"name": "${SINK_TEST_NAME}"})

    result = project.invoke("misc", "api", "project", "name")

    assert result.exit_code == 0, combined(result)
    assert result.output.strip() == '"expanded"'


def test_missing_environment_variable_is_a_config_error(
    project_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SINK_MISSING_ROOT", raising=False)
    project = project_factory(
        project_overrides={"root": "${SINK_MISSING_ROOT}"}
    )

    result = project.invoke("file", "put", "dev")

    assert result.exit_code != 0
    text = combined(result)
    assert "ConfigError" in text
    assert "SINK_MISSING_ROOT" in text


def test_unknown_server_lists_known_servers(project_factory) -> None:
    project = project_factory()
    result = project.invoke("file", "put", "nope")

    assert result.exit_code != 0
    text = combined(result)
    assert "UnknownServer" in text
    assert "dev" in text


def test_multiple_default_servers_are_rejected(project_factory) -> None:
    project = project_factory(
        extra_servers={
            "prod": {
                "root": "/var/www/prod",
                "deploy_root": "/var/www/deploys",
                "default": True,
                "automatic": False,
                "ssh": [
                    {
                        "username": "deploy",
                        "server": "prod.example.com",
                    }
                ],
            }
        }
    )
    result = project.invoke("deploy", "-m", "local", "new", "dev")

    assert result.exit_code != 0
    text = combined(result)
    assert "ConfigError" in text
    assert "dev" in text
    assert "prod" in text


def unwrap_output(result) -> str:
    """Return the rendered command with shell continuations joined."""
    return unwrap(result.output)


def test_project_fixture_is_valid_yaml(project_factory) -> None:
    project = project_factory()
    document = yaml.safe_load((project.path / "sink.yaml").read_text())

    assert document["project"]["name"] == "demo"
    assert document["servers"]["dev"]["root"] == "/var/www/demo"
