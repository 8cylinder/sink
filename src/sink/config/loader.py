"""The only module that reads ``sink.yaml``.

``find_config`` locates the file; ``load`` parses, validates, expands
environment references, resolves relative paths, and returns immutable
models.  The loader performs no printing and calls no ``sys.exit``.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from sink.config.models import (
    Config,
    DatabaseConfig,
    Project,
    Server,
    SSHConfig,
    URLConfig,
)
from sink.errors import ConfigError

TOP_LEVEL_KEYS = {"project", "servers"}
PROJECT_KEYS = {
    "name",
    "root",
    "pulls_dir",
    "cache_dir",
    "log_dir",
    "rsync_binary",
    "rsync_flags",
    "difftool",
    "exclude",
    "actions",
    "pv",
    "mysqlpump",
    "note",
}
SERVER_KEYS = {
    "type",
    "name",
    "servername",
    "note",
    "root",
    # Legacy deploy_root is accepted and ignored so old configs load cleanly.
    "deploy_root",
    "warn",
    "default",
    "group",
    "user",
    "automatic",
    "control_panel",
    "hosting",
    "ssh",
    "mysql",
    "databases",
    "urls",
    "actions",
    "exclude",
    "mamp",
}
SSH_KEYS = {
    "name",
    "username",
    "password",
    "server",
    "key",
    "port",
    "note",
}
DATABASE_KEYS = {
    "db",
    "username",
    "password",
    "hostname",
    "port",
    "skip_secure_auth",
    "note",
}
URL_KEYS = {
    "url",
    "admin_url",
    "username",
    "password",
    "htusername",
    "htpassword",
    "note",
}
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def find_config(start: Path) -> Path | None:
    """Walk up from ``start`` to find ``sink.yaml``."""
    start = start.resolve()
    for directory in (start, *start.parents):
        candidate = directory / "sink.yaml"
        if candidate.is_file():
            return candidate
    return None


def load(path: Path) -> Config:
    """Parse, validate, and resolve a config file into models."""
    path = path.resolve()
    try:
        document = yaml.safe_load(path.read_text())
    except OSError as error:
        raise ConfigError(f"{path}: {error}") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: {error}") from error

    if document is None:
        raise ConfigError(f"{path}: sink.yaml appears to have no data")
    if not isinstance(document, Mapping):
        raise ConfigError(f"{path}: the top level must be a mapping")

    expanded = _expand_env(document, path)
    warnings: list[str] = []
    _check_unknown(expanded, TOP_LEVEL_KEYS, str(path), warnings)

    project = _project(expanded.get("project"), path, warnings)
    servers = _servers(expanded.get("servers"), path, project, warnings)

    defaults = [server.name for server in servers.values() if server.default]
    if len(defaults) > 1:
        names = ", ".join(sorted(defaults))
        raise ConfigError(
            f"{path}: more than one default server is set ({names})"
        )
    default_server = defaults[0] if defaults else None

    return Config(
        path=path,
        project=project,
        servers=MappingProxyType(servers),
        default_server=default_server,
        raw=MappingProxyType(expanded),
        warnings=tuple(warnings),
    )


def _expand_env(value: Any, path: Path) -> Any:
    """Recursively expand ``${NAME}`` references in YAML values."""
    if isinstance(value, Mapping):
        return {key: _expand_env(item, path) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item, path) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        """Return one environment value or raise a config error."""
        name = match.group(1)
        try:
            return os.environ[name]
        except KeyError:
            raise ConfigError(
                f'{path}: environment variable "${{{name}}}" is not set'
            ) from None

    return ENV_PATTERN.sub(replace, value)


def _project(data: Any, path: Path, warnings: list[str]) -> Project:
    """Build and validate the project section."""
    if not isinstance(data, Mapping):
        raise ConfigError(f"{path}: project section must be a mapping")
    _check_unknown(data, PROJECT_KEYS, f"{path}: project", warnings)

    root_value = data.get("root")
    if root_value is None:
        raise ConfigError(f"{path}: project.root is required")
    root = _resolve_path(root_value, path, "project.root")
    if not root.is_dir():
        raise ConfigError(f"{path}: project.root does not exist: {root}")

    return Project(
        name=_string(data.get("name"), path, "project.name")
        or path.parent.name,
        root=root,
        pulls_dir=_optional_path(
            data.get("pulls_dir"), path, "project.pulls_dir"
        ),
        cache_dir=_optional_path(
            data.get("cache_dir"), path, "project.cache_dir"
        ),
        log_dir=_optional_path(data.get("log_dir"), path, "project.log_dir"),
        rsync_binary=_rsync_binary(data.get("rsync_binary"), path),
        difftool=_string(data.get("difftool"), path, "project.difftool"),
        exclude=_string_tuple(data.get("exclude"), path, "project.exclude"),
        actions=_actions(data.get("actions"), path, "project.actions"),
        pv=_boolean(data.get("pv"), path, "project.pv"),
        mysqlpump=_boolean(data.get("mysqlpump"), path, "project.mysqlpump"),
        note=_string(data.get("note"), path, "project.note"),
    )


def _servers(
    data: Any,
    path: Path,
    project: Project,
    warnings: list[str],
) -> dict[str, Server]:
    """Build every server in the servers section."""
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ConfigError(f"{path}: servers section must be a mapping")

    servers: dict[str, Server] = {}
    for name, raw in data.items():
        if not isinstance(name, str):
            raise ConfigError(f"{path}: server names must be strings")
        if not isinstance(raw, Mapping):
            raise ConfigError(f'{path}: server "{name}" must be a mapping')
        servers[name] = _server(name, raw, path, project, warnings)
    return servers


def _server(
    name: str,
    data: Mapping[str, Any],
    path: Path,
    project: Project,
    warnings: list[str],
) -> Server:
    """Build and validate one server entry."""
    where = f"{path}: servers.{name}"
    _check_unknown(data, SERVER_KEYS, where, warnings)

    ssh_configs = _ssh_configs(data.get("ssh"), path, project, where, warnings)
    databases = _databases(
        data.get("mysql", data.get("databases")), path, where
    )
    urls = _urls(data.get("urls"), path, where)

    return Server(
        name=name,
        root=_optional_remote_path(data.get("root"), path, f"{where}.root"),
        server_type=_string(data.get("type"), path, f"{where}.type"),
        warn=_boolean(data.get("warn"), path, f"{where}.warn"),
        default=_boolean(data.get("default"), path, f"{where}.default"),
        automatic=_boolean(data.get("automatic"), path, f"{where}.automatic"),
        group=_string(data.get("group"), path, f"{where}.group"),
        user=_string(data.get("user"), path, f"{where}.user"),
        ssh=ssh_configs,
        databases=databases,
        urls=urls,
        actions=_actions(data.get("actions"), path, f"{where}.actions"),
        exclude=_string_tuple(data.get("exclude"), path, f"{where}.exclude"),
        mamp=_string(data.get("mamp"), path, f"{where}.mamp"),
        hosting=_mapping(data.get("hosting"), path, f"{where}.hosting"),
        control_panel=_mapping(
            data.get("control_panel"), path, f"{where}.control_panel"
        ),
        note=_string(data.get("note"), path, f"{where}.note"),
    )


def _ssh_configs(
    data: Any,
    path: Path,
    project: Project,
    where: str,
    warnings: list[str],
) -> tuple[SSHConfig, ...]:
    """Build ssh configs and resolve key paths."""
    if data is None:
        return ()
    if not isinstance(data, list):
        raise ConfigError(f"{path}: {where}.ssh must be a list")

    configs = []
    for index, raw in enumerate(data):
        item_where = f"{where}.ssh[{index}]"
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{path}: {item_where} must be a mapping")
        _check_unknown(raw, SSH_KEYS, f"{path}: {item_where}", warnings)
        key = _string(raw.get("key"), path, f"{item_where}.key")
        if key:
            key = _resolve_key(key, path, project, warnings, item_where)
        configs.append(
            SSHConfig(
                name=_string(raw.get("name"), path, f"{item_where}.name"),
                username=_string(
                    raw.get("username"), path, f"{item_where}.username"
                ),
                password=_string(
                    raw.get("password"), path, f"{item_where}.password"
                ),
                server=_string(raw.get("server"), path, f"{item_where}.server"),
                key=key,
                port=_optional_int(raw.get("port"), path, f"{item_where}.port"),
                note=_string(raw.get("note"), path, f"{item_where}.note"),
            )
        )
    return tuple(configs)


def _databases(data: Any, path: Path, where: str) -> tuple[DatabaseConfig, ...]:
    """Build the database list for one server."""
    if data is None:
        return ()
    if not isinstance(data, list):
        raise ConfigError(f"{path}: {where}.mysql must be a list")

    databases = []
    for index, raw in enumerate(data):
        item_where = f"{where}.mysql[{index}]"
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{path}: {item_where} must be a mapping")
        _check_unknown(raw, DATABASE_KEYS, f"{path}: {item_where}", [])
        databases.append(
            DatabaseConfig(
                db=_string(raw.get("db"), path, f"{item_where}.db"),
                username=_string(
                    raw.get("username"), path, f"{item_where}.username"
                ),
                password=_string(
                    raw.get("password"), path, f"{item_where}.password"
                ),
                hostname=_string(
                    raw.get("hostname"), path, f"{item_where}.hostname"
                ),
                port=_optional_int(
                    raw.get("port"), path, f"{item_where}.port", 3306
                ),
                skip_secure_auth=raw.get("skip_secure_auth"),
                note=_string(raw.get("note"), path, f"{item_where}.note"),
            )
        )
    return tuple(databases)


def _urls(data: Any, path: Path, where: str) -> tuple[URLConfig, ...]:
    """Build the URL list for one server."""
    if data is None:
        return ()
    if not isinstance(data, list):
        raise ConfigError(f"{path}: {where}.urls must be a list")

    urls = []
    for index, raw in enumerate(data):
        item_where = f"{where}.urls[{index}]"
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{path}: {item_where} must be a mapping")
        _check_unknown(raw, URL_KEYS, f"{path}: {item_where}", [])
        urls.append(
            URLConfig(
                url=_string(raw.get("url"), path, f"{item_where}.url"),
                admin_url=_string(
                    raw.get("admin_url"), path, f"{item_where}.admin_url"
                ),
                username=_string(
                    raw.get("username"), path, f"{item_where}.username"
                ),
                password=_string(
                    raw.get("password"), path, f"{item_where}.password"
                ),
                htusername=_string(
                    raw.get("htusername"), path, f"{item_where}.htusername"
                ),
                htpassword=_string(
                    raw.get("htpassword"), path, f"{item_where}.htpassword"
                ),
                note=_string(raw.get("note"), path, f"{item_where}.note"),
            )
        )
    return tuple(urls)


def _actions(data: Any, path: Path, where: str) -> Mapping[str, str]:
    """Build an immutable action mapping."""
    if data is None:
        return MappingProxyType({})
    if not isinstance(data, Mapping):
        raise ConfigError(f"{path}: {where} must be a mapping")
    actions = {}
    for name, command in data.items():
        if not isinstance(name, str) or not isinstance(command, str):
            raise ConfigError(f"{path}: {where} entries must be string: string")
        actions[name] = command
    return MappingProxyType(actions)


def _check_unknown(
    data: Mapping[str, Any],
    allowed: set[str],
    where: str,
    warnings: list[str],
) -> None:
    """Collect a warning for each unknown key."""
    for key in data:
        if key not in allowed:
            warnings.append(f'{where}: unknown key "{key}" was ignored')


def _string(value: Any, path: Path, where: str) -> str | None:
    """Validate an optional string value."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{path}: {where} must be a string")
    return value


