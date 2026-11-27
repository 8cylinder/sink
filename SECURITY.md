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

## Secret handling

Sink never renders database passwords into commands. Local clients use a
`0600` defaults file in a private temporary directory; remote clients use a
temporary remote credentials file written over ssh stdin. `MYSQL_PWD` is not
exported. `misc api`, `misc settings`, and `info` redact secrets unless
`--show-secrets` is passed. `info --show-secrets` requires a terminal
confirmation or the explicit `--yes` flag. The repository's gitleaks hook and
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
