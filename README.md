# Sink

Sink is a command line tool for syncing files and databases between local
projects and remote website servers. It prints every shell command it would
run and executes exactly that command with `--real`.

## Features

- Transfer files and directories with `rsync`.
- Pull and push MySQL databases with `mysqldump`/`mysql`, optional `pv`, or
  `mysqlpump`.
- Diff a local file against its remote copy.
- Run configured local or remote actions.
- Check SSH, MySQL, URL, TLS, and local-directory configuration.
- Store connection details in one `sink.yaml`.
- Emit JSON for scripts with `misc api`.

Sink does not manage deployments; use your deployment tooling for that.

## Requirements

- Python 3.15 or newer.
- [uv](https://docs.astral.sh/uv/).
- `rsync` and `ssh` on the local machine and remote server.
- `mysql`/`mysqldump` for database commands.
- `pv` is optional; `mysqlpump` is optional for remote progress.
- Bash 4.4 or newer for generated completions. macOS zsh completion is not
  supported.

## Install

```console
git clone git@github.com:8cylinder/sink.git
cd sink
uv sync --all-groups
uv run sink -h
```

Install the command for your user:

```console
uv tool install --editable .
```

Build the wheel and sdist:

```console
uv build
```

## Quick start

Create a config in a project root:

```console
sink misc init > sink.yaml
sink misc init dev stag prod > sink.yaml
```

A minimal `sink.yaml`:

```yaml
project:
  name: example
  root: .
  pulls_dir: pulls
  exclude:
    - .git
    - .env

servers:
  dev:
    root: /var/www/example
    default: yes
    ssh:
      - name: deploy
        username: deploy
        server: example.com
        key: ~/.ssh/id_ed25519
    mysql:
      - username: example
        password: ${DATABASE_PASSWORD}
        db: example
        hostname: localhost
```

Environment references use `${NAME}`. A missing variable is a configuration
error. Extra keys are allowed and ignored by normal commands; `sink check`
reports them as warnings so misspelled Sink keys are still visible. Secrets are redacted from `misc api` and `misc settings` unless
`--show-secrets` is passed.

## Command overview

| Command | Purpose |
|---|---|
| `sink file put\|pull [SERVER] [FILENAME]` | Sync a file, directory, or the whole project. |
| `sink single FILENAME` | Send a file to every automatic server. |
| `sink diff SERVER [FILENAME]` | Compare a local file with its remote copy. |
| `sink db pull\|put SERVER [SQL-GZ]` | Pull or push a gzipped MySQL dump. |
| `sink ssh SERVER [USER]` | Print or open an interactive ssh session. |
| `sink action SERVER [ACTION]` | List or run a configured action. |
| `sink check [SERVER]` | Check project, server, database, and URL settings. |
| `sink info` | View the config; `--edit` opens the editor. |
| `sink misc api` | Read config values as JSON. |
| `sink misc settings` | Print client connection settings. |
| `sink misc pack` | Print a command to archive uncommitted files. |
| `sink misc init` | Print a starter config. |

See [docs/cli.md](docs/cli.md) or `sink COMMAND -h` for the full reference.

## Dry-run and output

Dry-run is the default. Commands with a native dry-run (`rsync --dry-run`)
execute that variant so you can see the intended action. Other commands are
printed and not spawned.

```console
$ sink file put dev index.html
+ rsync --dry-run ... index.html deploy@example.com:/var/www/example/index.html
[Success (DRY RUN)] dev: upload complete
```

Use `--real`/`-r` to execute. The command is printed in both modes.

- `-q` hides the rendered command but keeps command output and success.
- `-qq` hides all output; the exit code is the only signal.
- `-s`/`--suppress-commands` is an alias for `-q`.
- `--silent` is an alias for `-qq`.
- `--color auto|always|never` controls ANSI output.
- `--config` prints the discovered absolute `sink.yaml` path.
- `--completions` writes a static bash completion script and prints its path.
- `-v/--verbose` enables diagnostics.

## Completions

```console
sink --completions
source "$(sink --completions)"
```

The script completes commands, options, choices, and file paths. Project
server names are not completed because the script is static; type them
manually. Regenerate after changing commands or options.

## Documentation

- Command reference: [docs/cli.md](docs/cli.md)
- Configuration: [docs/configuration.md](docs/configuration.md)
- Development: [docs/development.md](docs/development.md)
- Man page: `make man`, then `man -l docs/_build/man/sink.1`

Build HTML docs with `make docs`; serve with `make docs-serve`.

## Development

```console
uv sync --all-groups
make check
make test
```

`make check` runs Ruff formatting/linting, `ty`, import-linter contracts, and
the full branch-coverage suite. The coverage floor is 90%. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

Sink is licensed under the GNU General Public License, version 2 only
(`GPL-2.0-only`). See [LICENSE](LICENSE) for the full text and
[NOTICE](NOTICE) for the copyright notice.

Copyright (C) 2018-2026 Sheldon McGrandle and contributors.

Releases through 0.2.1 were licensed under GPLv3; this and later releases are
licensed under GPL-2.0-only.
