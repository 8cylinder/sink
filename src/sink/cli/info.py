"""The ``sink info`` command and config editor."""

from pathlib import Path

import click
import yaml

from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.runtime import Runtime
from sink.ui import ui


def edit_config(path: Path) -> None:
    """Edit and validate the config, offering a retry on YAML errors."""
    click.edit(filename=str(path))
    try:
        with path.open() as stream:
            yaml.safe_load(stream)
    except yaml.YAMLError as error:
        if hasattr(error, "problem_mark"):
            msg = "There was an error while parsing the config file"
            if getattr(error, "context", None) is not None:
                ui.error(
                    f"{msg}:\n{error.problem_mark}\n"
                    f"{getattr(error, 'problem', '')} {getattr(error, 'context', '')}.",
                    exit=False,
                )
            else:
                ui.error(
                    f"{msg}:\n{error.problem_mark} {getattr(error, 'problem', '')}.",
                    exit=False,
                )
        else:
            ui.error(
                "Something went wrong while parsing the yaml file.",
                exit=False,
            )

        if click.confirm("\nDo you want to edit the file again?", default=True):
            edit_config(path)


@cli.command(context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.option(
    "--view/--edit", "-v/-e", default=True, help="View or edit config file."
)
@click.pass_obj
def info(rt: Runtime, view: bool) -> None:
    """View or edit the config file.

    If edit, it will be opened in the default editor.

    To config the default editor, add the following lines to
    ~/.bashrc.  Change the 'program' to editor name.

    \b
    export EDITOR='program'
    export VISUAL='program'
    """
    cfg = rt.config
    if view:
        click.echo_via_pager(cfg.path.read_text())
    else:
        edit_config(cfg.path)
