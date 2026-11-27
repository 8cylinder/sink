# Safety

Sink changes files and databases on remote servers. This page records the
safety contract, how each command maps to it, and what the automated suites
do and do not prove.

## Invariants

| ID | Invariant |
|----|-----------|
| S1 | Nothing destructive runs without `--real`. |
| S2 | `check` probes are read-only and always run. |
| S3 | Local and remote paths stay inside the project root. |
| S4 | `warn: yes` asks before overwriting files or a database. |
| S5 | Passwords never appear in argv, rendered commands, logs, or output. |
| S6 | Temporary credential files are `0600` and removed on success, failure, and interruption. |
| S7 | A failing pipeline stage fails the whole action and the real stderr is reported. |
| S8 | Host-key and non-interactive SSH policy is enforced. |
| S9 | Config values cannot inject shell syntax or escape path boundaries. |
| S10 | A failed pull never becomes `LATEST-*` and never looks successful. |
| S11 | Transfers do not delete unrelated files. |
| S12 | Errors leave a non-zero exit code and do not claim success. |
| S13 | Large payloads stream without excessive memory use. |
| S14 | A pull never overwrites an existing dump or its name collision. |

## Command map

| Command | Writes | Relevant invariants |
|---------|--------|---------------------|
| `file put` | remote files | S1, S3, S4, S7, S11, S12 |
| `file pull` | local files | S1, S3, S7, S11, S12 |
| `diff` | temporary download | S1, S3, S7, S12 |
| `db pull` | local dump and `LATEST-*` | S1, S3, S5, S6, S7, S10, S13, S14 |
| `db put` | remote database | S1, S4, S5, S6, S7, S12 |
| `check` | nothing | S2, S5, S8 |
| `action` | whatever the action does | S1, S9, S12 |
| `ssh` | interactive session | S8 |
| `misc init/settings/api` | local files or output | S5 |

## Dry-run and warnings

`rsync` runs its native `--dry-run` variant by default. Commands without a
native dry-run are printed and not executed. `--real` prints and executes the
real variant. `check` is the exception: its probes are read-only and always
run.

When a server sets `warn: yes`, Sink asks before an `rsync` overwrite and
before a database import. Declining leaves the remote unchanged and exits
successfully.

## Secret material

Directory transfers exclude secret material by default: `sink.yaml`,
`.sink/`, `pulls/`, the configured `pulls_dir`, `*.sql.gz`, `.env*`, `*.pem`,
`*.key`, `id_*`, `.ssh/`, `.git/`, `.aws/`, `.config/gcloud/`, `.netrc`,
`.npmrc`, `.pypirc`, `*.kdbx`, `*.bak`, `*~`, and `.#*`. The exclusions are
applied before per-server includes and cannot be removed through project or
server `exclude` entries.

`file put` scans a directory before it starts rsync. If it finds a
secret-looking path, it prints the paths and exits non-zero. Pass
`--allow-secret-files` to print the paths and proceed. The override is
put-only: a directory pull always applies the safe exclusions so a remote
cannot overwrite local config or add a dump to the working tree. `.git/` and
`.sink/` metadata are always excluded, even with the override. Explicit
single-file transfers are not filtered: `sink file put dev .env.prod`
remains available for an intentional transfer. Automatic `.env.<server>`
inclusion was removed; dotenv files are credential material.

## Symlinks

Rsync runs with `--links --safe-links` for put, pull, and diff. `--safe-links`
ignores absolute links and links whose targets escape the destination tree.
A directory put adds a stricter pre-scan: it refuses absolute symlinks and
links whose resolved targets leave `project.root`. Safe relative links inside
the root are transferred, and a symlink loop is reported as unresolvable.
Pulls cannot pre-scan the remote, so they rely on `--safe-links` to ignore
escaping remote links.

## Configuration trust

`sink.yaml` is executable code and credential material. It can select the
SSH and MySQL hosts, identities, URL targets, rsync binary, diff tool, and
action commands. Implicit discovery stops at the nearest `.git` root, or
after three parents when there is no repository, and never crosses into
`$HOME`, the system temporary directory, or `/`. Use `--config-file PATH` for
an explicit config.

`sink check` prints the resolved path and refuses a config owned by another
user, world-writable, or outside the detected repository unless
`--trust-config` is passed. Other commands print a warning but do not block.
A configured non-default `rsync_binary` or `difftool` is announced before it
is used, and configured actions print the command before execution.

## SSH host keys

Every non-interactive SSH path (rsync, scp, check, actions, and credential
staging) uses `StrictHostKeyChecking=yes` and `BatchMode=yes`. When a key is
configured, Sink also passes `IdentitiesOnly=yes`. Interactive `sink ssh`
enforces strict host keys but keeps the session interactive. Set
`ssh.known_hosts` to a dedicated file seeded out of band; Sink then passes
`UserKnownHostsFile` and disables `GlobalKnownHostsFile`. An unknown or
changed host key stops the command—verify the fingerprint before updating
the file.

A configured key must exist. Dry-run warns and renders the command without
`-i`; real mode exits non-zero and does not run the command. Sink never falls
back to the agent or default identities implicitly. Set `key: agent` to use
the SSH agent deliberately.

