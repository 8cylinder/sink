# Changelog

## Unreleased

### Security

- Directory transfers now exclude secret material before per-server
  includes: `sink.yaml`, the pulls directory, `*.sql.gz`, `.env*`, `*.pem`,
  `*.key`, `id_*`, `.ssh/`, `.git/`, cloud credential paths, and common
  backup/editor files. `file put` refuses a directory that contains one of
  those paths and prints the exact entries; `--allow-secret-files` is the
  put-only override. Directory pulls always apply the exclusions. Explicit
  single-file transfers are unchanged.
- Automatic `.env.<server>` inclusion was removed because dotenv files are
  credential material. Transfer one deliberately with an explicit file path
  or `--allow-secret-files`.
- The starter config now uses `root: public` and a `pulls_dir` outside the
  deployed root.
- `sink info` now redacts passwords, tokens, notes, and free-form credential
  keys by default. It no longer uses a pager, honors `-qq`, and adds
  `--show-secrets` with a terminal confirmation or the explicit `--yes`
  flag.
- Rsync now runs with `--safe-links` for put, pull, and diff. Directory puts
  refuse absolute symlinks and links whose resolved targets escape
  `project.root`; safe relative in-tree links still transfer. Symlink loops
  are reported instead of being followed.
- `.git/` and `.sink/` are always excluded from directory transfers, even
  with `--allow-secret-files`. `.git` no longer triggers the secret-file
  refusal, so a normal repository root remains usable.
- Local database pulls create dumps with mode `0600`. `db pull` creates a
  missing `pulls_dir` with `0700` and refuses a group- or world-accessible
  directory. Local MySQL clients use a private `0600` defaults file instead
  of `MYSQL_PWD`, which is no longer exported to any pipeline stage.
- Config discovery now stops at the nearest `.git` root, or after three
  parents when there is no repository, and never crosses `$HOME`, the system
  temporary directory, or `/`. Added `--config-file PATH` for an explicit
  config.
- `sink check` prints the resolved config path and refuses a config owned by
  another user, world-writable, or outside the repository unless
  `--trust-config` is passed. Other commands warn but do not block.
  Configured `rsync_binary`, `difftool`, and action commands are announced
  before use.
- Every non-interactive SSH path now enforces `StrictHostKeyChecking=yes` and
  `BatchMode=yes`; `IdentitiesOnly=yes` is added when a key is configured.
  Interactive `sink ssh` also enforces strict host keys. Added optional
  `ssh.known_hosts` for a dedicated known-hosts file.
- `sink check` now exits non-zero when any probe fails, including under
  `-qq`. Use `--allow-failures` for the old exit-0 behavior. `--json` emits a
  machine-readable probe summary.

### Fixed

- `db pull --tag` accepts only one filename component. Values such as
  `../../../escape` are rejected instead of writing outside `pulls_dir`.
- `db put` honors `warn: yes` and asks before overwriting a database on the
  remote, Lando, and DDEV paths. Declining leaves the database unchanged.
- `db pull` appends `-2`, `-3`, and so on instead of overwriting a dump
  created in the same second.
- A failed `db pull` removes the truncated local dump, leaves `LATEST-*`
  unchanged, and exits non-zero.
- Project and server names are reduced to a single filename component before
  they become dump names or `LATEST-*` links, so a name containing `../`
  cannot escape `pulls_dir`.

### Tests

- Added fast safety contracts and real-service Docker coverage for hostile
  filenames and tags, outside-root paths, special-character passwords,
  restricted and disconnected databases, warning confirmation, unwritable
  remote roots, missing directories, URL probes, and credential cleanup.
- Added interruption coverage for SIGINT file put/pull and database pulls,
  SSH drops, disk pressure, concurrent pulls, a large-pull memory budget,
  a PTY-driven interactive-SSH check, diff option/difftool coverage, and a
  Docker CI matrix on Ubuntu 20.04 and 26.04.

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
- Added opt-in Docker-backed integration tests for real SSH, rsync, and MySQL
  against Ubuntu LTS containers. `make integration`, `make integration-oldest`,
  and `make integration-matrix` cover the oldest and latest supported LTS
  releases; the default `make check` suite remains Docker-free.
- `diff` always downloads a single remote file before comparison.  Using
  `--compare-dest` there skipped identical files and left `git diff` with no
  temporary file.
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
