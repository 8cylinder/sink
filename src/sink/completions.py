"""Static bash completion generation.

The generated script contains only command/option metadata; it never runs
Python or the app at tab-press time.
"""

from __future__ import annotations

import os
import shlex
import tempfile
from collections.abc import Iterable
from pathlib import Path

import click


def _commands(
    group: click.Group, prefix: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], click.Command]]:
    """Yield every non-hidden command path and command."""
    commands = []
    for name, command in group.commands.items():
        if command.hidden:
            continue
        path = (*prefix, name)
        commands.append((path, command))
        if isinstance(command, click.Group):
            commands.extend(_commands(command, path))
    return commands


def _shell_words(values: Iterable[object]) -> str:
    """Quote completion words for a bash ``compgen`` list."""
    return " ".join(shlex.quote(str(value)) for value in values)


def _context(command: click.Command, path: tuple[str, ...]) -> click.Context:
    """Build a Click context without disturbing the help-option cache."""
    # Click 8.5 caches the first help option it builds on the command.  A
    # bare Context defaults to ["--help"]; pass the command's configured
    # names so generating completions never strips "-h" from later parsing.
    names = command.context_settings.get("help_option_names", ["--help"])
    return click.Context(
        command,
        info_name=path[-1] if path else "sink",
        help_option_names=list(names),
    )


def _option_data(
    command: click.Command, path: tuple[str, ...]
) -> tuple[list[str], dict[str, list[str]], bool]:
    """Collect option names and choice values for one command."""
    ctx = _context(command, path)
    options: list[str] = []
    choices: dict[str, list[str]] = {}
    for parameter in command.get_params(ctx):
        if not isinstance(parameter, click.Option) or parameter.hidden:
            continue
        names = [*parameter.opts, *parameter.secondary_opts]
        options.extend(names)
        parameter_type = parameter.type
        if isinstance(parameter_type, click.Choice):
            for name in names:
                choices[name] = list(parameter_type.choices)
    return options, choices, False


def _argument_data(
    command: click.Command, path: tuple[str, ...]
) -> tuple[dict[int, list[str]], set[int]]:
    """Collect positional choices and path positions."""
    ctx = _context(command, path)
    choices: dict[int, list[str]] = {}
    paths: set[int] = set()
    index = 0
    for parameter in command.get_params(ctx):
        if not isinstance(parameter, click.Argument):
            continue
        parameter_type = parameter.type
        if isinstance(parameter_type, click.Choice):
            choices[index] = list(parameter_type.choices)
        elif isinstance(parameter_type, (click.Path, click.File)):
            paths.add(index)
        index += 1
    return choices, paths


