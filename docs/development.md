# Development

Sink uses Python 3.15, uv, Ruff, ty, pytest, pytest-cov, and import-linter.

```console
uv sync --all-groups
make check
make test
```

`make check` runs formatting, linting, type checking, import contracts, and
the full branch-coverage suite. The coverage floor is 90%.

Docker-backed integration tests exercise real SSH, rsync, and MySQL against
Ubuntu LTS containers. They are excluded from `make check` and require Docker
Compose, `ssh`, `ssh-keygen`, `rsync`, `git`, and `gzip` on the
host:

```console
make integration          # latest Ubuntu LTS
make integration-oldest   # oldest supported Ubuntu LTS
make integration-matrix   # oldest and latest
```

Run one version directly:

```console
SINK_TEST_UBUNTU=22.04 uv run pytest -m integration tests/integration --no-cov
UBUNTU_VERSIONS="20.04 22.04 24.04 26.04" make integration-matrix
```

The fixture creates an isolated Compose project, ephemeral SSH keys, a
temporary `known_hosts`, and temporary projects, then removes the stack. Use
`make integration-down` to clean up containers left by an interrupted run.

CI runs the integration suite on Ubuntu 20.04 and 26.04 for pull requests;
both matrix jobs must be green before a release.

Build documentation:

```console
make docs
make man
```

`make install-man` installs the generated `sink.1` under
`$XDG_DATA_HOME/man/man1` or `~/.local/share/man/man1`.

Source layout:

- `src/sink/cli/` — Click command modules and entry point.
- `src/sink/config/` — typed models and the pure YAML loader.
- `src/sink/` — runtime, shell execution, credentials, transfers, database,
  check, actions, UI, and completions.
- `tests/` — hermetic pytest suite.

Every source file has a module docstring; callables are documented and
non-obvious control flow is commented. `tests/test_docstrings.py` enforces
this.
