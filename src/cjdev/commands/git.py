from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table
from typer import Typer

from cjdev.commands.context import CjDevContext

cli = Typer()
console = Console()


@cli.callback()
def git_callback(ctx: typer.Context):
    """Git multirepo management utils."""
    pass


@cli.command(name="init", short_help="Init multi-module environment")
def init_cmd(
    ctx: typer.Context,
    branch: Annotated[
        str, typer.Option("-b", "--branch", help="A remote branch for tracking updates")
    ] = "dev",
):
    """Init multi-module environment."""
    cjdev_ctx: CjDevContext = ctx.obj

    if cjdev_ctx.worktree_manager is None:
        console.print("[red]error[/red]: Worktree manager not initialized")
        raise typer.Exit(1)

    console.print(
        f"[blue]info[/blue]: Initializing cjdev with branch [yellow]{branch}[/yellow]"
    )
    cjdev_ctx.worktree_manager.init(branch)
    console.print("[green]success[/green]: Initialization complete")


@cli.command(name="start", short_help="Start a new branch")
def start_cmd(
    ctx: typer.Context,
    branch: Annotated[str, typer.Argument(help="Branch name to create")],
    base: Annotated[
        Optional[str], typer.Option("-b", "--base", help="Base branch to start from")
    ] = None,
    this: Annotated[
        bool, typer.Option("--this", help="Use current branch as base")
    ] = False,
):
    """Start a new branch with worktrees for all projects."""
    cjdev_ctx: CjDevContext = ctx.obj

    if cjdev_ctx.worktree_manager is None:
        console.print("[red]error[/red]: Worktree manager not initialized")
        raise typer.Exit(1)

    effective_base = base
    if this:
        effective_base = cjdev_ctx.worktree_manager._detect_current_branch() or "dev"

    if effective_base is None:
        effective_base = "dev"

    console.print(
        f"[blue]info[/blue]: Starting branch [yellow]{branch}[/yellow] from [yellow]{effective_base}[/yellow]"
    )
    success = cjdev_ctx.worktree_manager.start(branch, base, use_current=this)

    if success:
        console.print(f"[green]success[/green]: Branch {branch} created")
    else:
        console.print(f"[red]error[/red]: Failed to create branch {branch}")
        raise typer.Exit(1)


@cli.command(name="sync", short_help="Sync all repos with upstreams")
def sync_cmd(ctx: typer.Context):
    """Sync all repos with upstreams."""
    cjdev_ctx: CjDevContext = ctx.obj

    if cjdev_ctx.worktree_manager is None:
        console.print("[red]error[/red]: Worktree manager not initialized")
        raise typer.Exit(1)

    console.print("[blue]info[/blue]: Syncing all repos with upstreams...")
    cjdev_ctx.worktree_manager.sync()
    console.print("[green]success[/green]: Sync complete")


@cli.command(name="list", short_help="List all branches and worktrees")
def list_cmd(ctx: typer.Context):
    """List all branches and their worktrees."""
    cjdev_ctx: CjDevContext = ctx.obj

    if cjdev_ctx.worktree_manager is None:
        console.print("[red]error[/red]: Worktree manager not initialized")
        raise typer.Exit(1)

    branches = cjdev_ctx.worktree_manager.list()

    if not branches:
        console.print("[yellow]warning[/yellow]: No branches found")
        return

    root = cjdev_ctx.workspace.root if cjdev_ctx.workspace else Path(".")
    console.print(f"\n[bold]Repository Structure in {root}[/bold]")
    console.print("[bold]" + "=" * 50 + "[/bold]\n")

    for branch_name, worktrees in branches:
        console.print(f"[bold]Branch: {branch_name}[/bold]")

        if not worktrees:
            console.print("  (no repositories)")
            continue

        for wt in worktrees:
            status = wt.branch if not wt.is_detached else "detached"
            console.print(f"  - {wt.path.name} (branch: {status})")

        console.print()


@cli.command(name="remove-branch", short_help="Remove a branch and all worktrees")
def remove_branch_cmd(
    ctx: typer.Context,
    branch: Annotated[str, typer.Argument(help="Branch name to remove")],
):
    """Remove a branch and all its worktrees."""
    cjdev_ctx: CjDevContext = ctx.obj

    if cjdev_ctx.worktree_manager is None:
        console.print("[red]error[/red]: Worktree manager not initialized")
        raise typer.Exit(1)

    console.print(f"[blue]info[/blue]: Removing branch [yellow]{branch}[/yellow]...")
    cjdev_ctx.worktree_manager.remove_branch(branch)
    console.print(f"[green]success[/green]: Branch {branch} removed")


@cli.command(name="upload", short_help="Create pull requests to upstreams")
def upload_cmd(
    ctx: typer.Context,
    title: Annotated[
        str, typer.Option("-T", "--title", help="Title for the pull request")
    ],
):
    """Create pull requests to upstreams with committed changes."""
    console.print("[yellow]warning[/yellow]: upload command not implemented yet")
