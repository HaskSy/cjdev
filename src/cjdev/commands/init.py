import logging
from pathlib import Path
from typing import Any, Dict, Optional

import questionary
import typer
from pydantic import ValidationError
from pydantic_core import Url
from questionary import Choice
from rich import print
from typer import Context, Typer

from cjdev.commands.context import (
    CacheConfig,
    CjDevContext,
    Config,
    ContainerConfig,
    Project,
    ProjectsConfig,
)
from cjdev.commands.dc import init_container
from cjdev.utils.logging import MESSAGE

cli = Typer()

DEFAULT_PROJECTS = [
    "cangjie_compiler",
    "cangjie_runtime",
    "cangjie_test",
    "cangjie_stdx",
    "cangjie_tools",
    "cangjie_test_framework",
]


@cli.command()
def init(ctx: Context):
    """Init cjdev environment (create config and clone repositories)."""
    cjdev_ctx: CjDevContext = ctx.obj
    config: Config = cjdev_ctx.config
    config_path: Path = cjdev_ctx.config_path

    print("[bold]Welcome to cjdev initialization![/bold]\n")

    if not config_path.exists():
        print("No cjdev.toml found. Let's create one!\n")
        _configure_container(config)
        _configure_cache(config, config_path.parent)
        _configure_projects(config)
        _save_config(config_path, config)
        print(f"[green]Config saved to {config_path}[/green]\n")

    enabled_projects = _get_enabled_projects(config)
    if not enabled_projects:
        print("No projects selected. Let's select some!")
        _configure_projects(config)
        _save_config(config_path, config)
        print(f"[green]Config saved to {config_path}[/green]\n")

    if cjdev_ctx.worktree_manager:
        orphan_worktrees = cjdev_ctx.worktree_manager.detect_orphan_worktrees()
        if orphan_worktrees:
            print(
                f"[yellow]Found {len(orphan_worktrees)} orphaned worktree(s) without bare repos.[/yellow]"
            )
            reattach = questionary.confirm(
                "Would you like to reattach them?", default=True
            ).ask()
            if reattach:
                print("\n[bold]Reattaching worktrees...[/bold]\n")
                cjdev_ctx.worktree_manager.reattach_all()
                print("\n[green]Worktrees reattached![/green]")
                return

        branches = cjdev_ctx.worktree_manager.list()
        if branches:
            print("[green]Repositories already initialized.[/green]")
            return

        run_clone = questionary.confirm(
            "Would you like to clone repositories now?", default=True
        ).ask()

        if run_clone:
            branch = questionary.text("Enter branch name:", default="dev").ask()
            print(f"\n[bold]Cloning repositories on branch '{branch}'...[/bold]\n")
            cjdev_ctx.worktree_manager.init(branch)
            print("\n[green]Git initialization complete![/green]")
    else:
        print("[red]Error: Worktree manager not initialized[/red]")


def _init(cjdev_ctx: CjDevContext):
    cfg_path = cjdev_ctx.config_path
    config = _init_config(cfg_path, cjdev_ctx.config)
    init_container(cfg_path, config.container, cjdev_ctx.logger)
    cjdev_ctx.config = config


def _init_config(cfg_path: Path, prev_cfg: Config) -> Config:
    try:
        answers = questionary.unsafe_prompt(
            _questions(cfg_path, prev_cfg if cfg_path.exists() else None),
            true_color=True,
        )

        if not _override_config(answers):
            return prev_cfg

        raw_cfg = {"container": {}, "cache": {}, "projects": {}}
        use_container = answers["use_container"]
        raw_cfg["container"]["use_container"] = use_container
        if use_container:
            raw_cfg["container"]["container_name"] = answers["container_name"]
        elif cfg_path.exists() and prev_cfg.container:
            raw_cfg["container"]["container_name"] = prev_cfg.container.container_name

        enable_cache = answers.get("enable_cache", False)
        raw_cfg["cache"]["enable"] = enable_cache
        if enable_cache:
            raw_cfg["cache"]["dir"] = answers.get("cache_dir", ".ccache")

        chosen_projects = (
            answers["chosen_projects"] if answers["chosen_projects"] else []
        )
        gc_user = answers["gitcode_user"]
        default_branch = answers["default_branch"]
        for project_name in chosen_projects:
            raw_cfg["projects"][project_name] = {
                "name": project_name,
                "path": project_name,
                "origin_url": f"https://gitcode.com/{gc_user}/{project_name}.git",
                "upstream_url": f"https://gitcode.com/Cangjie/{project_name}.git",
            }

        cfg = Config.model_validate(raw_cfg)
        cfg.save(cfg_path)
        logging.log(MESSAGE, f"Config saved successfully at {cfg_path.as_posix()}!")
        return cfg
    except KeyboardInterrupt:
        logging.log(MESSAGE, "Cancelled by user")
        return prev_cfg
    except ValidationError as e:
        logging.error(f"Incorrect project configuration:\n{e}")
        raise typer.Exit(1)


def _override_config(answers: Dict[str, Any]):
    return "override_config" not in answers or answers["override_config"]


