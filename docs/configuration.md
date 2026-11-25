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
  root: .
  pulls_dir: pulls
  exclude:
    - .git
    - .env
  # Optional: use pv for local database imports when it is installed.
  pv: no
  # Optional: use mysqlpump --watch-progress for remote dumps.
  mysqlpump: no

servers:
  dev:
    root: /var/www/example
    default: yes
    automatic: no
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

Environment references use `${NAME}`. A missing variable is a configuration
error. Secrets are redacted from rendered commands and from `misc api` /
`misc settings` unless `--show-secrets` is passed.

`deploy_root` keys from older configs are accepted and ignored. Sink no
longer manages deployments.
