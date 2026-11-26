# Contributing to Sink

## Development setup

Requirements: Python 3.15, uv, and the external tools used by the commands
(`rsync`, `ssh`; `mysql`/`mysqldump` for database work).

```console
git clone git@github.com:8cylinder/sink.git
cd sink
uv sync --all-groups
make hooks
make check
```

`make hooks` installs the gitleaks pre-commit hook. `make check` runs
formatting checks, Ruff, ty, import-linter, and pytest with branch coverage.

## Tests

Tests are hermetic: they use temporary projects, isolated HOME/XDG
directories, and stub executables. Do not add tests that require a real
server or network access unless they are marked `integration`.

- Run everything: `uv run pytest`
- Run a subset without coverage: `uv run pytest --no-cov tests/test_file.py`
- Run opt-in integration tests: `uv run pytest -m integration`

Behavior changes follow the test-first workflow in `MODERNIZE.plan.org`: add a
strict xfail/regression test, prove it fails for the intended reason, then fix
it and remove the marker.

## Code standards

- Python 3.15, PEP 604/585 annotations, `pathlib.Path`, and aware datetimes.
- Every file has a module docstring; public and non-obvious callables are
  documented. `tests/test_docstrings.py` enforces this.
- Ruff, ty, and import-linter are configured in `pyproject.toml`; do not add
  ad-hoc tool configuration.
- Keep the command-transparency contract: one command object renders and
  executes the same argv/pipeline.

## Release gate

Before tagging a release, run:

```console
make check
make secrets
make integration-matrix
```

CI runs the same integration suite on Ubuntu 20.04 and 26.04 as separate
jobs. Both matrix jobs must be green before a release.

## Documentation

Update `README.md`, `docs/`, and `CHANGELOG.md` for user-visible changes.
Build docs with `make docs` and the man page with `make man`.

## License

Contributions are accepted under GPL-2.0-only. See `LICENSE`.
