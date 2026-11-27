"""SEC-13: a whole-project pull needs explicit confirmation or --force."""

from __future__ import annotations

from helpers import combined, commands_named

from sink import rsync as rsync_module


def test_whole_project_pull_requires_confirmation(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    monkeypatch.setattr(rsync_module, "_stdin_is_tty", lambda: True)

    result = project.invoke("file", "pull", "dev", "--real", input="n\n")

    assert result.exit_code != 0, combined(result)
    assert "Pull cancelled" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_whole_project_pull_can_be_confirmed(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    monkeypatch.setattr(rsync_module, "_stdin_is_tty", lambda: True)

    result = project.invoke("file", "pull", "dev", "--real", input="y\n")

    assert result.exit_code == 0, combined(result)
    assert commands_named(project.stub_log, "rsync")


def test_whole_project_pull_non_interactive_requires_force(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    monkeypatch.setattr(rsync_module, "_stdin_is_tty", lambda: False)

    result = project.invoke("file", "pull", "dev", "--real")

    assert result.exit_code != 0, combined(result)
    assert "--force" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_whole_project_pull_force_skips_confirmation(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    monkeypatch.setattr(rsync_module, "_stdin_is_tty", lambda: False)

    result = project.invoke("file", "pull", "dev", "--real", "--force")

    assert result.exit_code == 0, combined(result)
    assert commands_named(project.stub_log, "rsync")


def test_single_file_pull_needs_no_confirmation(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    monkeypatch.setattr(rsync_module, "_stdin_is_tty", lambda: False)

    result = project.invoke(
        "file", "pull", "dev", "project/index.html", "--real"
    )

    assert result.exit_code == 0, combined(result)
    assert commands_named(project.stub_log, "rsync")


def test_dry_run_needs_no_confirmation(project_factory, monkeypatch) -> None:
    project = project_factory()
    monkeypatch.setattr(rsync_module, "_stdin_is_tty", lambda: False)

    result = project.invoke("file", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    assert commands_named(project.stub_log, "rsync")


def test_subdirectory_pull_needs_no_confirmation(
    project_factory, monkeypatch
) -> None:
    project = project_factory()
    monkeypatch.setattr(rsync_module, "_stdin_is_tty", lambda: False)

    result = project.invoke("file", "pull", "dev", "project/sub", "--real")

    assert result.exit_code == 0, combined(result)
    assert commands_named(project.stub_log, "rsync")
