"""SEC-18: CI actions are immutable and downloaded tools are verified."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
SHA_REF = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def test_actions_are_pinned_by_commit_sha() -> None:
    offenders: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text())
        for job in document.get("jobs", {}).values():
            for step in job.get("steps", []):
                uses = step.get("uses")
                if (
                    uses
                    and not uses.startswith("./")
                    and not SHA_REF.match(uses)
                ):
                    offenders.append(f"{path.name}: {uses}")
    assert offenders == []


def test_gitleaks_download_is_checksummed() -> None:
    text = (WORKFLOWS / "ci.yml").read_text()

    assert "gitleaks_8.30.1_linux_x64.tar.gz" in text
    assert "sha256sum -c" in text
    assert "| tar" not in text