def generate_bash(group: click.Group, prog_name: str, version: str) -> str:
    """Return the complete static bash completion script."""
    commands = _commands(group)
    groups = {
        " ".join(path): command
        for path, command in commands
        if isinstance(command, click.Group)
    }
    root = group
    all_paths = set(groups) | {" ".join(path) for path, _command in commands}
    subcommands = {
        name: sorted(
            child.name or ""
            for child in command.commands.values()
            if not child.hidden
        )
        for name, command in groups.items()
    }
    root_subs = sorted(
        child.name or "" for child in root.commands.values() if not child.hidden
    )
    subcommands[""] = root_subs

    branches = []
    root_options = [
        "-h",
        "--help",
        "--version",
        "--config",
        "--completions",
        "--color",
        "-q",
        "--quiet",
        "-s",
        "--suppress-commands",
        "--silent",
        "-v",
        "--verbose",
    ]
    root_words = [*root_subs, *root_options]
    branches.append(
        "\n".join(
            [
                "    '')",
                f"      words={shlex.quote(_shell_words(root_words))}",
                '      COMPREPLY=( $(compgen -W "$words" -- "$cur") )',
                '      if [[ "$prev" == --color ]]; then',
                "        COMPREPLY=( $(compgen -W 'auto always never' -- \"$cur\") )",
                "        return",
                "      fi",
                "      ;;",
            ]
        )
    )
    for path, command in commands:
        name = " ".join(path)
        options, choices, _ = _option_data(command, path)
        arg_choices, arg_paths = _argument_data(command, path)
        # Add root-only machine options to the root command.
        if not path:
            options.extend(
                [
                    "--version",
                    "--config",
                    "--completions",
                    "--color",
                    "-q",
                    "--quiet",
                    "-s",
                    "--suppress-commands",
                    "--silent",
                    "-v",
                    "--verbose",
                ]
            )
            choices["--color"] = ["auto", "always", "never"]
        words = [*subcommands.get(name, []), *options]
        branch = [f"    {shlex.quote(name)})"]
        branch.append(f"      words={shlex.quote(_shell_words(words))}")
        branch.append('      COMPREPLY=( $(compgen -W "$words" -- "$cur") )')
        for option, values in choices.items():
            branch.append(
                f'      if [[ "$prev" == {shlex.quote(option)} ]]; then'
            )
            branch.append(
                f"        COMPREPLY=( $(compgen -W "
                f'{shlex.quote(_shell_words(values))} -- "$cur") )'
            )
            branch.append("        return")
            branch.append("      fi")
        for index, values in arg_choices.items():
            branch.append(f"      if (( cword == {index + 1} )); then")
            branch.append(
                f"        COMPREPLY=( $(compgen -W "
                f'{shlex.quote(_shell_words(values))} -- "$cur") )'
            )
            branch.append("        return")
            branch.append("      fi")
        for index in sorted(arg_paths):
            branch.append(f"      if (( cword == {index + 1} )); then")
            branch.append("        _sink_files")
            branch.append("        return")
            branch.append("      fi")
        branch.append("      ;;")
        branches.append("\n".join(branch))

    # The scanner compares "$cmd $word".  The first command has an empty
    # prefix (so its pattern starts with a space); nested commands compare
    # against the already-populated "parent child" path.
    command_cases = "\n".join(
        (
            f'        " {name}") cmd={shlex.quote(name)} ;;'
            if " " not in name
            else f"        {shlex.quote(name)}) cmd={shlex.quote(name)} ;;"
        )
        for name in sorted(all_paths)
        if name
    )
    completion_cases = "\n".join(branches)

    return f"""# bash completion for {prog_name} {version}
# Generated by {prog_name} --completions. Do not edit; regenerate instead.
# Requires bash >= 4.4 for complete -o nosort.
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4) )); then
  printf '%s\\n' '{prog_name} completions require bash >= 4.4' >&2
  return 0 2>/dev/null || exit 0
fi

_sink_files() {{
  if declare -F _filedir >/dev/null; then
    _filedir
  else
    COMPREPLY=( $(compgen -f -- "$cur") )
  fi
}}

_{prog_name}_complete() {{
  local cur prev words cword
  if declare -F _init_completion >/dev/null; then
    _init_completion || return
  else
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    cword=$COMP_CWORD
  fi
  if [[ "$cur" == --*=* ]]; then
    prev="${{cur%%=*}}"
    cur="${{cur#*=}}"
  fi

  local cmd="" i word
  for ((i=1; i<cword; i++)); do
    word="${{COMP_WORDS[i]}}"
    case "$word" in
      -*) continue ;;
    esac
    case "$cmd $word" in
{command_cases}
    esac
  done

  case "$cmd" in
{completion_cases}
    *)
      COMPREPLY=()
      ;;
  esac
}}

complete -o nosort -o bashdefault -o default -F _{prog_name}_complete {prog_name}
"""


def completion_path(prog_name: str) -> Path:
    """Return the per-user completion destination."""
    bash_dir = os.environ.get("BASH_COMPLETION_USER_DIR", "")
    first = next((part for part in bash_dir.split(":") if part), "")
    if first:
        base = Path(first).expanduser()
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = (
            Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
        )
    return (
        base / "bash-completion" / "completions" / f"{prog_name}.bash"
    ).absolute()


def install_bash_completion(
    group: click.Group, prog_name: str, version: str
) -> Path:
    """Write the completion script atomically and return its path."""
    path = completion_path(prog_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    script = generate_bash(group, prog_name, version)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{prog_name}-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(script)
        Path(temporary).chmod(0o644)
        Path(temporary).replace(path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    return path
