# Sink

Sink is a command line tool for syncing files and databases with remote
website servers. It renders the shell command for every action, prints it,
and runs exactly that command with `--real`.

```{toctree}
:maxdepth: 2

cli
configuration
development
```

## Quick start

```console
git clone git@github.com:8cylinder/sink.git
cd sink
uv sync --all-groups
uv tool install --editable .
sink misc init > sink.yaml
sink -h
```

Every command is dry-run by default:

```console
sink file put dev index.html
```

`rsync` runs its native `--dry-run` variant by default. Commands without a
native dry-run are printed and not executed. Use `--real`/`-r` to run the
printed command.

## Output levels

- `-q` hides only the rendered command.
- `-qq` hides all output; use the exit code in scripts.
- `-s`/`--suppress-commands` is an alias for `-q`.
- `--silent` is an alias for `-qq`.
- `--color auto|always|never` controls ANSI output.

## Completions

```console
sink --completions
source "$(sink --completions)"
```

The generated bash script contains commands, options, choices, and paths.
It does not complete project server names; type those manually. Bash 4.4 or
newer is required.

## License

GPL-2.0-only. See [LICENSE](https://github.com/8cylinder/sink/blob/master/LICENSE)
and [NOTICE](https://github.com/8cylinder/sink/blob/master/NOTICE).
