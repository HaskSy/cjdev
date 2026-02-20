from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from git import Git, Repo
from rich.console import Console

from cjdev.config.workspace import Workspace

if TYPE_CHECKING:
    from cjdev.commands.context import Config

console = Console()


@dataclass
class ProjectInfo:
    name: str
    path: str
    origin_url: str
    upstream_url: str
    branch: str


@dataclass
class WorktreeInfo:
    path: Path
    branch: str
    is_detached: bool


class GitConfig:
    def __init__(self, config_file: Path):
        self.config_file = config_file

    def get(self, key: str) -> Optional[str]:
        if not self.config_file.exists():
            return None
        try:
            git = Git(str(self.config_file.parent))
            return git.config(key, get=True)
        except Exception:
            pass
        return None

    def set(self, key: str, value: str) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        git = Git(str(self.config_file.parent))
        git.config(key, value)

    def iter_paths(self) -> list[str]:
        if not self.config_file.exists():
            return []
        try:
            git = Git(str(self.config_file.parent))
            config_list = git.config("--list")
            paths = []
            for line in config_list.splitlines():
                if line.startswith("module."):
                    parts = line.split("=")
                    if len(parts) == 2:
                        key = parts[0]
                        if ".path" in key:
                            path_value = parts[1].strip()
                            if path_value and path_value not in paths:
                                paths.append(path_value)
            return paths
        except Exception:
            pass
        return []


