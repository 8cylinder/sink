# AGENTS.md

`sink` is a Python/Click CLI that manages remote website projects (file/db sync, diff, deploy, ssh, check) driven by a `sink.yaml` config. It targets Linux remote servers via `rsync`, `ssh`, and `mysql`.

## Commands

- Install deps: `uv sync --all-groups` (uv manages the in-project `.venv`, Python 3.15).
- Run CLI: `uv run sink <command>`.
- Run tests: `uv run pytest -q`.
- Build + install: `uv build`, then `uv tool install --force .` (or `pip install --force-reinstall dist/sink-<version>-py3-none-any.whl`).
- `pyproject.toml` is the only manifest. Hatchling builds `src/sink`; there is no `setup.py` and no Poetry.
- `uv.lock` is tracked and must stay committed. `.python-version` is 3.15.
- Lint/type configuration arrives in Stage 2 of `MODERNIZE.plan.org`; do not add ad-hoc tool config.

## Critical gotchas

- **Dry-run by default.** Commands that run shell commands print the command and only execute when `--real`/`-r` is passed. Tools with a native dry-run (`rsync --dry-run`) are executed in dry-run mode so their output shows the intended action. Do not assume a command did anything without `--real`.
- **Version is single-sourced.** `pyproject.toml` has the only `version`; `click.version_option(package_name="sink", prog_name="sink")` reads it from installed metadata. Do not add `__version__` or a fallback version constant.
- **`sink.yaml` is gitignored** and found by walking up from CWD. Commands fail with "You are not in a project" if no config is found. Create one with `uv run sink misc init > sink.yaml`.
- The tool shells out to real `rsync`/`ssh`/`mysql` against remote servers; only run destructive commands with `--real` when intended.
- The legacy `vm` group, `sink/vm.py`, and `sink/resources/Vagrantfile` were removed. Do not reintroduce them; VM provisioning is out of scope (see D7 in `MODERNIZE.plan.org`).
- The current `config` object is still the pre-modernization mutable singleton. Stage 5 replaces it with typed models, a pure loader, and an injected `Runtime`; do not build new code on the singleton.

## Layout

- `src/sink/sink.py` — all Click commands and the CLI entrypoint (`sink.sink:sink`).
- `src/sink/config.py` — loads/validates `sink.yaml` (project + servers); most other modules read the shared `config` singleton. Stage 5 changes this.
- `src/sink/rsync.py`, `db.py`, `ssh.py`, `check.py`, `deploy.py`, `actions.py`, `applications.py`, `command.py` — per-feature logic.
- `src/sink/ui.py` — themed console output helpers (`ui.error`, `ui.warn`, `ui.notice`). Stage 6 moves this to Rich.
- `src/sink/__main__.py` — `python -m sink`.
- `tests/` — pytest suite, baseline fixtures, and `xfail` reproductions.
- `MODERNIZE.plan.org` — staged modernization plan; read it before making structural changes.
