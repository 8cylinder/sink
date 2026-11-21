# AGENTS.md

`sink` is a Python/Click CLI that manages remote website projects (file/db sync, diff, deploy, ssh, check) driven by a `sink.yaml` config. Targets Linux remote servers via `rsync`, `ssh`, and `mysql`.

## Commands

- Install deps: `poetry install` (Poetry is the source of truth; it manages the in-project `.venv`, Python 3.11).
- Run CLI: `poetry run sink <command>` (or `sink` if installed).
- Build + install locally: `poetry build && pip install --force-reinstall dist/sink-<version>-py3-none-any.whl`
- `setup.py` is legacy and unused; add/edit dependencies in `pyproject.toml` only.
- `uv.lock` is untracked and not the workflow; do not switch tooling to uv.
- No tests, lint, typecheck, or CI config exist. Verify changes with `poetry run sink -h` or `poetry run sink <command> -h`.

## Critical gotchas

- **Dry-run by default.** Mutating commands (`db`, `file`, `action`, `deploy`) only print the bash commands they would run. You must pass `--real`/`-r` to actually execute. Don't assume a command did anything.
- **Version is duplicated.** `pyproject.toml` `version` AND `sink/sink.py` `__version__` (line ~49) must both be bumped; the README wheel filename also hardcodes it.
- **`sink.yaml` is gitignored** and found by walking up from CWD. Commands fail with "You are not in a project" if no config is found. Create one with `poetry run sink misc init > sink.yaml`.
- The tool shells out to real `rsync`/`ssh`/`mysql` against remote servers; only run destructive commands with `--real` when intended.

## Layout

- `sink/sink.py` — all Click commands and the CLI entrypoint (`sink.sink:sink`).
- `sink/config.py` — loads/validates `sink.yaml` (project + servers); most other modules read the shared `config` singleton.
- `sink/rsync.py`, `db.py`, `ssh.py`, `check.py`, `deploy.py`, `actions.py`, `vm.py`, `applications.py` — per-feature logic.
- `sink/ui.py` — themed console output helpers (`ui.error`, `ui.warn`, `ui.notice`).
- `sink/resources/Vagrantfile` — template for `sink vm`.