class WorktreeManager:
    def __init__(
        self,
        workspace: Workspace,
        git_config: GitConfig,
        config: Optional["Config"] = None,
    ):
        self.workspace = workspace
        self.git_config = git_config
        self._config = config

    def get_project_info(self, project_path: str) -> Optional[ProjectInfo]:
        if self._config:
            for key, proj in self._config.projects.model_dump().items():
                if proj and proj.get("path") == project_path and proj.get("origin_url"):
                    return ProjectInfo(
                        name=proj.get("name") or key,
                        path=proj.get("path") or key,
                        origin_url=proj["origin_url"],
                        upstream_url=proj.get("upstream_url", ""),
                        branch="dev",
                    )

        name = Path(project_path).name
        origin = self.git_config.get(f"module.{project_path}.origin")
        upstream = self.git_config.get(f"module.{project_path}.upstream")
        branch = self.git_config.get(f"module.{project_path}.branch")

        if origin is None:
            return None

        return ProjectInfo(
            name=name,
            path=project_path,
            origin_url=origin,
            upstream_url=upstream or "",
            branch=branch or "dev",
        )

    def get_all_projects(self) -> list[ProjectInfo]:
        if self._config:
            projects = []
            config_dict = self._config.projects.model_dump()
            for key, p in config_dict.items():
                if p and p.get("origin_url"):
                    projects.append(
                        ProjectInfo(
                            name=p.get("name") or key,
                            path=p.get("path") or key,
                            origin_url=p["origin_url"],
                            upstream_url=p.get("upstream_url", ""),
                            branch="dev",
                        )
                    )
            return projects

        projects = []
        for path in self.git_config.iter_paths():
            info = self.get_project_info(path)
            if info:
                projects.append(info)
        return projects

    def bare_repo_dir(self, project_name: str) -> Path:
        return self.workspace.bare_dir / f"{project_name}.git"

    def worktree_dir(self, branch: str, project_name: str) -> Path:
        return self.workspace.root / branch / project_name

    def init(self, branch: str = "dev") -> None:
        self.workspace.bare_dir.mkdir(parents=True, exist_ok=True)

        for project in self.get_all_projects():
            self._init_project(project, branch)

    def _init_project(self, project: ProjectInfo, branch: str) -> None:
        bare_dir = self.bare_repo_dir(project.name)

        console.print(f"[blue]info[/blue]: Setting up [cyan]{project.name}[/cyan]...")

        if not bare_dir.exists():
            console.print(f"  Cloning bare repo from {project.origin_url}...")
            Repo.clone_from(
                project.origin_url,
                str(bare_dir),
                bare=True,
                branch=branch,
            )

        repo = Repo(bare_dir)
        if repo.remotes.origin.url != project.origin_url:
            repo.remotes.origin.set_url(project.origin_url)

        upstream_exists = any(r.name == "upstream" for r in repo.remotes)
        if not upstream_exists and project.upstream_url:
            repo.create_remote("upstream", project.upstream_url)

        worktree_dir = self.worktree_dir(branch, project.name)
        if not worktree_dir.exists():
            console.print(f"  Creating worktree at {worktree_dir}...")
            repo.git.worktree("add", str(worktree_dir), branch)

    def start(
        self, branch: str, base_branch: Optional[str] = None, use_current: bool = False
    ) -> bool:
        if use_current:
            base_branch = self._detect_current_branch()

        if base_branch is None:
            base_branch = "dev"

        (self.workspace.root / branch).mkdir(parents=True, exist_ok=True)

        all_success = True
        for project in self.get_all_projects():
            success = self._start_project(project, branch, base_branch)
            if not success:
                all_success = False

        return all_success

    def _detect_current_branch(self) -> Optional[str]:
        location = self.workspace.detect_from_pwd()
        if location:
            return location.branch
        return None

    def _start_project(
        self, project: ProjectInfo, branch: str, base_branch: str
    ) -> bool:
        bare_dir = self.bare_repo_dir(project.name)

        console.print(
            f"[blue]info[/blue]: Setting up [cyan]{project.name}[/cyan] on branch [yellow]{branch}[/yellow]..."
        )

        if not bare_dir.exists():
            console.print(
                f"[red]error[/red]: Bare repo {bare_dir} does not exist. Run `git init` first."
            )
            return False

        repo = Repo(bare_dir)

        origin_refs = [ref.name for ref in repo.remotes.origin.refs]
        if f"origin/{branch}" in origin_refs:
            console.print(f"  Branch {branch} found in origin, fetching...")
            repo.remotes.origin.fetch(branch)
            if branch not in repo.heads:
                repo.git.branch(branch, f"origin/{branch}")
        else:
            if repo.remotes:
                upstream_refs = (
                    [ref.name for ref in repo.remotes.upstream.refs]
                    if hasattr(repo.remotes, "upstream")
                    else []
                )
                if f"upstream/{branch}" in upstream_refs:
                    console.print(f"  Branch {branch} found in upstream, fetching...")
                    repo.remotes.upstream.fetch(branch)
                    if branch not in repo.heads:
                        repo.git.branch(branch, f"upstream/{branch}")
                else:
                    base_exists_remote = f"origin/{base_branch}" in [
                        ref.name for ref in repo.remotes.origin.refs
                    ]
                    if not base_exists_remote:
                        console.print(f"  Fetching origin/{base_branch}...")
                        repo.remotes.origin.fetch(base_branch)

                    if base_branch not in repo.heads:
                        if f"origin/{base_branch}" in [
                            ref.name for ref in repo.remotes.origin.refs
                        ]:
                            repo.git.update_ref(
                                f"refs/heads/{base_branch}",
                                f"refs/remotes/origin/{base_branch}",
                            )

                    if branch not in repo.heads:
                        repo.git.branch(branch, base_branch)

        worktree_dir = self.worktree_dir(branch, project.name)
        if not worktree_dir.exists():
            console.print(f"  Creating worktree at {worktree_dir}...")
            repo.git.worktree("add", str(worktree_dir), branch)
        else:
            console.print(f"  Worktree already exists, checking out {branch}...")
            worktree_repo = Repo(worktree_dir)
            worktree_repo.git.checkout(branch)

        return True

    def sync(self) -> None:
        for project in self.get_all_projects():
            self._sync_project(project)

    def _sync_project(self, project: ProjectInfo) -> None:
        bare_dir = self.bare_repo_dir(project.name)
        if not bare_dir.exists():
            console.print(
                f"[yellow]warning[/yellow]: Bare repo {bare_dir} does not exist, skipping..."
            )
            return

        console.print(f"[blue]info[/blue]: Syncing [cyan]{project.name}[/cyan]...")

        base_branch = project.branch

        repo = Repo(bare_dir)
        if repo.remotes:
            repo.remotes.upstream.fetch()

        repo.git.checkout(base_branch)
        repo.git.rebase(f"upstream/{base_branch}")
        repo.git.push("origin", base_branch, force=True)

        worktree_dir = self.worktree_dir(base_branch, project.name)
        if worktree_dir.exists():
            worktree_repo = Repo(worktree_dir)
            worktree_repo.git.rebase(base_branch)

    def list(self) -> list[tuple[str, list[WorktreeInfo]]]:
        branch_worktrees: dict[str, list[WorktreeInfo]] = {}

        if not self.workspace.root.exists():
            return []

        for branch_dir in self.workspace.root.iterdir():
            if branch_dir.name == ".bare" or not branch_dir.is_dir():
                continue

            branch_name = branch_dir.name
            worktrees = []

            for repo_dir in branch_dir.iterdir():
                if not repo_dir.is_dir():
                    continue

                worktree_info = self._detect_worktree(repo_dir)
                if worktree_info:
                    worktrees.append(worktree_info)

            if worktrees:
                branch_worktrees[branch_name] = worktrees

        return sorted(branch_worktrees.items(), key=lambda x: x[0])

    def detect_orphan_worktrees(self) -> list[tuple[Path, str, str]]:
        orphans = []

        if not self.workspace.root.exists():
            return orphans

        for branch_dir in self.workspace.root.iterdir():
            if branch_dir.name == ".bare" or not branch_dir.is_dir():
                continue

            for repo_dir in branch_dir.iterdir():
                if not repo_dir.is_dir():
                    continue

                git_file = repo_dir / ".git"
                if not git_file.exists() or not git_file.is_file():
                    continue

                content = git_file.read_text()
                if "worktrees" not in content:
                    continue

                git_dir = self._get_git_dir(repo_dir)
                if git_dir is None or not git_dir.exists():
                    bare_path = content.replace("gitdir: ", "").strip()
                    bare_path = Path(bare_path).parent.parent
                    branch = branch_dir.name
                    orphans.append((repo_dir, branch, bare_path))

        return orphans

    def reattach_all(self) -> None:
        orphans = self.detect_orphan_worktrees()

        for repo_dir, branch, old_bare_path in orphans:
            project_name = repo_dir.name
            bare_dir = self.bare_repo_dir(project_name)

            console.print(
                f"[blue]info[/blue]: Reattaching [cyan]{project_name}[/cyan] on branch [yellow]{branch}[/yellow]..."
            )

            if not bare_dir.exists():
                for proj in self.get_all_projects():
                    if proj.name == project_name:
                        console.print(f"  Cloning bare repo from {proj.origin_url}...")
                        Repo.clone_from(proj.origin_url, str(bare_dir), bare=True)
                        break

            repo = Repo(bare_dir) if bare_dir.exists() else None
            if not repo:
                continue

            branch_exists = branch in repo.heads
            if not branch_exists:
                origin_refs = (
                    [ref.name for ref in repo.remotes.origin.refs]
                    if repo.remotes
                    else []
                )
                if f"origin/{branch}" in origin_refs:
                    console.print(f"  Fetching branch {branch} from origin...")
                    repo.remotes.origin.fetch(branch)
                else:
                    upstream_refs = (
                        [ref.name for ref in repo.remotes.upstream.refs]
                        if hasattr(repo.remotes, "upstream") and repo.remotes
                        else []
                    )
                    if f"upstream/{branch}" in upstream_refs:
                        console.print(f"  Fetching branch {branch} from upstream...")
                        repo.remotes.upstream.fetch(branch)

            console.print(f"  Removing old worktree and recreating...")

            if repo_dir.exists():
                shutil.rmtree(repo_dir)

            if branch in repo.heads:
                repo.git.worktree("add", str(repo_dir), branch)
            else:
                console.print(
                    f"  [yellow]warning[/yellow]: Branch {branch} not found, skipping {project_name}"
                )

            console.print(f"  Reattached!")

    def _detect_worktree(self, path: Path) -> Optional[WorktreeInfo]:
        git_file = path / ".git"
        if not git_file.exists():
            return None

        if git_file.is_file():
            content = git_file.read_text()
            if "worktrees" in content:
                current_branch = self._get_current_branch(path)
                return WorktreeInfo(
                    path=path,
                    branch=current_branch or "detached",
                    is_detached=current_branch is None,
                )

        return None

    def _get_git_dir(self, path: Path) -> Optional[Path]:
        try:
            repo = Repo(path)
            gd = repo.git_dir
            if gd:
                return Path(gd)
        except Exception:
            return None

    def _get_current_branch(self, path: Path) -> Optional[str]:
        try:
            repo = Repo(path)
            return repo.active_branch.name
        except Exception:
            return None

    def remove_branch(self, branch: str) -> None:
        for project in self.get_all_projects():
            self._remove_project_worktree(project, branch)

        branch_dir = self.workspace.root / branch
        if branch_dir.exists():
            shutil.rmtree(branch_dir)
            console.print(f"[blue]info[/blue]: Removed branch directory {branch_dir}")

    def _remove_project_worktree(self, project: ProjectInfo, branch: str) -> None:
        bare_dir = self.bare_repo_dir(project.name)
        if not bare_dir.exists():
            return

        worktree_dir = self.worktree_dir(branch, project.name)

        repo = Repo(bare_dir)
        worktrees = repo.git.worktree("list").splitlines()
        for line in worktrees:
            if worktree_dir.name in line and branch in line:
                repo.git.worktree("remove", str(worktree_dir), force=True)
                break

        if branch in repo.heads:
            repo.git.branch("-d", branch)
