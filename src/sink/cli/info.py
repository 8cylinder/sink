"""The ``sink info`` command and config editor."""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path

import click
import yaml

from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.config.models import Config
from sink.runtime import Runtime
from sink.ui import ui

# Free-form keys in control_panel and hosting are not schema-validated.  A
# key such as "pass" must be treated as a credential even though it is not
# named password or secret.
_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "api_key",
    "api-key",
    "apikey",
    "private_key",
)
_SENSITIVE_TOKENS = frozenset({"pass", "pwd", "passphrase", "pin"})
_MIN_SECRET_LENGTH = 4
_KEY_LINE = re.compile(
    r"^(?P<indent>\s*)(?P<key>-?\s*[^:#][^:]*?):(?P<rest>.*)$"
)
_EMPTY_VALUES = frozenset({"", '""', "''", "null", "Null", "NULL", "~"})


def _key_name(key: str) -> str:
    """Return a YAML key without a list-item marker or surrounding space."""
    return key.removeprefix("-").strip()


def _sensitive_key(key: str) -> bool:
    """Return whether a config key name looks like credential material."""
    lowered = key.lower()
    if any(part in lowered for part in _SENSITIVE_SUBSTRINGS):
        return True
    tokens = re.split(r"[^a-z0-9]+", lowered)
    return any(token in _SENSITIVE_TOKENS for token in tokens)


def _collect_secret_values(config: Config) -> tuple[str, ...]:
    """Collect configured values that must be redacted from output."""
    values: set[str] = set()

    def walk(value: object) -> None:
        """Visit a config fragment and collect secret values."""
        if isinstance(value, Mapping):
            for key, item in value.items():
                if (
                    isinstance(key, str)
                    and isinstance(item, str)
                    and item
                    and (key.lower() == "note" or _sensitive_key(key))
                ):
                    values.add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(config.raw)
    # Longest first so a value that contains another secret is replaced
    # before the shorter substring.
    return tuple(sorted(values, key=len, reverse=True))


def _redact_values(text: str, secrets: tuple[str, ...]) -> str:
    """Replace known secret values in arbitrary config text."""
    for secret in secrets:
        if len(secret) >= _MIN_SECRET_LENGTH:
            text = text.replace(secret, "********")
        # A multi-line note may be rendered as a quoted or folded scalar.
        # Redact each substantive line as a backstop when the key-based pass
        # cannot see through the YAML quoting.
        if "\n" in secret:
            for line in secret.splitlines():
                part = line.strip()
                if len(part) >= _MIN_SECRET_LENGTH:
                    text = text.replace(part, "********")
    return text


def _redact_yaml(text: str, config: Config) -> str:
    """Redact secret keys, notes, and known values from raw YAML text.

    A line-based pass preserves comments and formatting.  It handles block
    scalars such as ``note: |`` that a value-only replacement cannot match
    because the raw file contains indentation and not the unfolded string.
    """
    output: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _KEY_LINE.match(line)
        if match is not None:
            key = match.group("key")
            name = _key_name(key)
            rest = match.group("rest")
            if name.lower() == "note" or _sensitive_key(name):
                stripped = rest.strip()
                if stripped.startswith(("|", ">")):
                    indent = len(match.group("indent"))
                    output.append(f'{match.group("indent")}{key}: "********"')
                    index += 1
                    # Consume the block scalar body: every non-empty line
                    # indented farther than the key belongs to the value.
                    while index < len(lines):
                        candidate = lines[index]
                        if not candidate.strip():
                            index += 1
                            continue
                        candidate_indent = len(candidate) - len(
                            candidate.lstrip()
                        )
                        if candidate_indent <= indent:
                            break
                        index += 1
                    continue
                if stripped not in _EMPTY_VALUES:
                    output.append(f'{match.group("indent")}{key}: "********"')
                    index += 1
                    continue
        output.append(line)
        index += 1

    redacted = "\n".join(output)
    if text.endswith("\n"):
        redacted += "\n"
    return _redact_values(redacted, _collect_secret_values(config))


def _stdin_is_tty() -> bool:
    """Return whether stdin is an interactive terminal."""
    return bool(sys.stdin.isatty())


def _confirm_show_secrets(yes: bool) -> None:
    """Warn and confirm before printing raw secret values."""
    if yes:
        ui.warn("Showing secret values because --yes was passed.")
        return
    if not _stdin_is_tty():
        ui.error(
            "Refusing to show secrets without a terminal; pass --yes to confirm."
        )
    if not click.confirm("Show secret values?", default=False):
        ui.error("Cancelled.")
    ui.warn("Showing secret values.")


def edit_config(path: Path) -> None:
    """Edit and validate the config, offering a retry on YAML errors."""
    click.edit(filename=str(path))
    try:
        with path.open() as stream:
            yaml.safe_load(stream)
    except yaml.YAMLError as error:
        if hasattr(error, "problem_mark"):
            msg = "There was an error while parsing the config file"
            if getattr(error, "context", None) is not None:
                ui.error(
                    f"{msg}:\n{error.problem_mark}\n"
                    f"{getattr(error, 'problem', '')} {getattr(error, 'context', '')}.",
                    exit=False,
                )
            else:
                ui.error(
                    f"{msg}:\n{error.problem_mark} {getattr(error, 'problem', '')}.",
                    exit=False,
                )
        else:
            ui.error(
                "Something went wrong while parsing the yaml file.",
                exit=False,
            )

        if click.confirm("\nDo you want to edit the file again?", default=True):
            edit_config(path)


@cli.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.option(
    "--view/--edit", "-v/-e", default=True, help="View or edit config file."
)
@click.option(
    "--show-secrets",
    is_flag=True,
    help="Print secret values instead of redacting them.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Confirm --show-secrets without an interactive prompt.",
)
@click.pass_obj
def info(rt: Runtime, view: bool, show_secrets: bool, yes: bool) -> None:
    """View or edit the config file.

    If edit, it will be opened in the default editor.

    The view mode redacts passwords, tokens, notes, and free-form credential
    keys.  Use --show-secrets to print the raw file.

    To config the default editor, add the following lines to
    ~/.bashrc.  Change the 'program' to editor name.

    \b
    export EDITOR='program'
    export VISUAL='program'
    """
    cfg = rt.config
    if not view:
        edit_config(cfg.path)
        return
    if ui.quiet >= 2:
        return
    if show_secrets:
        _confirm_show_secrets(yes)
        text = cfg.path.read_text()
    else:
        text = _redact_yaml(cfg.path.read_text(), cfg)
    click.echo(text, nl=False)
