import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, final

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import Url
from tomlkit import dumps, item, parse, register_encoder
from tomlkit.exceptions import ConvertError

from cjdev.config.workspace import Workspace
from cjdev.config.worktree import GitConfig, WorktreeManager


@final
class CjDevContext:
    config_path: Path
    config: "Config"
    logger: logging.Logger
    verbose: bool
    workspace: Optional[Workspace] = None
    worktree_manager: Optional[WorktreeManager] = None

    def __init__(
        self,
        config_path: Path,
        config: "Config",
        logger: logging.Logger,
        verbose: bool,
        workspace: Optional[Workspace] = None,
        worktree_manager: Optional[WorktreeManager] = None,
    ):
        self.config_path = config_path
        self.config = config
        self.logger = logger
        self.verbose = verbose
        self.workspace = workspace
        self.worktree_manager = worktree_manager

    @classmethod
    def create(
        cls,
        config_path: Path,
        config: "Config",
        logger: logging.Logger | None = None,
        verbose: bool = False,
    ) -> "CjDevContext":
        if logger is None:
            logger = logging.getLogger("cjdev")
        workspace_root = config_path.parent
        workspace = Workspace(workspace_root, config)
        git_config = GitConfig(workspace.config_file)
        worktree_manager = WorktreeManager(workspace, git_config, config)

        return cls(
            config_path=config_path,
            config=config,
            logger=logger,
            verbose=verbose,
            workspace=workspace,
            worktree_manager=worktree_manager,
        )


@final
class CacheConfig(BaseModel):
    enable: bool = False
    dir: Path = Path(".ccache")

    @field_validator("dir", mode="before")
    @classmethod
    def resolve_dir(cls, v: str | Path | None) -> Path:
        if v is None:
            return Path(".ccache")
        if isinstance(v, str):
            return Path(v)
        return v


@final
class ContainerConfig(BaseModel):
    use_container: bool = False
    container_name: Optional[str] = None
    host_workdir: Optional[Path] = None
    container_workdir: Optional[Path] = None

    @field_validator("host_workdir", "container_workdir", mode="before")
    @classmethod
    def resolve_paths(cls, v: str | Path | None) -> Optional[Path]:
        if v is None:
            return None
        if isinstance(v, str):
            return Path(v)
        return v

    @model_validator(mode="after")
    def validate_fields_when_container_used(self) -> "ContainerConfig":
        if not self.use_container:
            return self

        missing_fields = []
        if not self.container_name:
            missing_fields.append("container_name")
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        return self


@final
class Project(BaseModel):
    name: str = ""
    path: str = ""
    origin_url: str = ""
    upstream_url: str = ""

    @property
    def path_obj(self) -> Path:
        return Path(self.path)


@final
class ProjectConfig(BaseModel):
    path: Path
    origin_url: Url
    upstream_url: Url
    default_branch: str


@final
class ProjectsConfig(BaseModel):
    cangjie_compiler: Optional[Project] = None
    cangjie_runtime: Optional[Project] = None
    cangjie_test: Optional[Project] = None
    cangjie_multiplatform_interop: Optional[Project] = None
    cangjie_stdx: Optional[Project] = None
    cangjie_tools: Optional[Project] = None
    cangjie_test_framework: Optional[Project] = None


_CONFIG_FILE_NAME = "cjdev.toml"


@final
class Config(BaseModel):
    container: ContainerConfig = ContainerConfig()
    cache: CacheConfig = CacheConfig()
    projects: ProjectsConfig = ProjectsConfig()

    @classmethod
    def load(cls, fpath: Path) -> "Config":
        text = fpath.read_text()
        parsed = parse(text)
        return cls.model_validate(parsed)

    @classmethod
    def load_or_default(cls) -> Tuple[Path, "Config"]:
        config = cls()
        config_path = cls.find_config()
        if config_path.is_file():
            text = config_path.read_text()
            parsed = parse(text)
            config = cls.model_validate(parsed)
        return config_path, config

    def save(self, path: Path) -> None:
        if not path.is_file():
            path.joinpath(_CONFIG_FILE_NAME)

        dict = self.model_dump(exclude_none=True)
        toml = dumps(dict)
        path.write_text(toml)

    @classmethod
    def find_config(cls) -> Path:
        cwd = Path.cwd()
        config = cwd / _CONFIG_FILE_NAME
        first_attempt = config

        while not config.is_file():
            parent = cwd.parent
            if parent == cwd:
                break
            cwd = parent
            config = cwd / _CONFIG_FILE_NAME

        return config if config.is_file() else first_attempt


@register_encoder
def _path_encoder(obj, _parent=None, _sort_keys=False):
    if isinstance(obj, Path):
        return item(obj.as_posix())
    raise ConvertError("Not a Path")


@register_encoder
def _url_encoder(obj, _parent=None, _sort_keys=False):
    if isinstance(obj, Url):
        return item(str(obj))
    raise ConvertError("Not a Url")
