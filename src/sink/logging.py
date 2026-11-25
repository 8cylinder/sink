"""Rich logging configuration for -v diagnostics."""

from __future__ import annotations

import logging

from rich.logging import RichHandler


def configure(verbose: int) -> None:
    level = logging.DEBUG if verbose > 1 else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(show_path=False)],
        force=True,
    )