def _boolean(value: Any, path: Path, where: str) -> bool:
    """Validate YAML-style boolean values."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"yes", "true", "on", "1"}:
            return True
        if lowered in {"no", "false", "off", "0", ""}:
            return False
    raise ConfigError(f"{path}: {where} must be a boolean")


def _optional_int(
    value: Any, path: Path, where: str, default: int | None = None
) -> int | None:
    """Validate an optional integer value."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except TypeError, ValueError:
        raise ConfigError(f"{path}: {where} must be an integer") from None


def _string_tuple(value: Any, path: Path, where: str) -> tuple[str, ...]:
    """Validate a list of non-empty strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list):
        raise ConfigError(f"{path}: {where} must be a list of strings")
    values = []
    for item in value:
        if not isinstance(item, str):
            raise ConfigError(f"{path}: {where} must contain only strings")
        if item:
            values.append(item)
    return tuple(values)


def _mapping(value: Any, path: Path, where: str) -> Mapping[str, object]:
    """Validate and freeze a mapping value."""
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path}: {where} must be a mapping")
    return MappingProxyType(dict(value))


def _resolve_path(value: Any, path: Path, where: str) -> Path:
    """Resolve a path relative to the config file."""
    if not isinstance(value, (str, os.PathLike)):
        raise ConfigError(f"{path}: {where} must be a path")
    candidate = Path(os.path.expanduser(str(value)))
    if not candidate.is_absolute():
        candidate = path.parent / candidate
    return candidate.resolve()


def _optional_path(value: Any, path: Path, where: str) -> Path | None:
    """Resolve an optional local path."""
    if value is None or value == "":
        return None
    return _resolve_path(value, path, where)


def _optional_remote_path(value: Any, path: Path, where: str) -> Path | None:
    """Expand an optional remote path."""
    if value is None or value == "":
        return None
    if not isinstance(value, (str, os.PathLike)):
        raise ConfigError(f"{path}: {where} must be a path")
    return Path(os.path.expanduser(str(value)))


def _resolve_key(
    key: str,
    path: Path,
    project: Project,
    warnings: list[str],
    where: str,
) -> str | None:
    """Resolve an ssh key against the config and project roots."""
    candidate = Path(os.path.expanduser(key))
    # Try the path as written first, then relative to the config file, then
    # relative to the project root.  A missing key is a warning, not a fatal
    # error, so commands still render for inspection.
    candidates = (
        [candidate]
        if candidate.is_absolute()
        else [path.parent / candidate, project.root / candidate]
    )
    for path_candidate in candidates:
        if path_candidate.is_file():
            return str(path_candidate.resolve())
    warnings.append(f"ssh key does not exist: {key} ({where})")
    return None


def _rsync_binary(value: Any, path: Path) -> str:
    """Select a platform-specific rsync binary name."""
    if isinstance(value, Mapping):
        if sys.platform.startswith("linux"):
            key = "linux"
        elif sys.platform == "darwin":
            key = "osx"
        else:
            key = ""
        value = value.get(key) or value.get("linux") or value.get("osx")
    if value is None or value == "":
        return "rsync"
    if not isinstance(value, str):
        raise ConfigError(f"{path}: project.rsync_binary must be a string")
    return value
