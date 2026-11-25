"""Git hooks tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".githooks" / "pre-commit"


def run_hook(
    tmp_path: Path,
    *,
    version: str | None = "8.30.1",
    missing: bool = False,
    exit_code: int = 0,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_file = tmp_path / "args.txt"
    if not missing:
        stub = bin_dir / "gitleaks"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            'if [ "$1" = "version" ]; then\n'
            f'  echo "{version}"\n'
            "  exit 0\n"
            "fi\n"
            'printf "%s\\n" "$@" > "$STUB_ARGS"\n'
            f"exit {exit_code}\n"
        )
        stub.chmod(0o755)

    env = os.environ.copy()
    if missing:
        # The hook needs `cat` for its error message, but must not find a
        # real gitleaks on PATH.
        (bin_dir / "cat").symlink_to("/bin/cat")
        env["PATH"] = str(bin_dir)
    else:
        env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    env["STUB_ARGS"] = str(args_file)
    return subprocess.run(
        ["/bin/bash", str(HOOK)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_hook_parses() -> None:
    result = subprocess.run(
        ["bash", "-n", str(HOOK)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_missing_gitleaks(tmp_path: Path) -> None:
    result = run_hook(tmp_path, missing=True)
    assert result.returncode == 1
    assert "gitleaks" in result.stderr
    assert "https://github.com/gitleaks/gitleaks#installing" in result.stderr


def test_old_gitleaks_is_rejected(tmp_path: Path) -> None:
    result = run_hook(tmp_path, version="8.16.0")
    assert result.returncode == 1
    assert "8.19" in result.stderr


def test_hook_records_staged_scan_arguments(tmp_path: Path) -> None:
    result = run_hook(tmp_path, version="8.30.1")
    assert result.returncode == 0
    recorded = (tmp_path / "args.txt").read_text().splitlines()
    assert recorded == [
        "git",
        "--staged",
        "--redact",
        "--no-banner",
        "--verbose",
    ]


def test_gitleaks_failure_is_propagated(tmp_path: Path) -> None:
    result = run_hook(tmp_path, exit_code=1)
    assert result.returncode == 1
