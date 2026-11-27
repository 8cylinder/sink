"""Immutable configuration models.

These types contain no I/O.  ``sink.config.loader`` builds them from
``sink.yaml`` and feature modules consume the narrow values they need.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from sink.errors import NoDefaultServer, UnknownServer


class Action(Enum):
    """File and database transfer directions."""

    PUT = "put"
    PULL = "pull"
    DIFF = "diff"


@dataclass(frozen=True, slots=True)
class SSHConfig:
    """One ssh account for a server."""

    name: str | None = None
    username: str | None = None
    password: str | None = None
    server: str | None = None
    key: str | None = None
    key_error: str | None = None
    known_hosts: str | None = None
    port: int | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """One MySQL database connection."""

    db: str | None = None
    username: str | None = None
    password: str | None = None
    hostname: str | None = None
    port: int | None = 3306
    skip_secure_auth: str | bool | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class URLConfig:
    """One site URL and its optional credentials."""

    url: str | None = None
    admin_url: str | None = None
    username: str | None = None
    password: str | None = None
    htusername: str | None = None
    htpassword: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ActionConfig:
    """A named action command."""

    name: str
    command: str


@dataclass(frozen=True, slots=True)
class Project:
    """Project-level configuration values."""

    name: str
    root: Path
    pulls_dir: Path | None = None
    cache_dir: Path | None = None
    log_dir: Path | None = None
    rsync_binary: str = "rsync"
    difftool: str | None = None
    exclude: tuple[str, ...] = ()
    actions: Mapping[str, str] = field(default_factory=dict)
    pv: bool = False
    mysqlpump: bool = False
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Server:
    """One remote server configuration."""

    name: str
    root: Path | None = None
    server_type: str | None = None
    warn: bool = False
    default: bool = False
    # Legacy setting from the removed ``single`` command; accepted but unused.
    automatic: bool = False
    group: str | None = None
    user: str | None = None
    ssh: tuple[SSHConfig, ...] = ()
    databases: tuple[DatabaseConfig, ...] = ()
    urls: tuple[URLConfig, ...] = ()
    actions: Mapping[str, str] = field(default_factory=dict)
    exclude: tuple[str, ...] = ()
    mamp: str | None = None
    hosting: Mapping[str, object] = field(default_factory=dict)
    control_panel: Mapping[str, object] = field(default_factory=dict)
    note: str | None = None

    @property
    def servername(self) -> str:
        """Compatibility alias while call sites move to ``name``."""
        return self.name


@dataclass(frozen=True, slots=True)
class Config:
    """A fully loaded configuration snapshot."""

    path: Path
    project: Project
    servers: Mapping[str, Server]
    default_server: str | None = None
    raw: Mapping[str, object] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    unknown_keys: tuple[str, ...] = ()

    def server(self, name: str | None = None) -> Server:
        """Return a named or default server."""
        key = name or self.default_server
        if key is None:
            raise NoDefaultServer(
                "No server was specified and no server is set to default."
            )
        try:
            return self.servers[key]
        except KeyError:
            known = ", ".join(sorted(self.servers)) or "(none)"
            raise UnknownServer(
                f'Server "{key}" does not exist. Known servers: {known}.'
            ) from None

    def excluded(self, name: str | None = None) -> tuple[str, ...]:
        """Combine project and server exclusions."""
        server = self.server(name) if name is not None else None
        values = list(self.project.exclude)
        if server is not None:
            values.extend(server.exclude)
        return tuple(sorted({value for value in values if value}))
