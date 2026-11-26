"""Real rsync and git diff behavior against the Docker server."""

from __future__ import annotations

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def test_diff_reports_identical_files(live_project) -> None:
    project = live_project()
    project.remote_write("index.html", "local index\n")

    result = project.invoke("diff", "dev", "project/index.html", "--real")

    assert result.exit_code == 0, combined(result)
    assert "Files are the same." in combined(result)


def test_diff_reports_a_changed_file(live_project, capfd) -> None:
    project = live_project()
    project.remote_write("index.html", "remote index\n")

    result = project.invoke("diff", "dev", "project/index.html", "--real")

    captured = capfd.readouterr()
    assert result.exit_code == 1, combined(result)
    assert "remote index" in captured.out + captured.err


def test_diff_reports_a_missing_remote_file(live_project) -> None:
    project = live_project()

    result = project.invoke("diff", "dev", "project/missing.txt", "--real")

    assert result.exit_code != 0, combined(result)


def test_diff_ignores_whitespace_only_when_requested(live_project) -> None:
    project = live_project()
    (project.path / "project" / "index.html").write_text("alpha beta\n")
    project.remote_write("index.html", "alpha  beta\n")

    plain = project.invoke("diff", "dev", "project/index.html", "--real")
    assert plain.exit_code == 1, combined(plain)

    ignored = project.invoke(
        "diff",
        "dev",
        "project/index.html",
        "--real",
        "--ignore-whitespace",
    )
    assert ignored.exit_code == 0, combined(ignored)
    assert "Files are the same." in combined(ignored)


def test_diff_word_and_letter_options_reach_git(live_project) -> None:
    project = live_project()
    (project.path / "project" / "index.html").write_text("alpha beta\n")
    project.remote_write("index.html", "alpha gamma\n")

    word = project.invoke(
        "diff", "dev", "project/index.html", "--real", "--word-diff", "word"
    )
    assert word.exit_code == 1, combined(word)
    assert "--word-diff=color" in combined(word)

    letter = project.invoke(
        "diff", "dev", "project/index.html", "--real", "--word-diff", "letter"
    )
    assert letter.exit_code == 1, combined(letter)
    assert "--word-diff-regex=." in combined(letter)


def test_directory_diff_uses_the_local_directory_for_compare_dest(
    live_project,
) -> None:
    project = live_project()

    result = project.invoke("diff", "dev", "project")

    assert result.exit_code == 0, combined(result)
    expected = f"--compare-dest={project.path / 'project'}"
    assert expected in combined(result)


def test_difftool_success_and_failure(live_project) -> None:
    ok_project = live_project(
        project_overrides={"difftool": "true {remote} {local}"}
    )
    ok_project.remote_write("index.html", "local index\n")
    ok = ok_project.invoke(
        "diff", "dev", "project/index.html", "--real", "--difftool"
    )
    assert ok.exit_code == 0, combined(ok)

    bad_project = live_project(
        project_overrides={"difftool": "false {remote} {local}"}
    )
    bad_project.remote_write("index.html", "local index\n")
    bad = bad_project.invoke(
        "diff", "dev", "project/index.html", "--real", "--difftool"
    )
    assert bad.exit_code != 0, combined(bad)
    assert "difftool failed" in combined(bad)
