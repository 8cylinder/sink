"""The ``sink diff`` command."""

from pathlib import Path

import click

from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.rsync import Transfer
from sink.runtime import Runtime


@cli.command("diff", context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("server")
@click.argument("filename", type=click.Path(exists=True), required=False)
@click.option(
    "--ignore-whitespace", "-i", is_flag=True, help="Ignore whitespace in diff."
)
@click.option(
    "--difftool", "-d", is_flag=True, help='Use meld instead of "git diff".'
)
@click.option(
    "--word-diff",
    "-w",
    type=click.Choice(["word", "letter"]),
    help="Refine diffs to word or letter differences.",
)
@click.option(
    "--real", "-r", is_flag=True, help="Download the file and show the diff."
)
@click.pass_obj
def diff_files(
    rt: Runtime,
    filename: str | Path | None,
    server: str,
    ignore_whitespace: bool,
    word_diff: str | None,
    difftool: bool,
    real: bool,
) -> None:
    """Diff a local and remote file.

    \b
    FILENAME: file to be transferred
    SERVER: server name (defined in sink.yaml)."""
    cfg = rt.config

    if not filename:
        filename = Path(cfg.project.root)
    fx = Path(filename).resolve()
    xfer = Transfer(cfg.project, cfg.server(server), real=real)
    xfer.diff(
        fx, ignore=ignore_whitespace, word_diff=word_diff, difftool=difftool
    )
