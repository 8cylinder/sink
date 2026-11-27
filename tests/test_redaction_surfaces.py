"""SEC-16: central redaction across actions, URLs, check, and misc output."""

from __future__ import annotations

from helpers import combined

from sink.redaction import redact_url


def test_url_redaction_masks_userinfo_and_sensitive_query() -> None:
    redacted = redact_url(
        "https://user:pass@example.test/path?token=sentinel&ok=1"
    )

    assert "user:pass" not in redacted
    assert "sentinel" not in redacted
    assert "********@example.test" in redacted
    assert "token=********" in redacted
    assert "ok=1" in redacted


def test_check_redacts_url_userinfo_and_query(
    project_factory, monkeypatch
) -> None:
    project = project_factory(
        urls=[
            {
                "url": "https://user:pass@example.test/path?token=sentinel",
            }
        ]
    )

    def fake_urlopen(_url, timeout=None, context=None):
        _ = timeout, context
        return object()

    monkeypatch.setattr("sink.check.urllib.request.urlopen", fake_urlopen)

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "user:pass" not in text
    assert "sentinel" not in text
    assert "********@example.test" in text


def test_check_redacts_a_config_secret_in_stderr(project_factory) -> None:
    project = project_factory()

    result = project.invoke(
        "check",
        "dev",
        env={
            "STUB_EXIT_SSH": "1",
            "STUB_ERR_SSH": "access denied for password secret\n",
        },
    )

    assert result.exit_code != 0, combined(result)
    assert "secret" not in combined(result)
    assert "********" in combined(result)


def test_action_listing_hides_commands(project_factory) -> None:
    project = project_factory(project_actions={"hello": "printf sentinel"})

    result = project.invoke("action", "local")

    assert result.exit_code == 0, combined(result)
    assert "hello" in result.output
    assert "sentinel" not in combined(result)
    assert "hidden" in combined(result).lower()


def test_action_listing_can_show_commands(project_factory) -> None:
    project = project_factory(project_actions={"hello": "printf sentinel"})

    result = project.invoke("action", "local", "--show-commands")

    assert result.exit_code == 0, combined(result)
    assert "sentinel" in combined(result)
    assert "may contain secrets" in combined(result)


def test_action_run_redacts_command_and_output(project_factory) -> None:
    project = project_factory(project_actions={"hello": "printf secret"})

    result = project.invoke("action", "local", "hello", "--real")

    assert result.exit_code == 0, combined(result)
    assert "secret" not in combined(result)


def test_misc_api_redacts_a_free_form_pass(project_factory) -> None:
    project = project_factory(
        server_overrides={"control_panel": {"pass": "sentinel"}}
    )

    result = project.invoke(
        "misc", "api", "servers", "dev", "control_panel", "pass"
    )

    assert result.exit_code == 0, combined(result)
    assert result.output.strip() == '"********"'


def test_misc_api_redacts_a_note(project_factory) -> None:
    project = project_factory(server_overrides={"note": "note-sentinel"})

    result = project.invoke("misc", "api", "servers", "dev", "note")

    assert result.exit_code == 0, combined(result)
    assert result.output.strip() == '"********"'
