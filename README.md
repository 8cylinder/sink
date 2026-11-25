# Sink

Sink is a command line tool for developers to help build websites. It syncs
files and databases between local and remote servers, diffs files, checks
server configuration, and keeps project connection details in one `sink.yaml`.

## What it does

- Sync files with `rsync`.
- Sync databases with `mysqldump` and `mysql`.
- Diff a local and a remote file.
- Run predefined commands on a server.
- Check SSH, database, URL, and local directory configuration.
- Store project and server data in `sink.yaml`, with `sink misc api` for
  scripts.

## Dry-run is the default

Every command prints the shell command it will run. When the underlying tool
has a native dry-run, Sink uses it so you can see the intended action:

```console
$ sink file put dev index.html
+ rsync --dry-run ... index.html deploy@example.com:/var/www/example/index.html
[Success (DRY RUN)]
```

`rsync --dry-run` is executed by default, so its itemized output shows what
would transfer. Commands without a native dry-run are printed only.

Use `--real` (or `-r`) to execute the command. The command is still printed,
and the printed command is the one that runs.

## Install

Requires Python >= 3.15 and [uv](https://docs.astral.sh/uv/).

```console
git clone git@github.com:8cylinder/sink.git
cd sink
uv sync
uv run sink -h
```

Install the command:

```console
uv tool install --editable .
```

Build the wheel and sdist:

```console
uv build
```

## Configure

Create a starting `sink.yaml` in the project root:

```console
sink misc init > sink.yaml
sink misc init dev stag prod > sink.yaml
```

A minimal configuration:

```yaml
project:
  name: example
servers:
  dev:
    root: /var/www/example
```

## Development

```console
uv sync --all-groups
uv run pytest
```

## License

Sink is licensed under the GNU General Public License, version 2 only
(`GPL-2.0-only`). See [LICENSE](LICENSE) for the full text and
[NOTICE](NOTICE) for the copyright notice.

Copyright (C) 2018-2026 Sheldon McGrandle and contributors.

Releases through 0.2.1 were licensed under GPLv3; this and later releases are
licensed under GPL-2.0-only.
