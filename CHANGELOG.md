# Changelog

## Unreleased (0.3.0)

### Changed

- The Click command tree now lives in `sink.cli`, with one module per command
  group and `sink.cli:main` as the console entry point. Root options include
  `--color`, `--config`, `--completions`, `-q/-qq`, `--silent`, `-s`, and
  `-v`.
- Output modes are explicit: `-q` hides rendered commands, `-qq` hides all
  output, and `--suppress-commands`/`--silent` remain aliases. Success lines
  use `[Success]` and `[Success (DRY RUN)]` labels.
- `--completions` writes a static bash script to the first configured
  bash-completion directory and prints only its path on stdout.
- `misc api` is JSON-only, redacts secret-looking values by default, and
  offers `--show-secrets`. `misc settings` also redacts by default.
- `db --quiet` is now `--filename-only`; `deploy new --quiet` is now
  `--no-itemize`; `check --required` uses `-R` so `--real` can use `-r`.
- Human output uses Rich; `click.style` and `click.secho` are gone.
- Configuration is now loaded into immutable, typed models by a pure loader.
  A per-invocation `Runtime` owns the working directory and lazily loads the
  config; the mutable global `config` singleton and `Dict2obj` are gone.
  Missing keys, bad YAML, unknown servers, and duplicate defaults raise typed
  config errors with the file and key. Unknown keys warn and are ignored.
- Commands are dry-run by default. Each action renders one command object;
  tools with a native dry-run (`rsync --dry-run`) execute that variant, while
  tools without one are printed and not spawned. Pass `--real` to execute.
- `sink ssh` now defaults to printing the ssh command; use `--real` for an
  interactive session. The inverse `--dry-run/-d` flag was removed.
- `sink diff` and `sink check` now print their commands by default and accept
  `--real`.
- Shell execution uses argv lists instead of `shell=True`. The `plumbum`
  dependency and `sink/command.py` were removed.
- Database passwords no longer appear in rendered commands. Local clients use
  `MYSQL_PWD`; remote clients use a temporary `0600` defaults-extra file
  written over ssh stdin and removed afterwards.
- `sink.yaml` values may reference environment variables with `${NAME}`. A
  missing variable is a config error.
- URL checks verify TLS certificates by default; `--insecure` is the explicit
  opt-out.

### Security

- Removed all `shell=True` call sites and the associated command injection
  surface.
- Redacted configured database passwords from command and error output.

Prior releases were GPLv3; this release is GPL-2.0-only.
