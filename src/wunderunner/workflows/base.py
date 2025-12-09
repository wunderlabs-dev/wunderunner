"""Base types for workflows."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Phase(Enum):
    """Workflow phases that can fail and trigger regeneration."""

    ANALYZE = "analyze"
    DOCKERFILE = "dockerfile"
    SERVICES = "services"
    BUILD = "build"
    START = "start"
    HEALTHCHECK = "healthcheck"


@dataclass
class Learning:
    """Captured learning from a failed phase."""

    phase: Phase
    error: Exception


@dataclass
class ContainerizeContext:
    """Context for the containerize workflow."""

    path: Path
    rebuild: bool = False


@dataclass
class Success:
    """Successful workflow completion."""


class Failure(Exception):
    """Workflow failed."""