## Credentials

`sink info` prints a redacted view of the config by default: passwords,
tokens, notes, and free-form credential keys are masked. `--show-secrets`
prints the raw file only after a terminal confirmation; non-interactive
callers must add `--yes`. `-qq` prints nothing. The view no longer uses a
pager, so `LESSOPEN`, scrollback, and pager temporary files cannot expose the
config.

Local MySQL clients use a `0600` option file inside a private temporary
directory and pass only `--defaults-file=<path>`. Sink does not export
`MYSQL_PWD`. Remote imports and dumps write a `0600` option file over SSH
stdin and pass only `--defaults-file=<path>`. An `EXIT` trap removes
the remote file, with a separate cleanup command as a fallback. Rendered
commands contain the file path, never the password.

`db pull` creates a missing pulls directory with mode `0700` and refuses to
write a dump into a directory that is accessible by group or other. New
dumps are `0600`; Lando/DDEV dumps are tightened to `0600` after creation.

Remote MySQL hosts default to `--ssl-mode=VERIFY_IDENTITY`. Set `ssl_ca`,
`ssl_cert`, and `ssl_key` as needed; for remote commands the paths are on the
server. `ssl_mode: DISABLED` is available for a trusted local endpoint.
Sink passes a complete `--defaults-file`, so ambient `~/.my.cnf` and
`/etc/my.cnf` cannot override the connection. `skip_secure_auth` is
deprecated and emits a warning.

## Failure behavior

A database pull writes to `<name>.part`, renames it to the final dump only
after a successful transfer, and only then updates `LATEST-*`. A failed,
interrupted, or startup-failed pull removes the partial file, leaves
`LATEST-*` untouched, reports the real stderr, and exits non-zero; stale
parts older than a day are removed at the start of the next pull. A failed
single-file pull removes only rsync temp files that did not exist before that
transfer, so backups and editor swap files named like `.file.*` are
preserved. A failed transfer reports the remote stderr and exits non-zero.
`check` exits non-zero when any probe prints
`[✗]`, including under `-qq`; `--allow-failures` restores the old exit-0
behavior and `--json` emits a machine-readable probe summary. Credential
files are removed on failure and interruption. Project
and server names are reduced to one filename component before they appear in
a dump name or a `LATEST-*` link, and pull tags accept only letters, digits,
dot, dash, and underscore.

## Test coverage

The fast suite stubs `ssh`, `rsync`, and MySQL, and covers command
construction, quoting, redaction, path validation, and failure reporting. The
Docker suite in `tests/integration` exercises real OpenSSH, rsync, and MySQL
on Ubuntu LTS. It covers transfers, diffs, database pull/push, `check`, path
traversal, hostile filenames, special-character passwords, failed dumps, a
MySQL outage, unwritable remote roots, and credential cleanup.

The Docker suite does not cover production `sshd`/PAM/sudo/SELinux policy,
cloud IAM authentication, network interruption at arbitrary points, or
Lando/DDEV. Those remain manual staging checks.

## Interruption checks

These are timing-dependent, so they stay manual until a deterministic
fault-injection harness exists. Run them against staging:

- Start a large `file put` or `file pull` and send SIGINT to the process
  group. Confirm a non-zero exit, no success line, and no leftover rsync
  temporary files. The put/pull cases are automated in
  `tests/integration/test_interrupt.py`; repeat on staging.
- Start `db pull` against a large table and send SIGINT. Confirm `LATEST-*`
  was not created or changed and no success line is printed. This is
  automated in `tests/integration/test_interrupt.py`; repeat on staging.
- Drop SSH during `mysqldump` (stop the server or sever the network). Confirm
  a non-zero exit and that no `/tmp/sink-mysql-*.cnf` remains. This is
  automated in `tests/integration/test_interrupt.py`; repeat on staging.
- Repeat a `db pull` with a small quota or `ulimit -f`. Confirm a non-zero
  exit, no success line, and that `LATEST-*` is unchanged. The local
  file-size limit case is automated in `tests/integration/test_interrupt.py`.
- Pull a large database on a memory-limited host and confirm memory use stays
  bounded (streaming, not buffering the whole dump). This is automated as a
  max-RSS budget in `tests/integration/test_interrupt.py`; repeat on staging.

## Manual staging checklist

Run against a real staging server before a release:

1. Confirm the SSH host key is pre-trusted and correct.
2. Run every command once without `--real`.
3. Back up the remote database and target directory.
4. Transfer a small file and a directory in both directions.
5. Diff a changed file.
6. Pull the database, inspect the gzip, and restore it to a scratch database.
7. Import to a scratch database and verify row counts.
8. Run `check` and confirm every probe is green.
9. Confirm no `/tmp/sink-mysql-*.cnf` file remains.
10. Confirm no unexpected deletions or ownership changes.
11. Open `sink ssh` interactively and confirm it starts in the server root.

Record any deviation as a new integration or regression test.

## Residual risks

Accepted until an environment-specific suite exists, owned by the maintainer:
non-Ubuntu Linux and macOS local `rsync` behavior, production SSH/PAM/sudo/
SELinux policy, cloud database IAM, real network loss, full disks and quotas,
and Lando/DDEV workflows.
