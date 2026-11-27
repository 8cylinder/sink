"""The ``sink info`` command and config editor."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click
import yaml

from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.config.models import Config
from sink.redaction import (
    collect_secret_values,
    is_sensitive_key,
    redact_values,
)
from sink.runtime import Runtime
from sink.ui import ui

_KEY_LINE = re.compile(
    r"^(?P<indent>\s*)(?P<key>-?\s*[^:#][^:]*?):(?P<rest>.*)$"
)
_EMPTY_VALUES = frozenset({"", '""', "''", "null", "Null", "NULL", "~"})


def _key_name(key: str) -> str:
    """Return a YAML key without a list-item marker or surrounding space."""
    return key.removeprefix("-").strip()


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
            if name.lower() == "note" or is_sensitive_key(name):
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
    return redact_values(redacted, collect_secret_values(config))


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
