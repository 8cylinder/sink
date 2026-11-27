"""SEC-05: bound config discovery and make the trust boundary visible."""

from __future__ import annotations

from pathlib import Path

import yaml
from helpers import combined, commands_named

from sink.config.loader import find_config, find_repo_root, load
from sink.runtime import config_trust


def _write_config(path: Path, root: Path, name: str = "demo") -> Path:
    """Write a minimal config rooted at *root*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "project": {"name": name, "root": str(root)},
                "servers": {},
            },
            sort_keys=False,
        )
    )
    return path


def test_find_config_stops_at_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "sub").mkdir()
    _write_config(tmp_path / "sink.yaml", repo)

    assert find_config(repo / "sub") is None


def test_find_config_finds_repo_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "sub").mkdir()
    config = _write_config(repo / "sink.yaml", repo)

    assert find_config(repo / "sub") == config


def test_find_config_stops_before_home() -> None:
    home = Path.home()
    sub = home / "project" / "sub"
    sub.mkdir(parents=True)
    _write_config(home / "sink.yaml", sub)

    assert find_config(sub) is None


def test_find_config_is_bounded_without_a_repository(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    config = _write_config(root / "sink.yaml", root)

    near = root / "a" / "b" / "c"
    near.mkdir(parents=True)
    deep = near / "d"
    deep.mkdir()

    assert find_config(near) == config
    assert find_config(deep) is None


def test_find_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "sub").mkdir()

    assert find_repo_root(repo / "sub") == repo
    assert find_repo_root(tmp_path) is None


def test_config_file_option_loads_an_explicit_config(
    project_factory, tmp_path: Path
) -> None:
    project = project_factory()
    external = tmp_path / "external"
    config = _write_config(
        external / "sink.yaml", project.path / "project", name="external"
    )

    result = project.invoke(
        "--config-file", str(config), "misc", "api", "project", "name"
    )

    assert result.exit_code == 0, combined(result)
    assert result.output.strip() == '"external"'


def test_config_option_prints_the_explicit_config(
    project_factory, tmp_path: Path
) -> None:
    project = project_factory()
    external = tmp_path / "external"
    config = _write_config(
        external / "sink.yaml", project.path / "project", name="external"
    )

    result = project.invoke("--config-file", str(config), "--config")

    assert result.exit_code == 0, combined(result)
    assert result.output.strip() == str(config.resolve())


def test_config_trust_accepts_a_normal_project(project_factory) -> None:
    project = project_factory()
    config = load(project.path / "sink.yaml")

    trusted, reason = config_trust(config, project.path)

    assert trusted
    assert reason is None


def test_config_trust_flags_a_config_outside_the_repository(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "sub").mkdir()
    outside = tmp_path / "outside"
    (outside / "project").mkdir(parents=True)
    config = _write_config(outside / "sink.yaml", outside / "project")
    loaded = load(config)

    trusted, reason = config_trust(loaded, repo / "sub")

    assert not trusted
    assert reason is not None
    assert "outside repository" in reason


def test_check_refuses_an_untrusted_config(project_factory) -> None:
    project = project_factory()
    (project.path / "sink.yaml").chmod(0o666)

    result = project.invoke("check", "dev")

    assert result.exit_code != 0
    text = combined(result)
    assert "untrusted" in text.lower()
    assert "--trust-config" in text
    assert project.stub_log.read_text() == ""


def test_check_trust_config_proceeds(project_factory) -> None:
    project = project_factory()
    (project.path / "sink.yaml").chmod(0o666)

    result = project.invoke("check", "dev", "--trust-config")

    assert result.exit_code == 0, combined(result)
    assert project.stub_log.read_text() != ""


def test_check_prints_the_config_path(project_factory) -> None:
    project = project_factory()

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    assert str(project.path / "sink.yaml") in combined(result)


def test_untrusted_real_command_warns_but_runs(project_factory) -> None:
    project = project_factory()
    (project.path / "sink.yaml").chmod(0o666)

    result = project.invoke("file", "put", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    assert "untrusted" in combined(result).lower()
    assert commands_named(project.stub_log, "rsync")


def test_non_default_rsync_binary_warns(project_factory) -> None:
    project = project_factory(
        project_overrides={"rsync_binary": "custom-rsync"}
    )
    (project.bin_dir / "custom-rsync").symlink_to(project.bin_dir / "rsync")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert "configured rsync binary" in combined(result)


def test_configured_difftool_warns(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project/index.html", "--difftool")

    assert result.exit_code == 0, combined(result)
    assert "configured difftool" in combined(result)


def test_configured_action_warns(project_factory) -> None:
    project = project_factory()

    result = project.invoke("action", "dev", "files", "--real")

    assert result.exit_code == 0, combined(result)
    assert "configured action" in combined(result)
