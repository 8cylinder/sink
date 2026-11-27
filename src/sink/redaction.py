"""Collect secret values and redact them from output surfaces."""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sink.config.models import Config

_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "api_key",
    "api-key",
    "apikey",
    "private_key",
)
_SENSITIVE_TOKENS = frozenset({"pass", "pwd", "passphrase", "pin"})
_SENSITIVE_QUERY_PARTS = (
    "password",
    "passwd",
    "pass",
    "pwd",
    "secret",
    "token",
    "key",
    "auth",
    "signature",
    "credential",
)
_MIN_SECRET_LENGTH = 4


def is_sensitive_key(key: str) -> bool:
    """Return whether a config key name looks like credential material."""
    lowered = key.lower()
    if any(part in lowered for part in _SENSITIVE_SUBSTRINGS):
        return True
    tokens = re.split(r"[^a-z0-9]+", lowered)
    return any(token in _SENSITIVE_TOKENS for token in tokens)


def collect_secret_values(config: Config) -> tuple[str, ...]:
    """Collect configured values that must be redacted from output."""
    values: set[str] = set()

    def walk(value: object) -> None:
        """Visit a config fragment and collect secret values."""
        if isinstance(value, Mapping):
            for key, item in value.items():
                if (
                    isinstance(key, str)
                    and isinstance(item, str)
                    and item
                    and (key.lower() == "note" or is_sensitive_key(key))
                ):
                    values.add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(config.raw)
    # Longest first so a value that contains another secret is replaced
    # before the shorter substring.
    return tuple(sorted(values, key=len, reverse=True))


def redact_values(text: str, secrets: tuple[str, ...]) -> str:
    """Replace known secret values in arbitrary text."""
    for secret in secrets:
        if len(secret) >= _MIN_SECRET_LENGTH:
            text = text.replace(secret, "********")
        # A multi-line note may be rendered as a quoted or folded scalar.
        # Redact each substantive line as a backstop when the key-based pass
        # cannot see through the YAML quoting.
        if "\n" in secret:
            for line in secret.splitlines():
                part = line.strip()
                if len(part) >= _MIN_SECRET_LENGTH:
                    text = text.replace(part, "********")
    return text


def redact_url(url: str) -> str:
    """Mask URL userinfo and sensitive query parameters."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    netloc = parts.netloc
    if "@" in netloc:
        netloc = "********@" + netloc.rsplit("@", 1)[1]
    query: list[tuple[str, str]] = []
    query_changed = False
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if any(part in key.lower() for part in _SENSITIVE_QUERY_PARTS):
            query.append((key, "********"))
            query_changed = True
        else:
            query.append((key, value))
    if "@" not in parts.netloc and not query_changed:
        return url
    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            urlencode(query, safe="*"),
            parts.fragment,
        )
    )
