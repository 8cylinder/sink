# Dry-run fixtures — Stage 0

Captured from `/tmp/sink-stage0/project` (a fixture project with stub
`rsync`/`ssh`/`scp`/`mysql`/`mysqldump`/`git`/`pv`/`lando`/`ddev` binaries on
`PATH`) using:

- `NO_COLOR=1`, `TERM=dumb`
- `STUB_LOG=/tmp/sink-stage0/project/stub.log`
- no `--real` flag anywhere, so every command should be a dry run

Each `.txt` file contains:

```
$ sink <args>
[exit <code>]
<combined stdout+stderr>
```

## Results

| File | Command | Exit | Notes |
| --- | --- | --- | --- |
| `file-put-root.txt` | `file put dev` | 0 | Renders `rsync --dry-run`. |
| `file-put-file.txt` | `file put dev project/index.html` | 0 | Renders `rsync --dry-run`. |
| `file-pull.txt` | `file pull dev index.html` | 0 | Renders `rsync --dry-run`; remote path is derived from the local absolute path (see `test_file_pull_outside_the_project_root`). |
| `single.txt` | `single project/index.html` | 1 | **Crash (B17).** The filename is passed as a server name: `KeyError: 'index.html'` then `AttributeError: 'list' object has no attribute 'username'` in `sink/config.py:347`. Traceback in the fixture file. |
| `db-pull.txt` | `db pull dev` | 0 | **Known bug (N13).** Rendered `mysqldump` includes `--dry-run`, which `mysqldump` does not support. Timestamp in the generated filename is captured at run time. |
| `db-put.txt` | `db put dev project/index.html` | 0 | Renders `pv ... \| ssh ... gunzip -c \| mysql`. |
| `diff.txt` | `diff dev project/index.html` | 0 | Renders `rsync --compare-dest` then `git diff \| less`. Temp dir name is random per run. |
| `deploy-symlink-init.txt` | `deploy -m symlink init dev` | 1 | **Crash (B1).** `AttributeError: 'DeployViaSymlink' object has no attribute 'ssh'` at `sink/deploy.py:225`. Traceback in the fixture file. |
| `deploy-rename-init.txt` | `deploy -m rename init dev public_html` | 1 | **Crash (B1).** `AttributeError: 'DeployViaRename' object has no attribute 'ssh'` at `sink/deploy.py:90`. Traceback in the fixture file. |
| `deploy-local-init.txt` | `deploy -m local init dev` | 0 | **Known bug (N8).** Creates `dist/` even without `--real`, and prints only `Warning: DIST (dist) dir does not exist, creating it.` with no rendered command. `dist/` removed after capture so the run is repeatable. |
| `deploy-local-new.txt` | `deploy -m local new dev` | 0 | Renders `rsync --archive --verbose --dry-run`. Destination dir name contains a generated codename and timestamp. |
| `check.txt` | `check dev` | 0 | Executes the three `ssh` probes against the stubs (see `stub.log`); output contains spinner backspace characters. |

## Nondeterministic content

These fixtures contain values that change between runs and will need
normalization before being used as golden files:

- `db-pull.txt`: generated SQL filename timestamp (`demo-dev-YY-MM-DD_HH-MM-SS.sql.gz`).
- `diff.txt`: `mktemp`-style directory name (`/tmp/tmpXXXXXXXX [dev]`).
- `deploy-local-new.txt`: generated codename + ISO timestamp directory.
- `check.txt`: spinner control characters (`\x08`).

Absolute paths also embed `/tmp/sink-stage0/project`, the scratch fixture root.
