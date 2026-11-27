"""SEC-12: extra rsync flags use a safe allowlist."""

from __future__ import annotations

import pytest
from helpers import combined, commands_named

DANGEROUS = (
    "--delete",
    "--delete-excluded",
    "--remove-source-files",
    "--rsync-path='touch /tmp/pwned'",
    "--files-from=/etc/passwd",
    "--log-file=/tmp/sink.log",
    "--rsh='ssh -o ProxyCommand=evil'",
    "--copy-links",
)


def test_safe_extra_flags_are_accepted(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "file",
        "put",
        "dev",
        "--extra-flags=--bwlimit=20 --info=progress2",
    )

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert "--bwlimit=20" in rsync[0].args
    assert "--info=progress2" in rsync[0].args
    assert "extra rsync flags" in combined(result)


@pytest.mark.parametrize("flag", DANGEROUS)
def test_dangerous_flags_are_refused(project_factory, flag: str) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev", f"--extra-flags={flag}")

    assert result.exit_code != 0, combined(result)
    assert "dangerous rsync flags" in combined(result).lower()
    assert "--allow-dangerous-rsync" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_unknown_flags_are_refused(project_factory) -> None:
    project = project_factory()

    result = project.invoke("file", "put", "dev", "--extra-flags=--made-up")

    assert result.exit_code != 0, combined(result)
    assert "safe allowlist" in combined(result)
    assert commands_named(project.stub_log, "rsync") == []


def test_operands_are_refused(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "file", "put", "dev", "--extra-flags=some-extra-source"
    )

    assert result.exit_code != 0, combined(result)
    assert "operand" in combined(result).lower()
    assert commands_named(project.stub_log, "rsync") == []


def test_dangerous_override_is_explicit_and_audited(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "file",
        "put",
        "dev",
        "--extra-flags=--delete",
        "--allow-dangerous-rsync",
    )

    assert result.exit_code == 0, combined(result)
    rsync = commands_named(project.stub_log, "rsync")
    assert "--delete" in rsync[0].args
    assert "Allowing dangerous rsync flags" in combined(result)


def test_filter_flags_warn(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "file", "put", "dev", "--extra-flags=--exclude=*.log"
    )

    assert result.exit_code == 0, combined(result)
    assert "filter flags can hide files" in combined(result)
