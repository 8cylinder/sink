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

Sink never renders database passwords into commands. Local clients use
`MYSQL_PWD`; remote clients use a temporary remote credentials file written
over ssh stdin. `misc api` and `misc settings` redact secrets unless
`--show-secrets` is passed. The repository's gitleaks hook and CI scan guard
against accidental committed secrets.
