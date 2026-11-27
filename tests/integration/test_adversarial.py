"""Hostile filenames, paths, and tags against the real Docker server."""

from __future__ import annotations

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_filenames_with_spaces_and_unicode_round_trip(live_project) -> None:
    project = live_project()
    name = "sp ace-\u00fc.txt"
    local = project.path / "project" / name
    local.write_text("payload\n")

    result = project.invoke("file", "put", "dev", f"project/{name}", "--real")

    assert result.exit_code == 0, combined(result)
    assert project.remote_read(name) == "payload\n"

    project.remote_write(name, "changed\n")
    result = project.invoke("file", "pull", "dev", f"project/{name}", "--real")

    assert result.exit_code == 0, combined(result)
    assert local.read_text() == "changed\n"


def test_paths_outside_the_project_root_are_rejected(live_project) -> None:
    project = live_project()
    outside = project.path / "outside.txt"
    outside.write_text("outside\n")

    result = project.invoke("file", "put", "dev", str(outside), "--real")

    assert result.exit_code != 0, combined(result)
    assert "outside the project root" in combined(result)
    assert not project.remote_exists("outside.txt")

    link = project.path / "project" / "link.txt"
    link.symlink_to(outside)
    result = project.invoke("file", "put", "dev", "project/link.txt", "--real")

    assert result.exit_code != 0, combined(result)
    assert "outside the project root" in combined(result)
    assert not project.remote_exists("link.txt")


def test_shell_syntax_in_a_filename_never_runs(live_project) -> None:
    project = live_project()
    name = "pwn-$(touch sink-pwned).txt"
    (project.path / "project" / name).write_text("payload\n")

    # Whether rsync accepts the name or rejects it, no remote or local shell
    # may evaluate the ``$(...)`` fragment.
    project.invoke("file", "put", "dev", f"project/{name}", "--real")

    remote_home = project.sandbox.exec(
        "server",
        "test",
        "-e",
        "/home/deploy/sink-pwned",
        check=False,
    )
    assert remote_home.returncode != 0
    assert not project.remote_exists("sink-pwned")
    assert not (project.path / "sink-pwned").exists()
    assert not (project.path / "project" / "sink-pwned").exists()


def test_db_pull_tag_cannot_escape_the_pulls_directory(live_project) -> None:
    project = live_project()

    result = project.invoke(
        "db",
        "pull",
        "dev",
        "--tag",
        "../../../escape",
        "--real",
    )

    assert result.exit_code != 0, combined(result)
    assert "tag" in combined(result).lower()
    assert not (project.path / "escape.sql.gz").exists()
    assert not (project.path.parent / "escape.sql.gz").exists()
    assert not list((project.path / "pulls").glob("*escape*"))


def test_database_password_is_never_rendered(live_project) -> None:
    project = live_project()

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert project.db_password not in text
    assert "defaults-extra-file=" in text


def test_nested_symlinks_do_not_escape_on_put(live_project) -> None:
    project = live_project()
    assets = project.path / "project" / "assets"
    assets.mkdir()
    (assets / "abs").symlink_to("/etc/passwd")
    (assets / "rel").symlink_to("../../outside")

    result = project.invoke("file", "put", "dev", "--real")

    assert result.exit_code != 0, combined(result)
    assert "escape the project root" in combined(result)
    assert not project.remote_exists("assets/abs")
    assert not project.remote_exists("assets/rel")
    assert not project.remote_exists("index.html")


def test_pull_ignores_remote_escaping_symlinks(live_project) -> None:
    project = live_project()
    project.remote_write("safe.txt", "safe\n")
    project.sandbox.exec(
        "server",
        "ln",
        "-s",
        "/etc/passwd",
        project.remote_path("abs-link"),
        user="deploy",
    )
    project.sandbox.exec(
        "server",
        "ln",
        "-s",
        "../../outside",
        project.remote_path("rel-link"),
        user="deploy",
    )
    project.sandbox.exec(
        "server",
        "ln",
        "-s",
        "safe.txt",
        project.remote_path("safe-link"),
        user="deploy",
    )

    result = project.invoke("file", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    local = project.path / "project"
    assert not (local / "abs-link").exists()
    assert not (local / "abs-link").is_symlink()
    assert not (local / "rel-link").exists()
    assert not (local / "rel-link").is_symlink()
    assert (local / "safe-link").is_symlink()
    assert (local / "safe-link").resolve() == (local / "safe.txt").resolve()


def test_whole_project_put_refuses_secret_material(live_project) -> None:
    project = live_project()
    root = project.path / "project"
    names = (
        "sink.yaml",
        ".env.prod",
        "pulls/dump.sql.gz",
        "id_ed25519",
        ".ssh/config",
    )
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("secret\n")

    result = project.invoke("file", "put", "dev", "--real")

    assert result.exit_code != 0, combined(result)
    assert "secret-looking" in combined(result)
    assert not project.remote_exists("index.html")
    for name in names:
        assert not project.remote_exists(name)


def test_whole_project_pull_does_not_overwrite_local_config(
    live_project,
) -> None:
    project = live_project(project_overrides={"root": "."})
    local_config = project.path / "sink.yaml"
    before = local_config.read_text()
    project.remote_write("sink.yaml", "project: {}\n")
    project.remote_write(".env.prod", "TOKEN=remote\n")

    result = project.invoke("file", "pull", "dev", "--real")

    assert result.exit_code == 0, combined(result)
    assert local_config.read_text() == before
    assert not (project.path / ".env.prod").exists()


def test_hostile_server_name_keeps_dumps_inside_pulls(live_project) -> None:
    name = "../../escape"
    project = live_project(server_name=name)

    result = project.invoke("db", "pull", name, "--real")

    assert result.exit_code == 0, combined(result)
    pulls = project.path / "pulls"
    dumps = list(pulls.glob("*.sql.gz"))
    assert dumps
    assert all(dump.resolve().parent == pulls.resolve() for dump in dumps)
    latest = list(pulls.glob("LATEST-*.sql.gz"))
    assert latest
    assert latest[0].is_symlink()
    assert latest[0].resolve().parent == pulls.resolve()
