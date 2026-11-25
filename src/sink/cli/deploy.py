from enum import Enum

import click

from sink.cli import CONTEXT_SETTINGS, AppGroup, cli
from sink.deploy import (
    DeployViaLocal,
    DeployViaRename,
    DeployViaSymlink,
)
from sink.ui import ui


class DeployType(Enum):
    RENAME = "rename"
    SYMLINK = "symlink"
    LOCAL = "local"


@cli.group(context_settings=CONTEXT_SETTINGS, cls=AppGroup)
@click.option(
    "-m",
    "--method",
    default=DeployType.LOCAL.value,
    type=click.Choice([i.value for i in DeployType]),
    help=f"Deploy method, default {DeployType.LOCAL.value}",
)
@click.pass_context
def deploy(ctx, method):
    """[Group] Deploy site to server with rollback."""
    ctx.meta["deploy_method"] = DeployType(method)


@deploy.command(context_settings=CONTEXT_SETTINGS)
@click.argument("server")
@click.argument("dirs", nargs=-1)
@click.pass_context
def init(ctx, server, dirs):
    """Initialize and setup a deploy.

    Create a dir localy or on the remote server to hold the versions.
    The exact method depends of the deploy method used."""
    deploytype = DeployType(ctx.meta["deploy_method"])
    cfg = ctx.obj.config

    if deploytype == DeployType.RENAME:
        init_deploy = DeployViaRename(
            cfg.project, cfg.server(server), real=True
        )
        init_deploy.init_deploy(*dirs)
    elif deploytype == DeployType.SYMLINK:
        init_deploy = DeployViaSymlink(
            cfg.project, cfg.server(server), real=True
        )
        init_deploy.init_deploy()
    elif deploytype == DeployType.LOCAL:
        deploy = DeployViaLocal(cfg.project, cfg.path.parent)
        deploy.init_deploy()
    else:
        ui.error("deploy type wrong")


@deploy.command(context_settings=CONTEXT_SETTINGS)
@click.argument("server")
@click.option("--real", "-r", is_flag=True)
@click.option(
    "--no-itemize",
    is_flag=True,
    help="No itemized output from rsync.",
)
@click.option(
    "-d", "--dump-db", is_flag=True, help="Take a snapshot of the db."
)
@click.option("-n", "--note", help="Add a note to DEPLOY_INFO.yaml.")
@click.pass_context
def new(ctx, server, real, no_itemize, dump_db, note):
    """Upload a new version of the site.

    Upload a new version to the deploy root."""
    deploytype = DeployType(ctx.meta["deploy_method"])
    cfg = ctx.obj.config

    if deploytype == DeployType.RENAME:
        new_deploy = DeployViaRename(
            cfg.project, cfg.server(server), real=real, quiet=no_itemize
        )
        new_deploy.new()
    elif deploytype == DeployType.SYMLINK:
        new_deploy = DeployViaSymlink(
            cfg.project, cfg.server(server), real=real, quiet=no_itemize
        )
        new_deploy.new(dump_db=dump_db)
    elif deploytype == DeployType.LOCAL:
        deploy = DeployViaLocal(cfg.project, cfg.path.parent)
        deploy.new(cfg.server(server), real=real, note=note)
    else:
        ui.error("deploy type wrong")


@deploy.command(context_settings=CONTEXT_SETTINGS)
@click.argument("server")
@click.option("--real", "-r", is_flag=True)
@click.option(
    "-l", "--load-db", is_flag=True, help="Take a snapshot of the db."
)
@click.option(
    "--delete",
    is_flag=True,
    help="Delete any files on remote server that are not part of the upload.",
)
@click.pass_context
def switch(ctx, server, real, load_db, delete):
    """Change the symlink to point to a different dir in the deploy root."""
    deploytype = DeployType(ctx.meta["deploy_method"])
    cfg = ctx.obj.config

    if deploytype == DeployType.RENAME:
        DeployViaRename(cfg.project, cfg.server(server), real=real)
    elif deploytype == DeployType.SYMLINK:
        deploy = DeployViaSymlink(cfg.project, cfg.server(server), real=real)
        deploy.change_current(load_db=load_db)
    elif deploytype == DeployType.LOCAL:
        deploy = DeployViaLocal(cfg.project, cfg.path.parent)
        deploy.change_current(cfg.server(server), real=real, delete=delete)
    else:
        ui.error("deploy type wrong")
