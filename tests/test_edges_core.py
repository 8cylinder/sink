"""Edge coverage for applications, init, SSH, and UI helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from sink.applications import Applications
from sink.config.loader import load
from sink.config.models import Server, SSHConfig
from sink.init import Init
from sink.ssh import SSH
from sink.ui import ui


def test_applications_render_all_clients(project_factory) -> None:
    project = project_factory(
        extra_servers={
            "prod": {
                "root": "/var/www/prod",
                "automatic": False,
                "ssh": [],
                "mysql": [],
                "urls": [],
            }
        }
    )
    config = load(project.path / "sink.yaml")
    app = Applications(config)

    assert app.known() == "mysql, filezilla, nautilus, dbeaver"
    assert app.name("missing") is False
    assert "mysql" in app.known()

    assert app.name("mysql") is True
    assert "Password" in app.app_settings()

    app.name("filezilla")
    assert "SFTP" in app.app_settings()
    app.name("nautilus")
    assert "sftp://" in app.app_settings()
    app.name("dbeaver")
    assert "DBeaver" not in app.app_settings()
    assert "Main tab" in app.app_settings()


def test_applications_require_selection(project_factory) -> None:
    config = load(project_factory().path / "sink.yaml")
    app = Applications(config)

    with pytest.raises(ValueError):
        app.app_settings()


def test_init_template_with_and_without_servers() -> None:
    default = Init().create()
    assert "project-name-here" in default
    assert "example_server" in default

    init = Init()
    init.servers(("dev", "prod"))
    custom = init.create()
    assert "dev:" in custom
    assert "prod:" in custom


def test_ssh_helpers(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("key")
    server = Server(
        name="dev",
        root=Path("/var/www/demo"),
        ssh=(
            SSHConfig(
                username="deploy",
                server="example.com",
                key=str(key),
                port=2222,
            ),
        ),
    )
    ssh = SSH(server, dry_run=True)

    assert ssh.real is False
    ssh.visit_ssh()
    ssh.scp_put(tmp_path / "file")
    ssh.scp_pull("/remote/file", tmp_path)
    assert "-i" in ssh.get_key()


def test_ssh_errors(tmp_path: Path) -> None:
    missing = Server(
        name="dev",
        root=Path("/var/www"),
        ssh=(
            SSHConfig(
                username="u",
                server="h",
                key=str(tmp_path / "missing"),
            ),
        ),
    )
    with pytest.raises(FileNotFoundError):
        SSH(missing, dry_run=True).get_key()

    with pytest.raises(SystemExit):
        SSH(Server(name="empty"), dry_run=True)

    with pytest.raises(SystemExit):
        SSH(
            Server(
                name="dev",
                ssh=(SSHConfig(username="u", server="h"),),
            ),
            user="nope",
            dry_run=True,
        )


def test_ui_helpers(capsys) -> None:
    ui.configure(color="never", quiet=0, verbose=1)
    ui.heading("heading", underline=True)
    ui.msg(" one \n two ")
    ui.notice("notice")
    ui.warn("warn", indent="  ")
    ui.error("error", exit=False)
    ui.echo("plain")
    ui.output("output\n")
    ui.output("")
    ui.display_cmd("rsync a b", indent=2, secrets=("secret",))
    ui.display_cmd("hidden", suppress_commands=True)
    ui.display_success(False)
    ui.display_success(True, server="dev", message="upload complete")
    ui.display_success(True, extra="extra")
    ui.display_success(True, message="message")
    ui.display_options({"a": "b"})
    ui.print_stack()
    assert ui.redact("a secret b", ("secret",)) == "a ******** b"
    with ui.status("working"):
        pass
    assert "heading" in capsys.readouterr().out

    ui.configure(color="auto", quiet=2)
    ui.heading("hidden")
    ui.msg("hidden")
    ui.notice("hidden")
    ui.warn("hidden")
    ui.error("hidden", exit=False)
    ui.echo("hidden")
    ui.output("hidden")
    ui.display_cmd("hidden")
    ui.display_success(True)
    ui.display_options({"a": "b"})
    ui.print_stack()
    with ui.status("hidden"):
        pass
