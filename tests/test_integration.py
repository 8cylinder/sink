"""Opt-in tests that need real binaries, a server, or a network.

The default pytest run excludes the ``integration`` marker.  Run them with:

    uv run pytest -m integration
"""

from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.integration


def test_required_binaries_are_installed() -> None:
    missing = [
        name
        for name in ("bash", "rsync", "ssh", "mysql", "mysqldump", "git")
        if shutil.which(name) is None
    ]
    if missing:
        pytest.skip(f"missing integration binaries: {', '.join(missing)}")
