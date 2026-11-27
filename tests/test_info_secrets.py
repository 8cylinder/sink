"""SEC-02: sink info redacts secrets and honors quiet modes."""

from __future__ import annotations

from pathlib import Path

from helpers import combined

from sink.cli import info as info_module
from sink.config.loader import load

SENTINELS = (
    "ssh-sentinel",
    "db-sentinel",
    "url-sentinel",
    "ht-sentinel",
    "hosting-sentinel",
    "panel-sentinel",
    "note-sentinel",
)


def _project_with_secrets(project_factory):
    """Return a project whose config contains one of every secret shape."""
    return project_factory(
        server_overrides={
            "note": "note-sentinel",
            "hosting": {"pass": "hosting-sentinel"},
            "control_panel": {"password": "panel-sentinel"},
            "ssh": [
                {
                    "name": "deploy",
                    "username": "deploy",
                    "server": "example.com",
                    "key": "id_rsa",
                    "port": 2222,
                    "password": "ssh-sentinel",
                }
            ],
            "mysql": [
                {
                    "username": "dbuser",
                    "password": "db-sentinel",
                    "db": "demo",
                    "hostname": "localhost",
                    "skip_secure_auth": "",
                }
            ],
            "urls": [
                {
                    "url": "https://example.test",
                    "password": "url-sentinel",
                    "htpassword": "ht-sentinel",
                }
            ],
        }
    )


def test_info_redacts_literal_secrets(project_factory) -> None:
    project = _project_with_secrets(project_factory)

    result = project.invoke("info")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    for sentinel in SENTINELS:
        assert sentinel not in text
    assert text.count("********") >= len(SENTINELS)
    assert "skip_secure_auth" in text
    assert "skip_secure_auth: ********" not in text


def test_info_redacts_known_secret_by_value_elsewhere(project_factory) -> None:
    project = _project_with_secrets(project_factory)
    config_path = project.path / "sink.yaml"
    config_path.write_text(
        config_path.read_text() + "\n# contact db-sentinel for access\n"
    )

    result = project.invoke("info")

    assert result.exit_code == 0, combined(result)
    assert "db-sentinel" not in combined(result)


def test_info_redacts_a_multiline_note(project_factory) -> None:
    project = project_factory(
        server_overrides={"note": "note-sentinel\nsecond line\n"}
    )

    result = project.invoke("info")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "note-sentinel" not in text
    assert "second line" not in text


def test_redact_yaml_handles_block_notes(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config_path = tmp_path / "sink.yaml"
    config_path.write_text(
        "project:\n"
        "  name: demo\n"
        "  root: project\n"
        "servers:\n"
        "  dev:\n"
        "    note: |\n"
        "      note-sentinel\n"
        "      second line\n"
        "    ssh:\n"
        "      - username: deploy\n"
        "        server: example.com\n"
    )
    config = load(config_path)

    redacted = info_module._redact_yaml(config_path.read_text(), config)

    assert "note-sentinel" not in redacted
    assert "second line" not in redacted
    assert 'note: "********"' in redacted


def test_info_double_quiet_prints_nothing(project_factory) -> None:
    project = _project_with_secrets(project_factory)

    result = project.invoke("-qq", "info")

    assert result.exit_code == 0, combined(result)
    assert result.output == ""
    assert result.stderr == ""


def test_info_quiet_prints_redacted_without_pager(
    project_factory, monkeypatch
) -> None:
    project = _project_with_secrets(project_factory)
    called: list[bool] = []

    def fake_pager(*_args, **_kwargs) -> None:
        called.append(True)

    monkeypatch.setattr(info_module.click, "echo_via_pager", fake_pager)

    result = project.invoke("-q", "info")

    assert result.exit_code == 0, combined(result)
    assert called == []
    assert "project:" in result.output
    assert "ssh-sentinel" not in combined(result)


def test_info_does_not_use_a_pager(project_factory, monkeypatch) -> None:
    project = _project_with_secrets(project_factory)

    def fail(*_args, **_kwargs) -> None:
        raise AssertionError("pager used")

    monkeypatch.setattr(info_module.click, "echo_via_pager", fail)

    result = project.invoke("info")

    assert result.exit_code == 0, combined(result)


def test_info_show_secrets_requires_confirmation(
    project_factory, monkeypatch
) -> None:
    project = _project_with_secrets(project_factory)
    monkeypatch.setattr(info_module, "_stdin_is_tty", lambda: True)

    result = project.invoke("info", "--show-secrets", input="n\n")

    assert result.exit_code != 0
    for sentinel in SENTINELS:
        assert sentinel not in combined(result)


def test_info_show_secrets_with_confirmation_prints_sentinel(
    project_factory, monkeypatch
) -> None:
    project = _project_with_secrets(project_factory)
    monkeypatch.setattr(info_module, "_stdin_is_tty", lambda: True)

    result = project.invoke("info", "--show-secrets", input="y\n")

    assert result.exit_code == 0, combined(result)
    assert "ssh-sentinel" in combined(result)
    assert "[Warning]" in result.stderr


def test_info_show_secrets_non_interactive_requires_yes(
    project_factory, monkeypatch
) -> None:
    project = _project_with_secrets(project_factory)
    monkeypatch.setattr(info_module, "_stdin_is_tty", lambda: False)

    result = project.invoke("info", "--show-secrets")

    assert result.exit_code != 0
    assert "--yes" in combined(result)
    for sentinel in SENTINELS:
        assert sentinel not in combined(result)


def test_info_show_secrets_with_yes_prints_sentinel(
    project_factory, monkeypatch
) -> None:
    project = _project_with_secrets(project_factory)
    monkeypatch.setattr(info_module, "_stdin_is_tty", lambda: False)

    result = project.invoke("info", "--show-secrets", "--yes")

    assert result.exit_code == 0, combined(result)
    assert "ssh-sentinel" in combined(result)
    assert "[Warning]" in result.stderr


def test_info_double_quiet_overrides_show_secrets(
    project_factory, monkeypatch
) -> None:
    project = _project_with_secrets(project_factory)
    monkeypatch.setattr(info_module, "_stdin_is_tty", lambda: True)

    result = project.invoke("-qq", "info", "--show-secrets", "--yes")

    assert result.exit_code == 0, combined(result)
    assert result.output == ""
    assert result.stderr == ""
