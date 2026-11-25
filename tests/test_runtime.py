"""Runtime laziness, config caching, and explicit injection."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from sink.config.loader import load
from sink.config.models import Config
from sink.errors import NotInProject
from sink.runtime import Runtime
from sink.sink import sink


def test_runtime_does_not_load_config_on_creation(tmp_path: Path) -> None:
    runtime = Runtime.create(cwd=tmp_path)

    assert runtime._config is None
    with pytest.raises(NotInProject):
        _ = runtime.config


def test_runtime_loads_and_caches_config(tmp_path: Path) -> None:
    path = tmp_path / "runtime"
    (path / "project").mkdir(parents=True)
    path.joinpath("sink.yaml").write_text(
        "project:\n  name: demo\n  root: project\nservers:\n  dev:\n"
        "    root: /var/www/demo\n    default: yes\n"
        "    ssh:\n      - username: deploy\n        server: example.com\n"
    )

    runtime = Runtime.create(cwd=path)
    first = runtime.config
    second = runtime.config

    assert first is second
    assert first.project.name == "demo"


def test_config_can_be_injected_into_the_cli(tmp_path: Path) -> None:
    path = tmp_path / "injected"
    (path / "project").mkdir(parents=True)
    config_path = path / "sink.yaml"
    config_path.write_text(
        "project:\n  name: injected\n  root: project\n"
        "servers:\n  dev:\n    root: /var/www/demo\n"
    )
    config = load(config_path)
    runtime = Runtime.with_config(config, cwd=tmp_path)

    result = CliRunner().invoke(
        sink,
        ["misc", "api", "project", "name"],
        obj=runtime,
    )

    assert result.exit_code == 0, result.output + result.stderr
    assert result.output.strip() == '"injected"'


def test_with_config_still_accepts_a_config_type(tmp_path: Path) -> None:
    path = tmp_path / "typed"
    (path / "project").mkdir(parents=True)
    config_path = path / "sink.yaml"
    config_path.write_text(
        "project:\n  name: typed\n  root: project\nservers: {}\n"
    )
    config: Config = load(config_path)

    runtime = Runtime.with_config(config)

    assert runtime.config is config
