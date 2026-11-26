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

## Credentials

Local MySQL imports use `MYSQL_PWD` in the child environment. Remote imports
and dumps write a `0600` option file over SSH stdin and pass only
`--defaults-extra-file=<path>`. An `EXIT` trap removes the file, with a
separate cleanup command as a fallback. Rendered commands contain the file
path, never the password.

## Failure behavior

A failed pull removes the truncated local dump, leaves `LATEST-*` untouched,
reports the real stderr, and exits non-zero. A failed transfer reports the
remote stderr and exits non-zero. Credential files are removed on failure and
interruption. Project and server names are reduced to one filename component
before they appear in a dump name or a `LATEST-*` link, and pull tags accept
only letters, digits, dot, dash, and underscore.

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
  bounded (streaming, not buffering the whole dump).

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
