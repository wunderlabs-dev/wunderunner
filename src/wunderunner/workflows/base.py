"""Base types for workflows."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal


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

    status: Literal["success"] = "success"


@dataclass
class Failure:
    """Failed workflow completion."""

    status: Literal["failure"] = "failure"
    learnings: list[Learning] = field(default_factory=list)


ContainerizeResult = Success | Failure
