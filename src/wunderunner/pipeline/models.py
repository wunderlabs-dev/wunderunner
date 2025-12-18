"""Pydantic models for pipeline artifacts."""

from pydantic import BaseModel, Field


class RuntimeFindings(BaseModel):
    """Output from runtime-detector specialist."""

    language: str = Field(description="Runtime language: python, node, go, rust")
    version: str | None = Field(default=None, description="Version string: 3.11, 20, 1.21")
    framework: str | None = Field(default=None, description="Web framework: fastapi, express, gin")
    entrypoint: str | None = Field(default=None, description="Main file path: src/main.py")


class NativeDependency(BaseModel):
    """A native/system dependency required for the build."""

    name: str = Field(description="Package name: libpq-dev, build-essential")
    reason: str = Field(description="Why it's needed: psycopg2 requires PostgreSQL client")


class DependencyFindings(BaseModel):
    """Output from dependency-analyzer specialist."""

    package_manager: str = Field(description="Package manager: pip, uv, npm, yarn, pnpm")
    package_manager_version: str | None = Field(default=None, description="Version: pnpm@9.1.0")
    native_deps: list[NativeDependency] = Field(default_factory=list)
    build_command: str | None = Field(default=None, description="Build command: npm run build")
    start_command: str | None = Field(default=None, description="Start command: npm start")


class EnvVarFinding(BaseModel):
    """An environment variable discovered in the project."""

    name: str = Field(description="Variable name: DATABASE_URL")
    required: bool = Field(default=True, description="Whether the app fails without it")
    secret: bool = Field(default=False, description="Whether it contains sensitive data")
    default: str | None = Field(default=None, description="Default value if any")
    service: str | None = Field(default=None, description="Related service: postgres, redis")


class ConfigFindings(BaseModel):
    """Output from config-finder specialist."""

    env_vars: list[EnvVarFinding] = Field(default_factory=list)
    config_files: list[str] = Field(
        default_factory=list, description="Config files found: .env.example"
    )


class ServiceFinding(BaseModel):
    """A backing service discovered in the project."""

    type: str = Field(description="Service type: postgres, redis, rabbitmq")
    version: str | None = Field(default=None, description="Version if detected: 15, 7")
    env_var: str | None = Field(default=None, description="Related env var: DATABASE_URL")


class ServiceFindings(BaseModel):
    """Output from service-detector specialist."""

    services: list[ServiceFinding] = Field(default_factory=list)
