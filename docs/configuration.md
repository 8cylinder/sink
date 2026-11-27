# Configuration

Sink reads `sink.yaml` from the current directory or the nearest parent.
Use `sink --config` to print the discovered absolute path.

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
        port: 22
    mysql:
      - username: example
        password: ${DATABASE_PASSWORD}
        db: example
        hostname: localhost
```

Extra keys are allowed. Sink ignores them during normal commands so a
`sink.yaml` can hold unrelated project data; `sink check` lists them as
unknown-key warnings to catch misspellings.

Directory transfers exclude secret material by default: `sink.yaml`,
`pulls/`, `*.sql.gz`, `.env*`, `*.pem`, `*.key`, `id_*`, `.ssh/`, `.git/`,
and cloud credential files. A directory `file put` that contains one of
those paths is refused unless `--allow-secret-files` is passed. Explicit
single-file transfers are not filtered. Directory pulls always keep the
built-in exclusions, so a remote cannot overwrite `sink.yaml` or add a dump
to the working tree. The exclusions are applied before per-server includes;
automatic `.env.<server>` inclusion is no longer available.

Environment references use `${NAME}`. A missing variable is a configuration
error. Secrets are redacted from rendered commands and from `misc api` /
`misc settings` unless `--show-secrets` is passed.

`deploy_root` keys from older configs are accepted and ignored. Sink no
longer manages deployments.
