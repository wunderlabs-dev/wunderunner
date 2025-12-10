"""State for the containerize workflow."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from rich.console import Console

from wunderunner.models.analysis import Analysis


class Phase(StrEnum):
    """Workflow phases where errors can occur."""

    DOCKERFILE = "dockerfile"
    VALIDATION = "validation"
    SERVICES = "services"
    BUILD = "build"
    START = "start"
    HEALTHCHECK = "healthcheck"


@dataclass
class Learning:
    """Captured learning from a failed phase."""

    phase: Phase
    error_type: str
    error_message: str
    context: str | None = None


@dataclass
class ContainerizeState:
    """Shared state for containerize workflow."""

    path: Path
    rebuild: bool = False
    console: Console = field(default_factory=Console)

    # Analysis result (set by Analyze node)
    analysis: Analysis | None = None

    # Secret values collected from user (name -> value)
    secret_values: dict[str, str] = field(default_factory=dict)

    # Accumulated learnings and hints
    learnings: list[Learning] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    # Retry tracking (reset after human hint)
    attempts_since_hint: int = 0

    # Intermediate artifacts (for persistence and refinement)
    dockerfile_content: str | None = None
    compose_content: str | None = None
    container_ids: list[str] = field(default_factory=list)

    # Validation tracking
    last_validation_grade: int | None = None

    # Confidence tracking (from Dockerfile generation)
    last_confidence: int | None = None

    # Conversation history for stateful Dockerfile generation
    dockerfile_messages: list[Any] = field(default_factory=list)
