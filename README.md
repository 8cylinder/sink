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
  # Create this directory first. Only deployable content belongs here; keep
  # sink.yaml, pulls/, env files, and keys above it.
  root: public
  # Outside root; create it before the first db pull.
  pulls_dir: .sink/pulls
  exclude:
    - .git

servers:
  dev:
    root: /var/www/example
    default: yes
    ssh:
      - name: deploy
        username: deploy
        server: example.com
        key: ~/.ssh/id_ed25519
        known_hosts: ~/.ssh/known_hosts_sink
    mysql:
      - username: example
        password: ${DATABASE_PASSWORD}
        db: example
        hostname: localhost
```

Directory transfers exclude secret material by default: `sink.yaml`,
`pulls/`, `*.sql.gz`, `.env*`, `*.pem`, `*.key`, `id_*`, `.ssh/`, `.git/`,
and cloud credential files. A directory `file put` that contains one of
those paths is refused unless `--allow-secret-files` is passed; explicit
single-file transfers are never filtered. Directory pulls always keep those
exclusions, so a remote cannot overwrite `sink.yaml` or drop a dump into the
working tree. `.git/` and `.sink/` are always excluded. Automatic
`.env.<server>` inclusion is gone.

Rsync runs with `--safe-links`. A directory put also refuses absolute
symlinks or links whose targets leave `project.root`; safe relative in-tree
links are preserved. Pulls ignore remote links that escape the destination.
A failed single-file pull removes only rsync temp files created during that
transfer; pre-existing backups and editor swap files are preserved.

Every non-interactive SSH path uses `StrictHostKeyChecking=yes` and
`BatchMode=yes`; `IdentitiesOnly=yes` is added when a key is configured.
Interactive `sink ssh` also enforces strict host keys. Set
`ssh.known_hosts` to a dedicated file seeded out of band if you do not want
to rely on the default `~/.ssh/known_hosts`. A changed host key stops the
command; verify the new fingerprint before updating the file.

Environment references use `${NAME}`. A missing variable is a configuration
error. Extra keys are allowed and ignored by normal commands; `sink check`
reports them as warnings so misspelled Sink keys are still visible. Secrets are redacted from `misc api` and `misc settings` unless
`--show-secrets` is passed.

## Configuration trust

`sink.yaml` is executable code and credential material. It chooses SSH and
MySQL hosts, identities, URL targets, the rsync binary, the diff tool, and
action commands. Review it before running commands, keep it in a trusted
repository, and restrict write access.

Discovery stops at the nearest `.git` root, or after three parents when there
is no repository, and never walks into `$HOME`, the system temporary
directory, or `/`. Use `--config-file PATH` for a config outside that
boundary. `sink check` prints the resolved path and refuses an untrusted
config (another owner, world-writable, or outside the repository) unless
`--trust-config` is passed. Other commands warn but do not block.

## Command overview

| Command | Purpose |
|---|---|
| `sink file put\|pull [SERVER] [FILENAME]` | Sync a file, directory, or the whole project. |
| `sink diff SERVER [FILENAME]` | Compare a local file with its remote copy. |
| `sink db pull\|put SERVER [SQL-GZ]` | Pull or push a gzipped MySQL dump. |
| `sink ssh SERVER [USER]` | Print or open an interactive ssh session. |
| `sink action SERVER [ACTION]` | List or run a configured action. |
| `sink check [SERVER]` | Check project, server, database, and URL settings; exit non-zero on failure. |
| `sink info` | View the config; `--edit` opens the editor. |
| `sink misc api` | Read config values as JSON. |
| `sink misc settings` | Print client connection settings. |
| `sink misc pack` | Print a command to archive uncommitted files. |
| `sink misc init` | Print a starter config. |

See [docs/cli.md](docs/cli.md) or `sink COMMAND -h` for the full reference.

## Dry-run and output

Dry-run is the default. Commands with a native dry-run (`rsync --dry-run`)
execute that variant so you can see the intended action. Other commands are
printed and not spawned. `sink check` is the exception: its probes are
read-only, so it always executes them and has no `--real` flag. It exits
non-zero if any probe fails, including under `-qq`; pass `--allow-failures`
to keep the old exit-0 behavior. `--json` emits a machine-readable probe
summary for CI.

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

`sink info` redacts passwords, tokens, notes, and free-form credential keys
by default. `--show-secrets` prints the raw file only after a terminal
confirmation; in a non-interactive context pass `--yes` to confirm. `-qq`
suppresses the view entirely.

Local database pulls create dumps with mode `0600` and require the pulls
directory to be `0700`. `db pull` creates a missing `pulls_dir` with `0700`
and refuses a group- or world-accessible directory. Dumps are written to a
`.part` file and renamed only after a successful transfer; a failed,
interrupted, or startup-failed pull leaves no final dump or `.part` and does
not update `LATEST-*`. Local MySQL clients use a `0600` defaults file in a
private temporary directory; Sink does not export `MYSQL_PWD`.

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

Docker-backed tests exercise real SSH, rsync, and MySQL against Ubuntu LTS
containers:

```console
make integration          # latest Ubuntu LTS
make integration-oldest   # oldest supported Ubuntu LTS
make integration-matrix   # oldest and latest
```

They are excluded from `make check` and require Docker Compose plus real
`ssh`, `rsync`, `git`, and `gzip` on the host.

## License

Sink is licensed under the GNU General Public License, version 2 only
(`GPL-2.0-only`). See [LICENSE](LICENSE) for the full text and
[NOTICE](NOTICE) for the copyright notice.

Copyright (C) 2018-2026 Sheldon McGrandle and contributors.

Releases through 0.2.1 were licensed under GPLv3; this and later releases are
licensed under GPL-2.0-only.
