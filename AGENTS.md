# AGENTS.md

`sink` is a Python/Click CLI that manages remote website projects (file/db sync, diff, ssh, check) driven by a `sink.yaml` config. It targets Linux remote servers via `rsync`, `ssh`, and `mysql`.

## Commands

- Install deps: `uv sync --all-groups` (uv manages the in-project `.venv`, Python 3.15).
- Run CLI: `uv run sink <command>`.
- Run tests: `uv run pytest -q`.
- Build + install: `uv build`, then `uv tool install --force .` (or `pip install --force-reinstall dist/sink-<version>-py3-none-any.whl`).
- `pyproject.toml` is the only manifest. Hatchling builds `src/sink`; there is no `setup.py` and no Poetry.
- `uv.lock` is tracked and must stay committed. `.python-version` is 3.15.
- Lint/type/coverage gates live in `pyproject.toml`; `make check` runs Ruff, ty, import-linter, and the 90% branch coverage suite. Do not add ad-hoc tool config.

## Critical gotchas

- **Dry-run by default.** Commands that run shell commands print the command and only execute when `--real`/`-r` is passed. Tools with a native dry-run (`rsync --dry-run`) are executed in dry-run mode so their output shows the intended action. Do not assume a command did anything without `--real`.
- **Version is single-sourced.** `pyproject.toml` has the only `version`; `click.version_option(package_name="sink", prog_name="sink")` reads it from installed metadata. Do not add `__version__` or a fallback version constant.
- **`sink.yaml` is gitignored** and found by walking up from CWD. Commands fail with "You are not in a project" if no config is found. Create one with `uv run sink misc init > sink.yaml`.
- The tool shells out to real `rsync`/`ssh`/`mysql` against remote servers; only run destructive commands with `--real` when intended.
- The legacy `vm` group, `sink/vm.py`, and `sink/resources/Vagrantfile` were removed. Do not reintroduce them; VM provisioning is out of scope (see D7 in `MODERNIZE.plan.org`).
- Configuration is loaded into immutable typed models by `src/sink/config/loader.py`; commands receive a `Runtime` through `ctx.obj`. Do not reintroduce a global config singleton.

## Layout

- `src/sink/cli/` — Click command tree and entrypoint (`sink.cli:main`), one module per command group.
- `src/sink/config/` — typed models and the pure YAML loader (`models.py`, `loader.py`).
- `src/sink/runtime.py` — lazy config, cwd, and output flags.
- `src/sink/shell.py`, `credentials.py` — argv execution and out-of-band database credentials.
- `src/sink/rsync.py`, `db.py`, `ssh.py`, `check.py`, `actions.py`, `applications.py` — per-feature logic.
- `src/sink/ui.py`, `completions.py`, `logging.py` — Rich output, static completions, and diagnostics.
- Every Python file has a module docstring; classes/functions are documented and tricky control flow is commented. `tests/test_docstrings.py` enforces this.
- `src/sink/__main__.py` — `python -m sink`.
- `tests/` — pytest suite and fixtures.
- `MODERNIZE.plan.org` — staged modernization plan; read it before making structural changes.
