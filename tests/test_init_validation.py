"""SEC-17: generated YAML rejects unsafe server names."""

from __future__ import annotations

import pytest
import yaml
from helpers import combined

from sink.errors import CommandError
from sink.init import Init

HOSTILE = (
    "a\nb",
    "a: b",
    "a#b",
    "a'b",
    "-dev",
    ".dev",
    ".",
    "..",
    "",
    "a b",
)


@pytest.mark.parametrize("name", HOSTILE)
def test_init_rejects_hostile_server_names(name: str) -> None:
    init = Init()

    with pytest.raises(CommandError, match="Invalid server name"):
        init.servers((name,))


def test_init_rejects_duplicate_server_names() -> None:
    init = Init()

    with pytest.raises(CommandError, match="Duplicate server name"):
        init.servers(("dev", "dev"))


def test_init_round_trips_valid_names() -> None:
    init = Init()
    names = ("dev", "prod-1", "a_b", "a.b")
    init.servers(names)

    document = yaml.safe_load(init.create())

    assert set(document["servers"]) == set(names)
    assert set(document) == {"project", "servers"}


def test_misc_init_rejects_a_hostile_name(project_factory) -> None:
    project = project_factory()

    result = project.invoke("misc", "init", "a\nb")

    assert result.exit_code != 0, combined(result)
    assert "Invalid server name" in combined(result)


def test_misc_init_valid_names_round_trip(project_factory) -> None:
    project = project_factory()

    result = project.invoke("misc", "init", "dev", "prod")

    assert result.exit_code == 0, combined(result)
    document = yaml.safe_load(result.output)
    assert set(document["servers"]) == {"dev", "prod"}
