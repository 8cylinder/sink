"""SEC-03: directory transfers reject escaping symlinks."""

from __future__ import annotations

import shlex

from helpers import combined, commands_named, unwrap


def _rendered_args(result) -> list[str]:
    """Split the first rendered command from a CLI result."""
    rendered = next(
        line[2:]
        for line in unwrap(combined(result)).splitlines()
        if line.startswith("+ ")
    )
    return shlex.split(rendered)


def _assets(project):
    """Create and return the project's assets directory."""
    assets = project.path / "project" / "assets"
    assets.mkdir()
    return assets


def test_directory_put_rejects_nested_symlink_outside_root(
    project_factory,
) -> None:
    project = project_factory()
    assets = _assets(project)
    (assets / "outside.txt").symlink_to("../../outside.txt")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code != 0, combined(result)
    text = combined(result)
    assert "escape the project root" in text
    assert "assets/outside.txt" in text
    assert "outside.txt" in text
    assert commands_named(project.stub_log, "rsync") == []


def test_directory_put_rejects_nested_symlink_to_outside_directory(
    project_factory,
) -> None:
    project = project_factory()
    outside = project.path / "outside-dir"
    outside.mkdir()
    assets = _assets(project)
    (assets / "out").symlink_to("../../outside-dir")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code != 0, combined(result)
    assert "assets/out" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_directory_put_rejects_absolute_symlink(project_factory) -> None:
    project = project_factory()
    assets = _assets(project)
    (assets / "abs").symlink_to("/etc/passwd")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code != 0, combined(result)
    assert "/etc/passwd" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_directory_put_rejects_symlink_loop(project_factory) -> None:
    project = project_factory()
    assets = _assets(project)
    (assets / "a").symlink_to("b")
    (assets / "b").symlink_to("a")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code != 0, combined(result)
    assert "<unresolvable>" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_directory_put_allows_in_tree_symlink(project_factory) -> None:
    project = project_factory()
    assets = _assets(project)
    (assets / "target.txt").write_text("inside\n")
    (assets / "link.txt").symlink_to("target.txt")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    assert "--safe-links" in rsync[0].args


def test_symlink_inside_git_is_ignored(project_factory) -> None:
    project = project_factory()
    git = project.path / "project" / ".git"
    git.mkdir()
    (git / "link").symlink_to("/etc/passwd")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    assert commands_named(project.stub_log, "rsync")


def test_secret_override_still_rejects_escaping_git_symlink(
    project_factory,
) -> None:
    project = project_factory()
    git = project.path / "project" / ".git"
    git.mkdir()
    (git / "link").symlink_to("/etc/passwd")

    result = project.invoke("file", "put", "dev", "--allow-secret-files")

    assert result.exit_code != 0, combined(result)
    assert "/etc/passwd" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_safe_links_is_present_for_put_pull_and_diff(project_factory) -> None:
    project = project_factory()

    put = project.invoke("file", "put", "dev")
    assert put.exit_code == 0, combined(put)
    assert "--safe-links" in _rendered_args(put)

    pull = project.invoke("file", "pull", "dev")
    assert pull.exit_code == 0, combined(pull)
    assert "--safe-links" in _rendered_args(pull)

    diff = project.invoke("diff", "dev", "project/index.html")
    assert diff.exit_code == 0, combined(diff)
    assert "--safe-links" in _rendered_args(diff)