def _questions(cfg_path: Path, prev_cfg: Optional[Config]):
    prechecked_projects = ["cangjie_compiler", "cangjie_runtime"]
    container_cfg_defaults = {
        "use_container": False,
        "container_name": "cjdev",
    }
    if prev_cfg:
        if prev_cfg.projects:
            projects_dump = prev_cfg.projects.model_dump(exclude_none=True)
            prechecked_projects = (
                list(projects_dump.keys())
                if len(projects_dump.keys()) > 0
                else prechecked_projects
            )
        if prev_cfg.container:
            container_cfg_defaults.update(
                prev_cfg.container.model_dump(exclude_none=True)
            )

    return [
        {
            "type": "confirm",
            "name": "override_config",
            "message": f"Override an existing configuration at {cfg_path.as_posix()}?",
            "default": False,
            "when": lambda _: cfg_path.exists(),
        },
        {
            "type": "confirm",
            "name": "use_container",
            "message": "Do you want to use a docker container for building?",
            "default": container_cfg_defaults["use_container"],
            "when": _override_config,
        },
        {
            "type": "text",
            "name": "container_name",
            "message": "Container name:",
            "default": container_cfg_defaults["container_name"],
            "when": lambda answers: (
                _override_config(answers) and answers["use_container"]
            ),
        },
        {
            "type": "confirm",
            "name": "enable_cache",
            "message": "Enable ccache?",
            "default": False,
            "when": _override_config,
        },
        {
            "type": "checkbox",
            "name": "chosen_projects",
            "message": "Select projects to setup:",
            "choices": list(
                map(
                    lambda p: Choice(p, checked=p in prechecked_projects),
                    DEFAULT_PROJECTS,
                )
            ),
            "when": _override_config,
            "validate": lambda chosen_projects: len(chosen_projects) > 0,
        },
        {
            "type": "text",
            "name": "default_branch",
            "message": "Default branch:",
            "default": "dev",
            "when": lambda answers: (
                _override_config(answers) and answers["chosen_projects"]
            ),
        },
        {
            "type": "text",
            "name": "gitcode_user",
            "message": "Your gitcode username:",
            "when": lambda answers: (
                _override_config(answers) and answers["chosen_projects"]
            ),
            "validate": lambda username: len(username) > 0,
        },
    ]


def _get_enabled_projects(config: Config) -> list[str]:
    enabled = []
    for key in DEFAULT_PROJECTS:
        proj = getattr(config.projects, key, None)
        if proj and proj.origin_url:
            enabled.append(proj.name or key)
    return enabled


def _configure_projects(config: Config):
    print("Select projects to configure:\n")

    project_choices = []
    for key in DEFAULT_PROJECTS:
        proj = getattr(config.projects, key, None)
        if proj and proj.origin_url:
            project_choices.append(key)
        else:
            project_choices.append(questionary.Choice(key, checked=False))

    selected = questionary.checkbox(
        "Select projects:",
        choices=project_choices,
    ).ask()

    if not selected:
        return

    username = questionary.text("Enter your gitcode username:", default="BonZer0").ask()

    for key in DEFAULT_PROJECTS:
        is_selected = key in (selected or [])
        if is_selected:
            origin_url = f"https://gitcode.com/{username}/{key}.git"
            upstream_url = f"https://gitcode.com/Cangjie/{key}.git"
            setattr(
                config.projects,
                key,
                Project(
                    name=key,
                    path=key,
                    origin_url=origin_url,
                    upstream_url=upstream_url,
                ),
            )
        else:
            setattr(config.projects, key, None)


def _configure_container(config: Config):
    use_container = questionary.confirm(
        "Use Docker container?", default=config.container.use_container
    ).ask()

    if use_container:
        host_workdir = (
            questionary.text(
                "Host workdir:", default=str(config.container.host_workdir or "")
            ).ask()
            or ""
        )
        container_workdir = (
            questionary.text(
                "Container workdir:",
                default=str(
                    config.container.container_workdir or "/home/cjdev/Projects"
                ),
            ).ask()
            or ""
        )
        container_name = (
            questionary.text(
                "Container name:", default=config.container.container_name or "cjdev"
            ).ask()
            or "cjdev"
        )

        config.container = ContainerConfig(
            use_container=True,
            host_workdir=Path(host_workdir) if host_workdir else None,
            container_workdir=Path(container_workdir) if container_workdir else None,
            container_name=container_name,
        )
    else:
        config.container = ContainerConfig(use_container=False)


def _configure_cache(config: Config, workspace_root: Path):
    enable_cache = questionary.confirm(
        "Enable ccache?", default=config.cache.enable
    ).ask()

    if enable_cache:
        default_dir = (
            config.cache.dir if config.cache.dir else workspace_root / ".ccache"
        )
        cache_dir = questionary.text("Cache directory:", default=str(default_dir)).ask()
        config.cache = CacheConfig(
            enable=True,
            dir=Path(cache_dir),
        )
    else:
        config.cache = CacheConfig(enable=False, dir=workspace_root / ".ccache")


def _save_config(config_path: Path, config: Config):
    lines = []

    lines.append("[container]")
    lines.append(f"use_container = {str(config.container.use_container).lower()}")
    if config.container.host_workdir:
        lines.append(f'host_workdir = "{config.container.host_workdir}"')
    if config.container.container_workdir:
        lines.append(f'container_workdir = "{config.container.container_workdir}"')
    lines.append(f'container_name = "{config.container.container_name}"')
    lines.append("")

    lines.append("[cache]")
    lines.append(f"enable = {str(config.cache.enable).lower()}")
    lines.append(f'dir = "{config.cache.dir}"')
    lines.append("")

    for key in DEFAULT_PROJECTS:
        proj = getattr(config.projects, key, None)
        if proj and proj.origin_url:
            lines.append(f"[projects.{key}]")
            lines.append(f'name = "{proj.name}"')
            lines.append(f'path = "{proj.path}"')
            lines.append(f'origin_url = "{proj.origin_url}"')
            if proj.upstream_url:
                lines.append(f'upstream_url = "{proj.upstream_url}"')
            lines.append("")

    config_path.write_text("\n".join(lines))
