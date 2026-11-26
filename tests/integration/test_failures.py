"""Failure, cleanup, and diagnostic paths against real services."""

from __future__ import annotations

import gzip
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from helpers import combined

pytestmark = pytest.mark.integration


def _update_dump(project, value: str) -> str:
    """Write a gzipped SQL update for the widgets table."""
    dump = project.path / "update.sql.gz"
    dump.write_bytes(
        gzip.compress(
            f"UPDATE widgets SET name='{value}' WHERE id=1;".encode()  # noqa: S608 - test SQL
        )
    )
    return "update.sql.gz"


def _reset_widgets(project) -> None:
    """Restore the shared widgets row before a destructive assertion."""
    project.sandbox.db_query("UPDATE widgets SET name='alpha' WHERE id=1")


def _widget_name(project) -> str:
    """Return the current widgets row name."""
    return str(
        project.sandbox.db_query(
            "SELECT name FROM widgets WHERE id = 1"
        ).strip()
    )


def test_restricted_database_user_leaves_no_dump(live_project) -> None:
    project = live_project(
        mysql_username="partial",
        mysql_password="partial",  # noqa: S106 - test fixture
    )

    result = project.invoke("db", "pull", "dev", "--real")

    assert result.exit_code != 0, combined(result)
    assert not (project.path / "pulls" / "LATEST-dev.sql.gz").exists()
    assert not list((project.path / "pulls").glob("demo-dev-*.sql.gz"))
    assert project.sandbox.credentials_files() == []


def test_db_put_rejects_non_gzip_before_touching_the_remote(
    live_project,
) -> None:
    project = live_project()
    _reset_widgets(project)

    result = project.invoke("db", "put", "dev", "project/index.html", "--real")

    assert result.exit_code != 0, combined(result)
    assert "gzip" in combined(result).lower()
    assert project.sandbox.credentials_files() == []
    assert "alpha" in _widget_name(project)


def test_db_put_with_restricted_user_reports_the_error(live_project) -> None:
    project = live_project(
        mysql_username="partial",
        mysql_password="partial",  # noqa: S106 - test fixture
    )
    _reset_widgets(project)
    filename = _update_dump(project, "mutated")

    result = project.invoke("db", "put", "dev", filename, "--real")

    assert result.exit_code != 0, combined(result)
    assert "denied" in combined(result).lower()
    assert "alpha" in _widget_name(project)
    assert project.sandbox.credentials_files() == []


def test_db_put_declined_warning_does_not_overwrite(live_project) -> None:
    project = live_project(warn=True)
    _reset_widgets(project)
    filename = _update_dump(project, "mutated")

    result = project.invoke("db", "put", "dev", filename, "--real", input="n\n")

    assert result.exit_code == 0, combined(result)
    assert "mutated" not in _widget_name(project)
    assert project.sandbox.credentials_files() == []


def test_db_put_confirmed_warning_overwrites(live_project) -> None:
    project = live_project(warn=True)
    _reset_widgets(project)
    filename = _update_dump(project, "mutated")

    result = project.invoke("db", "put", "dev", filename, "--real", input="y\n")

    assert result.exit_code == 0, combined(result)
    assert "mutated" in _widget_name(project)
    assert project.sandbox.credentials_files() == []


def test_unwritable_remote_root_fails_cleanly(live_project) -> None:
    project = live_project()
    project.sandbox.exec("server", "chmod", "500", project.remote_root)
    local = project.path / "project" / "index.html"
    before = local.read_text()

    result = project.invoke(
        "file", "put", "dev", "project/index.html", "--real"
    )

    assert result.exit_code != 0, combined(result)
    assert "denied" in combined(result).lower()
    assert local.read_text() == before
    assert not project.remote_exists("index.html")


def test_mysql_outage_reports_error_and_cleans_credentials(
    live_project,
) -> None:
    project = live_project()
    try:
        project.sandbox.compose_run("stop", "db")

        result = project.invoke("db", "pull", "dev", "--real")

        assert result.exit_code != 0, combined(result)
        assert not (project.path / "pulls" / "LATEST-dev.sql.gz").exists()
        assert not list((project.path / "pulls").glob("demo-dev-*.sql.gz"))
        assert project.sandbox.credentials_files() == []
    finally:
        project.sandbox.compose_run("start", "db")
        project.sandbox.wait_for_db()


def test_check_probes_every_database_and_filters_servers(
    live_project,
) -> None:
    project = live_project(
        extra_databases=[
            {
                "username": "nopriv",
                "password": "wrong",
                "db": "demo",
                "hostname": "db",
            }
        ],
        extra_servers={
            "other": {
                "root": "/var/www/sink-other",
                "ssh": [],
            }
        },
    )

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "DB(demo) as sink" in text
    assert "DB(demo) as nopriv" in text
    assert "Access denied" in text or "ERROR 1045" in text
    assert "other" not in text


def test_check_reports_a_missing_pulls_directory(live_project) -> None:
    project = live_project(project_overrides={"pulls_dir": "missing"})

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "pulls_dir" in text
    assert "missing" in text
    assert "[✗]" in text
    assert "ssh login good" in text


class _OkHandler(BaseHTTPRequestHandler):
    """A tiny HTTP server that answers every request with 200."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output quiet."""
        _ = format, args


def test_check_reports_a_missing_remote_root(live_project) -> None:
    project = live_project(
        server_overrides={"root": "/var/www/sink-missing-root"}
    )

    result = project.invoke("check", "dev")

    assert result.exit_code == 0, combined(result)
    text = combined(result)
    assert "root dir does not exist" in text
    assert "[✗]" in text


def test_check_url_success_and_failure(live_project) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    # Keep the port reserved but not listening so the connection is refused
    # instead of racing another process for the same number.
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    bad_port = closed.getsockname()[1]

    try:
        good_port = httpd.server_address[1]
        project = live_project(
            urls=[
                {"url": f"http://127.0.0.1:{good_port}/"},
                {"url": f"http://127.0.0.1:{bad_port}/"},
            ]
        )

        result = project.invoke("check", "dev")

        assert result.exit_code == 0, combined(result)
        text = combined(result)
        assert f"[✓] URL(http://127.0.0.1:{good_port}/)" in text
        assert f"[✗] URL(http://127.0.0.1:{bad_port}/)" in text
    finally:
        closed.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
