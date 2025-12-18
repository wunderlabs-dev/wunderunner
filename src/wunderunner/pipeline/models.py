"""Pydantic models for pipeline artifacts."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


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


class ResearchResult(BaseModel):
    """Combined output from all RESEARCH phase specialists."""

    runtime: RuntimeFindings
    dependencies: DependencyFindings
    config: ConfigFindings
    services: ServiceFindings


class VerificationStep(BaseModel):
    """A verification step to run after file generation."""

    command: str = Field(description="Command to run: docker build -t app .")
    expected: str = Field(description="Expected outcome: exit 0, 200 OK")
    phase: str = Field(default="BUILD", description="Phase: BUILD, START, HEALTHCHECK")


class ContainerizationPlan(BaseModel):
    """Output from PLAN phase - exact file contents."""

    summary: str = Field(description="Brief description of the containerization approach")
    dockerfile: str = Field(description="Exact Dockerfile content")
    compose: str | None = Field(default=None, description="Exact docker-compose.yaml content")
    verification: list[VerificationStep] = Field(default_factory=list)
    reasoning: str = Field(description="Why this approach was chosen")
    constraints_honored: list[str] = Field(
        default_factory=list, description="Constraints from fixes.json"
    )


class ConstraintStatus(str, Enum):
    """Status of a constraint."""

    HARD = "hard"  # Must be honored
    SOFT = "soft"  # Can be reconsidered with reasoning


class FixError(BaseModel):
    """Error that triggered a fix attempt."""

    type: str = Field(description="Error type: missing_dependency, build_failed")
    message: str = Field(description="Error message")
    exit_code: int | None = Field(default=None)


class FixChange(BaseModel):
    """A single change made during a fix attempt."""

    file: str = Field(description="File that was changed")
    before: str = Field(description="Content before change")
    after: str = Field(description="Content after change")


class FixAttempt(BaseModel):
    """Record of a single fix attempt."""

    attempt: int = Field(description="Attempt number: 1, 2, 3")
    timestamp: datetime = Field(default_factory=_utc_now)
    phase: str = Field(description="Phase where error occurred: BUILD, START, HEALTHCHECK")
    error: FixError
    diagnosis: str = Field(description="What we think caused the error")
    changes: list[FixChange] = Field(default_factory=list)
    outcome: str = Field(description="success, failure, partial")


class Constraint(BaseModel):
    """A constraint derived from a successful fix."""

    id: str = Field(description="Unique constraint ID: c1, c2")
    rule: str = Field(description="The constraint: MUST include pandas")
    reason: str = Field(description="Why: Required by app.py import")
    from_attempt: int = Field(description="Which attempt derived this")
    added_at: datetime = Field(default_factory=_utc_now)
    success_count: int = Field(default=0, description="Successful builds since added")
    status: ConstraintStatus = Field(default=ConstraintStatus.HARD)


class FixHistory(BaseModel):
    """Complete fix history for a project."""

    project: str = Field(description="Project name")
    created_at: datetime = Field(default_factory=_utc_now)
    attempts: list[FixAttempt] = Field(default_factory=list)
    active_constraints: list[Constraint] = Field(default_factory=list)


class ExhaustionItem(BaseModel):
    """An approach that could be tried."""

    approach: str = Field(description="What could be tried: CPU-only torch")
    attempted: bool = Field(default=False, description="Whether it's been tried")


class ErrorAnalysis(BaseModel):
    """Output from ERROR-RESEARCH phase."""

    error_summary: str = Field(description="Brief error description")
    root_cause: str = Field(description="What we think caused it")
    fix_history_review: str = Field(description="Summary of previous attempts")
    exhaustion_status: list[ExhaustionItem] = Field(default_factory=list)
    recommendation: str = Field(description="continue or stop")
    suggested_approach: str | None = Field(default=None, description="What to try next")


class FixPlan(BaseModel):
    """Output from FIX-PLAN phase - surgical changes."""

    summary: str = Field(description="Brief description of the fix")
    dockerfile: str = Field(description="Updated Dockerfile content")
    compose: str | None = Field(default=None, description="Updated compose if needed")
    changes_description: str = Field(description="What changed and why")
    constraints_honored: list[str] = Field(default_factory=list)


class ImplementResult(BaseModel):
    """Output from IMPLEMENT phase."""

    success: bool = Field(description="Whether all verification passed")
    files_written: list[str] = Field(default_factory=list, description="Files created/updated")
    phase: str | None = Field(default=None, description="Phase that failed: BUILD, START, HEALTHCHECK")
    error: str | None = Field(default=None, description="Error message if failed")
    logs: str | None = Field(default=None, description="Path to log file")
