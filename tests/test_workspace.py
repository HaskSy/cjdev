from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from cjdev.config.workspace import Workspace, WorkspaceLocation
from cjdev.commands.context import Config, ContainerConfig, CacheConfig, Project


class TestWorkspace:
    def test_workspace_initialization(self, tmp_path):
        workspace = Workspace(tmp_path)
        assert workspace.root == tmp_path
        assert workspace.bare_dir == tmp_path / ".bare"
        assert workspace.config_file == tmp_path / ".git-mm"

    def test_host_path_detection_no_git(self, tmp_path):
        workspace = Workspace(tmp_path)
        host = workspace.host_path()
        assert host == tmp_path

    def test_bare_dir_creation(self, tmp_path):
        workspace = Workspace(tmp_path)
        bare = workspace.bare_dir
        assert bare.parent == tmp_path
        assert bare.name == ".bare"

    def test_detect_from_pwd_no_git(self, tmp_path):
        workspace = Workspace(tmp_path)
        result = workspace.detect_from_pwd(tmp_path)
        assert result is None


class TestWorktreeManager:
    def test_bare_repo_dir(self, tmp_path):
        from cjdev.config.workspace import Workspace
        from cjdev.config.worktree import GitConfig, WorktreeManager

        workspace = Workspace(tmp_path)
        git_config = GitConfig(tmp_path / ".git-mm")
        manager = WorktreeManager(workspace, git_config)

        bare_dir = manager.bare_repo_dir("cangjie_compiler")
        assert bare_dir == tmp_path / ".bare" / "cangjie_compiler.git"

    def test_worktree_dir(self, tmp_path):
        from cjdev.config.workspace import Workspace
        from cjdev.config.worktree import GitConfig, WorktreeManager

        workspace = Workspace(tmp_path)
        git_config = GitConfig(tmp_path / ".git-mm")
        manager = WorktreeManager(workspace, git_config)

        wt_dir = manager.worktree_dir("dev", "cangjie_compiler")
        assert wt_dir == tmp_path / "dev" / "cangjie_compiler"

    def test_detect_orphan_worktrees_no_worktrees(self, tmp_path):
        from cjdev.config.worktree import GitConfig, WorktreeManager

        workspace = Workspace(tmp_path)
        git_config = GitConfig(tmp_path / ".git-mm")

        config = Config()
        config.projects.cangjie_compiler = Project(
            name="cangjie_compiler",
            path="cangjie_compiler",
            origin_url="https://gitcode.com/test/cangjie_compiler.git",
            upstream_url="https://gitcode.com/Cangjie/cangjie_compiler.git",
        )

        manager = WorktreeManager(workspace, git_config, config)

        orphans = manager.detect_orphan_worktrees()
        assert orphans == []

    def test_detect_orphan_worktrees_with_orphan(self, tmp_path):
        from cjdev.config.worktree import GitConfig, WorktreeManager

        workspace = Workspace(tmp_path)
        git_config = GitConfig(tmp_path / ".git-mm")

        config = Config()
        config.projects.cangjie_compiler = Project(
            name="cangjie_compiler",
            path="cangjie_compiler",
            origin_url="https://gitcode.com/test/cangjie_compiler.git",
            upstream_url="https://gitcode.com/Cangjie/cangjie_compiler.git",
        )

        branch_dir = tmp_path / "dev"
        branch_dir.mkdir(parents=True)

        repo_dir = branch_dir / "cangjie_compiler"
        repo_dir.mkdir(parents=True)

        git_file = repo_dir / ".git"
        git_file.write_text(
            "gitdir: /nonexistent/.bare/cangjie_compiler.git/worktrees/cangjie_compiler"
        )

        manager = WorktreeManager(workspace, git_config, config)

        orphans = manager.detect_orphan_worktrees()

        assert len(orphans) == 1
        assert orphans[0][0] == repo_dir
        assert orphans[0][1] == "dev"

    def test_detect_orphan_worktrees_excludes_regular_git(self, tmp_path):
        from cjdev.config.worktree import GitConfig, WorktreeManager
        import subprocess

        workspace = Workspace(tmp_path)
        git_config = GitConfig(tmp_path / ".git-mm")

        config = Config()

        branch_dir = tmp_path / "dev"
        branch_dir.mkdir(parents=True)

        repo_dir = branch_dir / "some_regular_repo"
        repo_dir.mkdir(parents=True)

        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)

        manager = WorktreeManager(workspace, git_config, config)

        orphans = manager.detect_orphan_worktrees()

        assert orphans == []


class TestGitConfig:
    def test_git_config_initialization(self, tmp_path):
        from cjdev.config.worktree import GitConfig

        config_file = tmp_path / ".git-mm"
        git_config = GitConfig(config_file)
        assert git_config.config_file == config_file

    def test_git_config_get_no_file(self, tmp_path):
        from cjdev.config.worktree import GitConfig

        config_file = tmp_path / ".git-mm"
        git_config = GitConfig(config_file)
        result = git_config.get("module.test.path")
        assert result is None

    def test_git_config_iter_no_file(self, tmp_path):
        from cjdev.config.worktree import GitConfig

        config_file = tmp_path / ".git-mm"
        git_config = GitConfig(config_file)
        result = git_config.iter_paths()
        assert result == []
