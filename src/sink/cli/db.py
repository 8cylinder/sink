"""The ``sink db`` command."""

import click

from sink.cli import CONTEXT_SETTINGS, AppCommand, cli
from sink.config.models import Action
from sink.db import DB
from sink.ui import ui


@cli.command("db", context_settings=CONTEXT_SETTINGS, cls=AppCommand)
@click.argument("db-action", type=click.Choice([i.value for i in Action]))
@click.argument("server", type=click.STRING)
@click.argument("sql-gz", type=click.Path(exists=True), required=False)
@click.option(
    "--tag",
    "-t",
    type=click.STRING,
    help="Add a tag to the generated filename when pulling.",
)
@click.option("--real", "-r", is_flag=True)
@click.option("--filename-only", is_flag=True, help="Return only the filename")
@click.pass_obj
def database(rt, db_action, sql_gz, server, real, filename_only, tag):
    """Overwrite a db with a gzipped sql file.

    \b
    ACTION: pull or put.
    SERVER: server name (defined in sink.yaml).
    SQL-GZ: gzipped sql file to upload.  Required if action is "put".

    When pulling, a gzipped file name is created using the project
    name, the server name, the date and time.  It is created in the
    pulls_dir.  eg:

    \b
    pulls_dir/projectname-servername-20-01-01_01-01-01.sql.gz
    """
    cfg = rt.config
    db = DB(
        cfg.project,
        cfg.server(server),
        real=real,
        filename_only=filename_only,
    )

    if db_action == Action.PULL.value:
        db.pull(tag=tag)
    elif db_action == Action.PUT.value:
        if not sql_gz:
            ui.error('When action is "put", SQL-GZ is required.')
        db.put(sql_gz)
