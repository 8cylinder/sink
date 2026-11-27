"""SEC-01: directory transfers exclude secret material by default."""

from __future__ import annotations

import shlex

import yaml
from helpers import combined, commands_named, unwrap

from sink.init import Init


def _write_secret_files(project) -> list[str]:
    """Create secret-looking files under the project root."""
    root = project.path / "project"
    files = {
        "sink.yaml": "project: {}\n",
        ".env.prod": "TOKEN=secret\n",
        "pulls/dump.sql.gz": "not really gzip\n",
        "id_ed25519": "key\n",
        ".ssh/config": "Host *\n",
        "sub/.env.dev": "TOKEN=secret\n",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    # The scan reports and prunes secret directories, so pulls and .ssh
    # appear as directory paths while ordinary files appear individually.
    return [
        "sink.yaml",
        ".env.prod",
        "pulls",
        "id_ed25519",
        ".ssh",
        "sub/.env.dev",
    ]


def _rendered_args(result) -> list[str]:
    """Split the rendered rsync command from a CLI result."""
    rendered = next(
        line[2:]
        for line in unwrap(combined(result)).splitlines()
        if line.startswith("+ ")
    )
    return shlex.split(rendered)


def test_directory_put_refuses_secret_files(project_factory) -> None:
    project = project_factory()
    names = _write_secret_files(project)

    result = project.invoke("file", "put", "dev")

    assert result.exit_code != 0, combined(result)
    text = combined(result)
    assert "secret-looking" in text
    for name in names:
        assert name in text
    assert commands_named(project.stub_log, "rsync") == []


def test_directory_put_allows_secret_files_with_override(
    project_factory,
) -> None:
    project = project_factory()
    names = _write_secret_files(project)

    result = project.invoke("file", "put", "dev", "--allow-secret-files")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "Allowing secret-looking files" in text
    for name in names:
        assert name in text
    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    assert "sink.yaml" not in rsync[0].args
    assert ".env*" not in rsync[0].args
    assert ".env.dev" not in rsync[0].args


def test_safe_excludes_come_before_includes(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev")

    assert result.exit_code == 0, combined(result)
    args = _rendered_args(result)
    assert args.index("--exclude") < args.index("--include")
    assert ".env*" in args
    assert "sink.yaml" in args
    assert ".env.dev" not in args


def test_pull_applies_safe_excludes(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    args = _rendered_args(result)
    assert args.index("--exclude") < args.index("--include")
    assert ".env*" in args
    assert "sink.yaml" in args
    assert ".env.dev" not in args


def test_pull_keeps_safe_excludes_with_override(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "pull", "dev", "--allow-secret-files")

    assert result.exit_code == 0, combined(result)
    args = _rendered_args(result)
    assert "sink.yaml" in args
    assert ".env*" in args


def test_pull_excludes_the_configured_pulls_dir(project_factory) -> None:
    project = project_factory(
        project_overrides={"pulls_dir": "project/backups"}
    )

    result = project.invoke("file", "pull", "dev")

    assert result.exit_code == 0, combined(result)
    assert "backups/" in _rendered_args(result)


def test_single_file_put_is_not_filtered(project_factory) -> None:
    project = project_factory()
    secret = project.path / "project" / ".env.prod"
    secret.write_text("TOKEN=secret\n")

    result = project.invoke("file", "put", "dev", "project/.env.prod")

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert len(rsync) == 1
    assert "sink.yaml" not in rsync[0].args
    assert ".env*" not in rsync[0].args


def test_configured_pulls_dir_inside_root_is_refused(project_factory) -> None:
    project = project_factory(
        project_overrides={"pulls_dir": "project/backups"}
    )
    dump = project.path / "project" / "backups" / "dump.sql.gz"
    dump.parent.mkdir(parents=True)
    dump.write_text("dump\n")

    result = project.invoke("file", "put", "dev")

    assert result.exit_code != 0, combined(result)
    assert "project/backups" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_nested_credential_directory_is_refused(project_factory) -> None:
    project = project_factory()
    config = project.path / "project" / "sub" / ".ssh" / "config"
    config.parent.mkdir(parents=True)
    config.write_text("Host *\n")

    result = project.invoke("file", "put", "dev", "project/sub")

    assert result.exit_code != 0, combined(result)
    assert "sub/.ssh" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_init_template_uses_narrow_root_and_secret_defaults() -> None:
    text = Init().create()
    document = yaml.safe_load(text)

    assert document["project"]["root"] == "public"
    assert document["project"]["pulls_dir"] == ".sink/pulls"
    assert "--allow-secret-files" in text
    assert "sink.yaml" in text
