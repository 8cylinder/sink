# Security Policy

## Supported versions

Security fixes are applied to the latest release on the default branch.

## Reporting a vulnerability

Please report security issues privately through the repository's GitHub
Security Advisories page:

https://github.com/8cylinder/sink/security/advisories/new

Do not open a public issue for a vulnerability. Include the affected version,
a minimal reproduction, and any relevant configuration. Please do not include
real passwords, private keys, or production host details.

## Trust model

`sink.yaml` is executable code and trusted credential material. It selects
the SSH host and identity, MySQL host, URL targets, child-process binary,
diff tool, and action commands. Anyone who can write the config, or place one
in a discovered parent directory, can cause code execution or credential
exfiltration in the operator's context. Review the config before running
commands and keep it in a trusted repository with restricted write access.

Implicit discovery stops at the nearest `.git` root, or after three parents
when there is no repository, and never crosses into `$HOME`, the system
temporary directory, or `/`. Use `--config-file PATH` for an explicit path.
`sink check` prints the resolved path and refuses a config owned by another
user, world-writable, or outside the detected repository unless
`--trust-config` is passed. Other commands warn but do not block.

All non-interactive SSH paths enforce `StrictHostKeyChecking=yes` and
`BatchMode=yes`; `IdentitiesOnly=yes` is added when a key is configured.
Interactive `sink ssh` also enforces strict host keys. Set
`ssh.known_hosts` to a dedicated file seeded out of band. A configured key
must exist; real mode fails instead of falling back to the agent. Set
`key: agent` to opt into agent identities explicitly.

## Secret handling

Sink never renders database passwords into commands. Local clients use a
`0600` defaults file in a private temporary directory; remote clients use a
temporary remote credentials file written into a private `0700` directory
over ssh stdin. Option values containing NUL, CR, or LF are rejected.
`MYSQL_PWD` is not exported. Remote MySQL hosts default to `--ssl-mode=VERIFY_IDENTITY`; set
`ssl_ca`/`ssl_cert`/`ssl_key` for a private CA or client certificate. Sink
passes a complete `--defaults-file` so ambient option files cannot override
the connection. `skip_secure_auth` is deprecated. `misc api`, `misc settings`,
`info`, check output, and action output redact configured secrets;
`--show-secrets` is the explicit opt-out where offered. Action listings hide
commands unless `--show-commands` is passed. `info --show-secrets` requires a
terminal confirmation or the explicit `--yes` flag. The repository's gitleaks hook and
CI scan guard against accidental committed secrets.

Directory transfers exclude secret material by default: `sink.yaml`,
`pulls/`, `*.sql.gz`, `.env*`, `*.pem`, `*.key`, `id_*`, `.ssh/`, `.git/`,
and cloud credential files. A directory `sink file put` refuses to start when
it finds one of those paths unless `--allow-secret-files` is passed; explicit
single-file transfers are not filtered. Directory pulls always apply the
exclusions, and `.git/`/`.sink/` are always excluded. Automatic
`.env.<server>` inclusion is not supported.

Rsync runs with `--safe-links`. A directory put refuses absolute symlinks and
links whose resolved targets leave `project.root`; safe relative in-tree links
remain transferable. Pulls ignore remote links that escape the destination.
