"""Real Ubuntu and tool versions selected by the matrix."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_ubuntu_and_tool_versions_are_recorded(sandbox) -> None:
    result = sandbox.exec(
        "server",
        "sh",
        "-c",
        ". /etc/os-release; printf '%s\\n' \"$PRETTY_NAME\"; "
        "ssh -V 2>&1; rsync --version 2>&1 | head -n 1; "
        "mysqldump --version 2>&1",
    )

    text = result.stdout
    assert "Ubuntu" in text
    assert sandbox.ubuntu in text
    assert "OpenSSH" in text
    assert "rsync" in text.lower()
    assert "dump" in text.lower()
