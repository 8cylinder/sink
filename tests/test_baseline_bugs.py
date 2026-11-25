"""Pre-modernization reproductions.

Each test asserts the *desired* behavior and is marked ``xfail(strict=True)``.
When a stage fixes the bug the test will XPASS and strict mode will fail,
prompting removal of the marker.
"""

from __future__ import annotations

from click.testing import Result


def rendered(result: Result) -> str:
    """Flatten the wrapped command display for substring assertions."""
    return " ".join(result.output.replace("\\", " ").split())


def test_single_uses_the_configured_servers(project_factory):
    project = project_factory()
    result = project.invoke("single", "project/index.html")
    assert result.exit_code == 0, result.output


def test_single_does_not_require_a_default_server(project_factory):
    project = project_factory(default=False)
    result = project.invoke("single", "project/index.html")
    assert result.exit_code == 0, result.output


def test_file_put_uses_the_default_server(project_factory):
    project = project_factory()
    result = project.invoke("file", "put")
    assert result.exit_code == 0, result.output


def test_action_local_without_project_actions(project_factory):
    project = project_factory()
    result = project.invoke("action", "local")
    assert result.exit_code == 0, result.output


def test_action_local_honors_dry_run(project_factory):
    project = project_factory(project_actions={"hello": "touch action-ran"})
    result = project.invoke("action", "local", "hello")
    assert result.exit_code == 0, result.output
    assert not (project.path / "action-ran").exists()


def test_db_pull_renders_a_valid_mysqldump_command(project_factory):
    project = project_factory()
    result = project.invoke("db", "pull", "dev")
    assert "mysqldump --dry-run" not in rendered(result)


def test_ssh_defaults_to_dry_run(project_factory):
    project = project_factory()
    project.invoke("ssh", "dev")
    assert project.stub_log.read_text() == ""


def test_file_pull_outside_the_project_root(project_factory):
    project = project_factory()
    result = project.invoke("file", "pull", "dev", "outside.txt")
    assert result.exit_code != 0
    assert str(project.path / "project") in rendered(result)
