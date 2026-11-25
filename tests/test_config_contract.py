"""Stage 5 structural contract: no mutable global config."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "sink"
LEGACY_IMPORT = re.compile(r"from\s+sink\.config\s+import\s+(?!models|loader)")


def sources() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py"))


@pytest.mark.xfail(
    strict=True,
    reason="Stage 5: remove the untyped Dict2obj container",
)
def test_no_dict2obj_references() -> None:
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in sources()
        if "Dict2obj" in path.read_text()
    ]
    assert offenders == []


@pytest.mark.xfail(
    strict=True,
    reason="Stage 5: delete the Configuration singleton and load_config",
)
def test_no_global_config_singleton() -> None:
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in sources()
        if "config = Configuration()" in path.read_text()
        or "load_config(" in path.read_text()
    ]
    assert offenders == []


def test_only_runtime_imports_the_loader() -> None:
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in sources()
        if path.name != "runtime.py"
        and "sink.config.loader" in path.read_text()
    ]
    assert offenders == []


@pytest.mark.xfail(
    strict=True,
    reason="Stage 5: feature modules must not import the legacy config module",
)
def test_no_legacy_config_imports() -> None:
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in sources()
        if LEGACY_IMPORT.search(path.read_text())
    ]
    assert offenders == []
