from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from git import Repo
from rich.console import Console

if TYPE_CHECKING:
    from cjdev.commands.context import Config

console = Console()


@dataclass
class WorkspaceLocation:
    root: Path
    branch: str
    is_worktree: bool


class Workspace:
    def __init__(self, root: Path, config: Optional["Config"] = None):
        self._root = root
        self._config = config
        self._host_path: Optional[Path] = None
        self._container_path: Optional[Path] = None
        self._detected_location: Optional[WorkspaceLocation] = None

    @property
    def root(self) -> Path:
        return self._root

    @property
    def bare_dir(self) -> Path:
        return self._root / ".bare"

    @property
    def config_file(self) -> Path:
        return self._root / ".git-mm"

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def project_path(self, branch: str, project_name: str) -> Path:
        return self._root / branch / project_name

    def to_container_path(self, host_path: Path) -> Path:
        if self._config and self._config.container.use_container:
            container_workdir = self._config.container.container_workdir
            if container_workdir:
                rel = host_path.relative_to(self._root)
                return container_workdir / rel
        return host_path

    def to_host_path(self, container_path: Path) -> Path:
        if self._config and self._config.container.use_container:
            container_workdir = self._config.container.container_workdir
            if container_workdir:
                try:
                    rel = container_path.relative_to(container_workdir)
                    return self._root / rel
                except ValueError:
                    pass
        return container_path

    def host_path(self) -> Path:
        if self._host_path is None:
            self._host_path = self._detect_host_path()
        return self._host_path

    def container_path(self) -> Path:
        if self._container_path is None:
            self._container_path = self._detect_container_path()
        return self._container_path

    def _detect_host_path(self) -> Path:
        location = self.detect_from_pwd()
        if location:
            return location.root
        return self._root

    def _detect_container_path(self) -> Path:
        if self._config and self._config.container.use_container:
            container_workdir = self._config.container.container_workdir
            if container_workdir:
                return container_workdir
        return self.host_path()

    def detect_from_pwd(
        self, cwd: Optional[Path] = None
    ) -> Optional[WorkspaceLocation]:
        if cwd is None:
            cwd = Path.cwd()

        current = cwd
        while current != current.parent:
            git_top = self._get_git_toplevel(current)
            if git_top:
                repo_name = git_top.name
                git_dir = self._get_git_dir(git_top)
                if git_dir and str(git_dir).startswith(
                    str(self.bare_dir / f"{repo_name}.git/worktrees")
                ):
                    branch = self._get_current_branch(git_top)
                    return WorkspaceLocation(
                        root=git_top.parent,
                        branch=branch or "unknown",
                        is_worktree=True,
                    )
                current = git_top.parent
            else:
                if str(current).startswith(str(self._root)):
                    branch = current.name
                    if branch != ".bare":
                        if self._is_branch_in_bare(branch):
                            return WorkspaceLocation(
                                root=current,
                                branch=branch,
                                is_worktree=True,
                            )
                current = current.parent

        return None

    def _get_git_toplevel(self, path: Path) -> Optional[Path]:
        try:
            repo = Repo(path, search_parent_directories=True)
            wd = repo.working_dir
            if wd:
                return Path(wd)
        except Exception:
            return None

    def _get_git_dir(self, path: Path) -> Optional[Path]:
        try:
            repo = Repo(path, search_parent_directories=True)
            git_dir = repo.git_dir
            if git_dir:
                return Path(git_dir)
        except Exception:
            return None

    def _get_current_branch(self, path: Path) -> Optional[str]:
        try:
            repo = Repo(path)
            return repo.active_branch.name
        except Exception:
            return None

    def _is_branch_in_bare(self, branch: str) -> bool:
        try:
            compiler_bare = self.bare_dir / "cangjie_compiler.git"
            if not compiler_bare.exists():
                return False

            repo = Repo(compiler_bare)
            worktrees = repo.git.worktree("list").splitlines()
            for line in worktrees:
                parts = line.split()
                if len(parts) >= 3:
                    worktree_path = Path(parts[0])
                    worktree_branch = parts[2].strip("[]")
                    if worktree_branch == branch:
                        return True
        except Exception:
            pass
        return False

    def ensure_inside(self) -> WorkspaceLocation:
        location = self.detect_from_pwd()
        if location is None:
            console.print(
                f"[red]error[/red]: not in a cjdev workspace directory `{self._root}`"
            )
            raise SystemExit(1)
        return location


def get_workspace_root() -> Path:
    env_root = Path(__file__).parent.parent.parent.parent
    return env_root
