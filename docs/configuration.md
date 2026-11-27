# Configuration

Sink reads `sink.yaml` from the current directory or a bounded parent.
Discovery stops at the nearest `.git` root, or after three parents when there
is no repository, and never crosses into `$HOME`, the system temporary
directory, or `/`. Use `--config-file PATH` to load an explicit file.
`sink --config` prints the resolved absolute path.

`sink.yaml` is executable code and credential material. It selects SSH and
MySQL hosts, identities, URL targets, the rsync binary, the diff tool, and
action commands. Review it before running commands. `sink check` prints the
resolved path and refuses a config owned by another user, world-writable, or
outside the detected repository unless `--trust-config` is passed. Other
commands warn but do not block.

```console
sink misc init > sink.yaml
sink misc init dev stag prod > sink.yaml
```

A minimal project:

```yaml
project:
  name: example
  # Create this directory first. Only deployable content belongs here; keep
  # sink.yaml, pulls/, env files, and keys above it.
  root: public
  # Outside root; create it before the first db pull.
  pulls_dir: .sink/pulls
  exclude:
    - .git
  # Optional: use pv for local database imports when it is installed.
  pv: no
  # Optional: use mysqlpump --watch-progress for remote dumps.
  mysqlpump: no

servers:
  dev:
    root: /var/www/example
    default: yes
    warn: no
    exclude:
      - storage/logs
    ssh:
      - name: deploy
        username: deploy
        server: example.com
        key: ~/.ssh/id_ed25519
        known_hosts: ~/.ssh/known_hosts_sink
        port: 22
    mysql:
      - username: example
        password: ${DATABASE_PASSWORD}
        db: example
        hostname: localhost
```

`ssh.known_hosts` is optional. Sink enforces `StrictHostKeyChecking=yes` and
`BatchMode=yes` on every non-interactive SSH path, and adds
`IdentitiesOnly=yes` when a key is configured. Interactive `sink ssh` also
enforces strict host keys. Seed a dedicated known-hosts file out of band
before the first connection; a changed key stops the command.

A configured `ssh.key` must exist. Dry-run prints a warning and renders the
command without `-i`; real mode exits non-zero instead of falling back to the
agent or a default identity. Set `key: agent` to use the SSH agent explicitly.

Extra keys are allowed. Sink ignores them during normal commands so a
`sink.yaml` can hold unrelated project data; `sink check` lists them as
unknown-key warnings to catch misspellings.

Directory transfers exclude secret material by default: `sink.yaml`,
`pulls/`, `*.sql.gz`, `.env*`, `*.pem`, `*.key`, `id_*`, `.ssh/`, `.git/`,
and cloud credential files. A directory `file put` that contains one of
those paths is refused unless `--allow-secret-files` is passed. Explicit
single-file transfers are not filtered. Directory pulls always keep the
built-in exclusions, so a remote cannot overwrite `sink.yaml` or add a dump
to the working tree. `.git/` and `.sink/` are always excluded. The
exclusions are applied before per-server includes; automatic
`.env.<server>` inclusion is no longer available. Rsync uses `--safe-links`,
and a directory put refuses absolute symlinks or links whose targets leave
`project.root`.

`db pull` creates a missing `pulls_dir` with mode `0700` and refuses a
group- or world-accessible directory. New dumps are `0600`. Local MySQL
clients use a private `0600` defaults file; `MYSQL_PWD` is not exported.

Environment references use `${NAME}`. A missing variable is a configuration
error. Secrets are redacted from rendered commands and from `misc api` /
`misc settings` unless `--show-secrets` is passed.

`deploy_root` keys from older configs are accepted and ignored. Sink no
longer manages deployments.
