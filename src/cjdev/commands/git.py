import logging
from pathlib import Path
from typing import Any, Dict, Optional

from typer import Context, Typer

from cjdev.commands.context import (
    CjDevContext,
    Config,
    ProjectsConfig,
)

from cjdev.utils.logging import MESSAGE

cli = Typer()


@cli.command()
def git(
    ctx: Context,
):
    """Git utils for Cangjie's repositories management."""
    cjdev_ctx = ctx.ensure_object(CjDevContext)
    _git(cjdev_ctx)

def _git(cjdev_ctx: CjDevContext):
    pass

def init_git(cfg_path: Path, projects: Optional["ProjectsConfig"], logger: logging.Logger):
    repositories = projects.as_list() if projects is not None else []
    cjdev_root = cfg_path.parent

def 
