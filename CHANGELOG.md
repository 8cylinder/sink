# Changelog

## 0.3.0 - 2026-11-25

### Removed

- Removed the `deploy` command group and all deploy implementations
  (`deploy.py`, `cli/deploy.py`), the `coolname` dependency, deploy tests,
  fixtures, and the `deploy_root` model field. Legacy `deploy_root` keys in
  existing `sink.yaml` files are accepted and ignored.
- Removed the obsolete `single` command. Use `sink file put` or
  `sink file pull` with the desired server instead. The legacy `automatic`
  setting is still accepted but is no longer used or shown by `sink check`.

### Changed

- `sink check` always runs its read-only probes and no longer has a
  `--real` flag. `--insecure` remains the TLS opt-out. It no longer lists
  the unused `log_dir` and `cache_dir` settings. Status lines now lead with
  colored `✓`/`✗` markers, omit the table header, and render `key: value`
  with the key and value in different colors. Probe errors print a compact
  indented `[Error]` line without surrounding blank lines. Database status
  lines include the username so multiple entries for the same database are
  distinguishable. Diagnostic labels read `[Warning]` and `[Notice]` without
  a trailing colon inside the brackets.
- The source tree is fully annotated and type-checked with `ty` without
  warning downgrades. Ruff now enforces `ANN`, `PTH`, `DTZ`, `RET`, and
  `ARG`, and branch coverage is gated at 90%.
- Removed the remaining dead `Transfer.error_code` helper.
- `sink check` reports a stable table for project directories, the rsync
  binary, and each server's root/warn/automatic fields. URL probes use a Rich
  status instead of the old spinner thread, and database symlink creation no
  longer changes the process working directory.
- `db put` validates that the source is a readable gzip file and that the
  server has a database before touching the remote host. Local imports use
  `cat` by default; set `project.pv: yes` to use `pv` when installed. Remote
  dumps use `mysqldump`, or `mysqlpump --watch-progress` with
  `project.mysqlpump: yes`.
- Database pull timestamps are timezone-aware while keeping the existing
  local-time filename format. Lando/DDEV failures now preserve stderr and
  exit non-zero.
- Pipelines capture stderr from every stage, so a failing producer such as
  `mysqldump | gzip` reports its real error instead of `Command failed`.
- Remote database credentials are quoted for MySQL option-file syntax,
  preserving passwords containing `#` and other special characters. The
  remote dump/import command installs an `EXIT` trap so the temporary `0600`
  file is removed even when the command fails or the connection drops.
- `file` accepts `[SERVER] [FILENAME]`; a lone non-server token is treated
  as a filename on the default server. Paths outside `project.root` are
  rejected instead of becoming remote absolute paths.
- `diff` compares against the local directory, honors `--ignore-whitespace`,
  avoids a pager when stdout is not a terminal, and reports git/difftool
  failures with a non-zero exit code.
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
