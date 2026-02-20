import logging
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, List, Optional

import questionary
from typer import Argument, Context, Typer

from cjdev.assets import DOCKERFILE
from cjdev.commands.context import CjDevContext, ContainerConfig
from cjdev.utils.execute import execute_with_log
from cjdev.utils.logging import MESSAGE

cli = Typer()


@cli.command(context_settings={"ignore_unknown_options": True})
def dc(
    ctx: Context,
    args: Annotated[Optional[List[str]], Argument()] = None,
):
    """Execute a command in the container."""
    cjdev_ctx = ctx.ensure_object(CjDevContext)
    _dc(cjdev_ctx, args)


_CONTAINER_WORKDIR = "/home/cjdev"


def _dc(
    cjdev_ctx: CjDevContext,
    args: Annotated[Optional[List[str]], Argument()] = None,
):
    config = cjdev_ctx.config
    container_cfg = config.container
    logger = cjdev_ctx.logger
    if not container_cfg.use_container:
        logger.log(
            MESSAGE,
            "Seems like you're [bold red]not[/] using a container. Set 'use_container' to true in your config file and repeat the command.",
        )

        return

    try:
        _check_prerequisites()
    except Exception as e:
        logger.error(f"Unable to run command in the container.\n{e}")
        return

    host_workdir = cjdev_ctx.config_path.parent
    current_project = _detect_current_project(cjdev_ctx)

    if current_project:
        project_worktree = host_workdir / current_project
        container_workdir = _get_worktree_container_path(
            host_workdir, project_worktree, current_project
        )
    else:
        container_workdir = _CONTAINER_WORKDIR

    container_pwd = _container_pwd(host_workdir, Path.cwd(), container_workdir)
    container_name = container_cfg.container_name or "cjdev"
    _exec_cmd_in_container(args or ["zsh"], host_workdir, container_pwd, container_name)


def _exec_cmd_in_container(
    cmd: List[str],
    host_workdir: Path,
    container_pwd: Path,
    container_name: str,
):
    cmd = [
        "container",
        "run",
        "-it",
        "--rm",
        "-v",
        f"{host_workdir.as_posix()}:{_CONTAINER_WORKDIR}:rw",
        "-w",
        container_pwd.as_posix(),
        container_name or "cjdev",
        "bash",
        "-lc",
        " ".join(cmd),
    ]
    subprocess.run(args=cmd, executable="docker")


def _container_pwd(host_workdir: Path, host_pwd: Path, container_workdir: str) -> Path:
    try:
        relpath = host_pwd.as_posix().removeprefix(host_workdir.as_posix())
    except ValueError:
        relpath = host_pwd.name

    return Path(container_workdir) / relpath.lstrip("/")


def _get_worktree_container_path(
    workspace_root: Path, project_path: Path, project_name: str
) -> str:
    try:
        project_rel = project_path.as_posix().removeprefix(workspace_root.as_posix())
    except ValueError:
        project_rel = project_path.name

    return f"{_CONTAINER_WORKDIR}{project_rel}"


def _detect_current_project(cjdev_ctx: CjDevContext) -> Optional[str]:
    if not cjdev_ctx.worktree_manager:
        return None

    current_path = Path.cwd()
    workspace_root = cjdev_ctx.config_path.parent

    for project in cjdev_ctx.worktree_manager.get_all_projects():
        project_path = workspace_root / project.path
        try:
            if current_path.resolve().is_relative_to(project_path.resolve()):
                return project.name
        except ValueError:
            pass

    return None


def init_container(cfg_path: Path, cfg: ContainerConfig, logger: logging.Logger):
    if not cfg.use_container:
        return

    try:
        _check_prerequisites()
    except Exception as e:
        logger.error(f"Unable to initialize container.\n{e}")
        return

    dockerfile = cfg_path.parent / "Dockerfile"
    override_dockerfile = questionary.confirm(
        f"Override an existing Dockerfile at {dockerfile.as_posix()}?",
        default=False,
    ).unsafe_ask()
    if override_dockerfile:
        dockerfile.write_text(DOCKERFILE)
    _build_container(cfg, dockerfile, logger)


def build_container(cfg: ContainerConfig, dockerfile: Path, logger: logging.Logger):
    try:
        _check_prerequisites()
    except Exception as e:
        logger.error(f"Unable to build container.\n{e}")
        return

    _build_container(cfg, dockerfile, logger)


def _build_container(cfg: ContainerConfig, dockerfile: Path, logger: logging.Logger):
    container_name = cfg.container_name if cfg.container_name else "cjdev"
    execute_with_log(
        ["docker", "build", "-t", container_name, dockerfile.parent.as_posix()],
        logger,
    )


def _check_prerequisites():
    if not shutil.which("docker"):
        raise Exception("`docker` is not installed")
