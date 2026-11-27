"""Real rsync transfers against the Docker server."""

from __future__ import annotations

import uuid

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_rsync_rejects_an_unknown_host_key(
    live_project, tmp_path, monkeypatch
) -> None:
    empty = tmp_path / "empty-known-hosts"
    empty.write_text("")
    empty.chmod(0o600)
    project = live_project(ssh_overrides={"known_hosts": str(empty)})
    monkeypatch.setenv("SINK_TEST_KNOWN_HOSTS", str(empty))

    result = project.invoke(
        "file", "put", "dev", "project/index.html", "--real"
    )

    assert result.exit_code != 0, combined(result)
    text = combined(result)
    assert (
        "Host key verification failed" in text
        or "REMOTE HOST IDENTIFICATION HAS CHANGED" in text
    )
    assert not project.remote_exists("index.html")


def test_file_put_and_pull(live_project) -> None:
    project = live_project()

    result = project.invoke(
        "file", "put", "dev", "project/index.html", "--real"
    )
    assert result.exit_code == 0, combined(result)
    assert project.remote_read("index.html") == "local index\n"

    project.remote_write("index.html", "remote index\n")
    result = project.invoke(
        "file", "pull", "dev", "project/index.html", "--real"
    )
    assert result.exit_code == 0, combined(result)
    assert (project.path / "project" / "index.html").read_text() == (
        "remote index\n"
    )


def test_directory_put_honors_exclusions(live_project) -> None:
    project = live_project()
    excluded = project.path / "project" / "storage" / "logs" / "app.log"
    excluded.parent.mkdir(parents=True)
    excluded.write_text("do not upload\n")

    result = project.invoke("file", "put", "dev", "project", "--real")

    assert result.exit_code == 0, combined(result)
    assert project.remote_exists("index.html")
    assert project.remote_exists("sub/file.txt")
    assert not project.remote_exists("storage/logs/app.log")


def test_dry_run_does_not_mutate_the_remote(live_project) -> None:
    project = live_project()

    result = project.invoke("file", "put", "dev", "project/index.html")

    assert result.exit_code == 0, combined(result)
    assert not project.remote_exists("index.html")


def test_warn_declined_does_not_overwrite(live_project) -> None:
    project = live_project(warn=True)

    result = project.invoke(
        "file",
        "put",
        "dev",
        "project/index.html",
        "--real",
        input="n\n",
    )

    assert result.exit_code == 0, combined(result)
    assert not project.remote_exists("index.html")


def test_whole_project_pull_requires_confirmation(
    live_project, monkeypatch
) -> None:
    project = live_project()
    monkeypatch.setattr("sink.rsync._stdin_is_tty", lambda: True)

    result = project.invoke("file", "pull", "dev", "--real", input="n\n")

    assert result.exit_code != 0, combined(result)
    assert "Pull cancelled" in combined(result)


def test_directory_pull_updates_local_files(live_project) -> None:
    project = live_project()
    put = project.invoke("file", "put", "dev", "project", "--real")
    assert put.exit_code == 0, combined(put)

    project.remote_write("sub/file.txt", "remote sub\n")
    result = project.invoke(
        "file", "pull", "dev", "project", "--real", "--force"
    )

    assert result.exit_code == 0, combined(result)
    local = project.path / "project" / "sub" / "file.txt"
    assert local.read_text() == "remote sub\n"


def test_file_put_preserves_the_source_mode(live_project) -> None:
    project = live_project()
    local = project.path / "project" / "index.html"
    local.chmod(0o600)

    result = project.invoke(
        "file", "put", "dev", "project/index.html", "--real"
    )

    assert result.exit_code == 0, combined(result)
    mode = project.sandbox.exec(
        "server", "stat", "-c", "%a", project.remote_path("index.html")
    ).stdout.strip()
    assert mode == "600"


def test_chown_flags_only_appear_when_configured(live_project) -> None:
    plain = live_project()
    result = plain.invoke("file", "put", "dev", "project/index.html")
    text = combined(result)
    assert "--chown" not in text
    assert "--owner" not in text
    assert "--group" not in text

    configured = live_project(
        server_overrides={"user": "deploy", "group": "deploy"}
    )
    result = configured.invoke("file", "put", "dev", "project/index.html")
    text = combined(result)
    assert "--chown=deploy:deploy" in text
    assert "--owner" in text
    assert "--group" in text


def test_transfers_leave_unrelated_files_alone(live_project) -> None:
    project = live_project()
    project.remote_write("unrelated.txt", "keep\n")
    local_unrelated = project.path / "project" / "unrelated-local.txt"
    local_unrelated.write_text("local\n")

    put = project.invoke("file", "put", "dev", "project/index.html", "--real")
    assert put.exit_code == 0, combined(put)
    assert project.remote_read("unrelated.txt") == "keep\n"

    pull = project.invoke("file", "pull", "dev", "project/index.html", "--real")
    assert pull.exit_code == 0, combined(pull)
    assert local_unrelated.read_text() == "local\n"
    assert project.remote_read("unrelated.txt") == "keep\n"


def test_remote_symlinked_directory_is_replaced_not_followed(
    live_project,
) -> None:
    project = live_project()
    outside = f"/var/www/sink-outside-{uuid.uuid4().hex[:12]}"
    project.sandbox.exec(
        "server", "install", "-d", "-o", "deploy", "-g", "deploy", outside
    )
    project.sandbox.exec(
        "server",
        "ln",
        "-s",
        outside,
        project.remote_path("sub"),
        user="deploy",
    )

    result = project.invoke("file", "put", "dev", "project", "--real")

    assert result.exit_code == 0, combined(result)
    leaked = project.sandbox.exec(
        "server", "ls", "-A", outside, user="deploy"
    ).stdout.strip()
    assert leaked == ""
    assert project.remote_read("sub/file.txt") == "local sub\n"
