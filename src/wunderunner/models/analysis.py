"""Pydantic models for project analysis."""

from pydantic import BaseModel


class ProjectStructure(BaseModel):
    """Result of project structure analysis."""

    framework: str | None = None
    runtime: str
    runtime_version: str | None = None
    package_manager: str | None = None
    package_manager_version: str | None = None  # For corepack (e.g., "pnpm@9.1.0")
    dependencies: list[str] = []
    entry_point: str | None = None


class BuildStrategy(BaseModel):
    """Result of build strategy analysis."""

    monorepo: bool = False
    monorepo_tool: str | None = None
    workspaces: list[str] = []
    native_dependencies: list[str] = []  # e.g., ["sharp", "bcrypt", "canvas"]
    build_command: str | None = None
    start_command: str | None = None
    multi_stage_recommended: bool = False


class EnvVar(BaseModel):
    """A discovered environment variable."""

    name: str
    required: bool = True
    default: str | None = None
    secret: bool = False
    service: str | None = None


class ServiceConfig(BaseModel):
    """A service to create in docker-compose."""

    type: str  # "postgres", "redis", "mysql", "mongodb"
    env_vars: list[str]  # Names of env vars this service satisfies


class CodeStyle(BaseModel):
    """Result of code style analysis."""

    uses_typescript: bool = False
    uses_eslint: bool = False
    uses_prettier: bool = False
    test_framework: str | None = None
    dockerfile_exists: bool = False
    compose_exists: bool = False


class Analysis(BaseModel):
    """Combined result of all analysis passes."""

    project_structure: ProjectStructure
    build_strategy: BuildStrategy
    env_vars: list[EnvVar] = []
    code_style: CodeStyle
    services: list[ServiceConfig] = []  # Confirmed services to create
