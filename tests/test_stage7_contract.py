"""Stage 7 transfer, diff, and ssh contract tests."""

from __future__ import annotations

from helpers import combined, commands_named, unwrap


def test_file_put_single_token_filename_uses_default(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "project/index.html")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    assert "deploy@example.com:/var/www/demo/index.html" in rsync[0].args


def test_file_put_with_no_tokens_uses_default_and_project(
    project_factory,
) -> None:
    project = project_factory()

    result = project.invoke("file", "put")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    assert f"{project.path / 'project'}/" in rsync[0].args
    assert "deploy@example.com:/var/www/demo" in rsync[0].args


def test_file_put_single_token_server_uses_whole_project(
    project_factory,
) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    assert "deploy@example.com:/var/www/demo" in rsync[0].args


def test_file_diff_is_not_offered(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "diff", "dev", "project/index.html")

    assert result.exit_code != 0


def test_file_put_rejects_a_path_outside_the_project(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev", "outside.txt")

    assert result.exit_code != 0
    assert str(project.path / "project") in combined(result)


def test_file_pull_rejects_a_path_outside_the_project(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "pull", "dev", "outside.txt")

    assert result.exit_code != 0
    assert str(project.path / "project") in combined(result)
    assert "deploy@example.com" not in combined(result)


def test_diff_reports_a_real_git_error(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "diff",
        "dev",
        "project/index.html",
        "--real",
        env={"STUB_EXIT_GIT": "2"},
    )

    assert result.exit_code != 0
    assert "git diff failed" in combined(result)


def test_diff_does_not_use_a_pager_in_a_pipe(project_factory) -> None:
    project = project_factory()

    project.invoke("diff", "dev", "project/index.html", "--real")

    assert "less" not in [
        command.name for command in commands_named(project.stub_log, "less")
    ]


def test_diff_honors_ignore_whitespace(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project/index.html")
    text = unwrap(combined(result))
    assert "--ignore-all-space" not in text

    project.clear_log()
    result = project.invoke(
        "diff", "dev", "project/index.html", "--ignore-whitespace"
    )
    assert "--ignore-all-space" in unwrap(combined(result))


def test_file_put_directory_is_recursive(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev", "project")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert rsync
    assert "--recursive" in rsync[0].args
    assert f"{project.path}/project/" in rsync[0].args


def test_file_pull_directory_is_recursive(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "pull", "dev", "project/sub")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert rsync
    assert "--recursive" in rsync[0].args
    assert "deploy@example.com:/var/www/demo/sub/" in rsync[0].args


def test_diff_directory_uses_compare_dest(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project")

    text = unwrap(combined(result))
    compare = next(
        token for token in text.split() if token.startswith("--compare-dest=")
    )
    assert compare == f"--compare-dest={project.path / 'project'}"


def test_diff_single_file_does_not_use_compare_dest(project_factory) -> None:
    project = project_factory()

    result = project.invoke("diff", "dev", "project/index.html")

    assert "--compare-dest=" not in unwrap(combined(result))


def test_ssh_interactive_command_includes_tty_port_and_key(
    project_factory,
) -> None:
    project = project_factory()

    result = project.invoke("ssh", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    ssh = commands_named(project.stub_log, "ssh")
    assert len(ssh) == 1
    args = ssh[0].args
    assert "-t" in args
    assert "-p" in args and "2222" in args
    assert "-i" in args
    assert args[-1] == "cd /var/www/demo; bash"


def test_remote_action_uses_batch_mode_and_timeout(project_factory) -> None:
    project = project_factory()

    result = project.invoke("action", "dev", "files", "--real")

    assert result.exit_code == 0, combined(result)
    ssh = commands_named(project.stub_log, "ssh")
    assert len(ssh) == 1
    assert "BatchMode=yes" in ssh[0].args
    assert "ConnectTimeout=25" in ssh[0].args
