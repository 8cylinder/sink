"""Application error hierarchy.

The CLI catches these and renders a message with a non-zero exit code.  The
loader and command modules raise them instead of calling ``sys.exit``.
"""

from __future__ import annotations


class SinkError(Exception):
    """Base class for all expected sink failures."""


class ConfigError(SinkError):
    """The project configuration is missing, unreadable, or invalid."""


class CommandError(SinkError):
    """A rendered command failed."""


class TransferError(CommandError):
    """An rsync/ssh transfer failed."""


class NotFoundError(SinkError):
    """A requested value or resource does not exist."""


class NoDefaultServer(ConfigError):
    """No server was named and the config has no default."""


class UnknownServer(ConfigError):
    """The requested server name is not in the config."""


class NotInProject(ConfigError):
    """No sink.yaml was found from the working directory."""
