"""Pre-modernization reproductions.

Each test asserts the *desired* behavior and is marked ``xfail(strict=True)``.
When a stage fixes the bug the test will XPASS and strict mode will fail,
prompting removal of the marker.
"""

from __future__ import annotations

import pytest


def rendered(result) -> str:
    """Flatten the wrapped command display for substring assertions."""
    return " ".join(result.output.replace("\\", " ").split())


@pytest.mark.xfail(strict=True, reason="B1: DeployViaSymlink uses self.ssh before assignment")
def test_deploy_symlink_init(project_factory):
    project = project_factory()
    result = project.invoke("deploy", "-m", "symlink", "init", "dev")
    assert result.exit_code == 0, result.output


@pytest.mark.xfail(strict=True, reason="B1: DeployViaRename uses self.ssh before assignment")
def test_deploy_rename_init(project_factory):
    project = project_factory()
    result = project.invoke("deploy", "-m", "rename", "init", "dev", "public_html")
    assert result.exit_code == 0, result.output


@pytest.mark.xfail(strict=True, reason="B4: vm check indexes Dict2obj with []")
def test_vm_check_reports_without_crashing(project_factory):
    project = project_factory()
    result = project.invoke("vm", "check", "dev", "localhost", "1.2.3.4")
    assert result.exit_code == 0, result.output


@pytest.mark.xfail(strict=True, reason="B17/N1: single passes the filename as a server name")
def test_single_uses_the_configured_servers(project_factory):
    project = project_factory()
    result = project.invoke("single", "project/index.html")
    assert result.exit_code == 0, result.output


@pytest.mark.xfail(strict=True, reason="B17: single requires a default server even though it scans all servers")
def test_single_does_not_require_a_default_server(project_factory):
    project = project_factory(default=False)
    result = project.invoke("single", "project/index.html")
    assert result.exit_code == 0, result.output


@pytest.mark.xfail(strict=True, reason="B16: file requires SERVER even though help says it is optional")
def test_file_put_uses_the_default_server(project_factory):
    project = project_factory()
    result = project.invoke("file", "put")
    assert result.exit_code == 0, result.output


@pytest.mark.xfail(strict=True, reason="N3: action local crashes when the project has no actions")
def test_action_local_without_project_actions(project_factory):
    project = project_factory()
    result = project.invoke("action", "local")
    assert result.exit_code == 0, result.output


@pytest.mark.xfail(strict=True, reason="N9: action local executes without --real")
def test_action_local_honors_dry_run(project_factory):
    project = project_factory(project_actions={"hello": "touch action-ran"})
    result = project.invoke("action", "local", "hello")
    assert result.exit_code == 0, result.output
    assert not (project.path / "action-ran").exists()


@pytest.mark.xfail(strict=True, reason="N8: deploy local init creates dist/ without --real")
def test_deploy_local_init_honors_dry_run(project_factory):
    project = project_factory()
    result = project.invoke("deploy", "-m", "local", "init", "dev")
    assert result.exit_code == 0, result.output
    assert not (project.path / "dist").exists()


@pytest.mark.xfail(strict=True, reason="N13: db pull renders mysqldump --dry-run, which mysqldump does not support")
def test_db_pull_renders_a_valid_mysqldump_command(project_factory):
    project = project_factory()
    result = project.invoke("db", "pull", "dev")
    assert "mysqldump --dry-run" not in rendered(result)


@pytest.mark.xfail(strict=True, reason="N24: ssh executes by default instead of rendering the command")
def test_ssh_defaults_to_dry_run(project_factory):
    project = project_factory()
    project.invoke("ssh", "dev")
    assert project.stub_log.read_text() == ""


@pytest.mark.xfail(strict=True, reason="N12: file pull outside the project root builds an absolute remote path")
def test_file_pull_outside_the_project_root(project_factory):
    project = project_factory()
    result = project.invoke("file", "pull", "dev", "outside.txt")
    assert "deploy@example.com:/var/www/demo" in rendered(result)
