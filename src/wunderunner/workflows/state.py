"""State for the containerize workflow."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Phase(StrEnum):
    """Workflow phases where errors can occur."""

    DOCKERFILE = "dockerfile"
    VALIDATION = "validation"
    SERVICES = "services"
    BUILD = "build"
    START = "start"
    HEALTHCHECK = "healthcheck"


class Severity(StrEnum):
    """Severity levels for progress messages."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


# Callback signatures
ProgressCallback = Callable[[Severity, str], None]
SecretPromptCallback = Callable[[str, str | None], str]  # (name, service) -> value
HintPromptCallback = Callable[[list["Learning"]], str | None]  # (learnings) -> hint or None to quit


def _noop_progress(severity: Severity, message: str) -> None:
    """Default no-op progress callback."""


def _noop_secret_prompt(name: str, service: str | None) -> str:
    """Default secret prompt - raises to indicate no handler."""
    raise NotImplementedError("Secret prompt callback not provided")


def _noop_hint_prompt(learnings: list["Learning"]) -> str | None:
    """Default hint prompt - returns None to quit."""
    return None


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

    # Callbacks for UI interaction (CLI provides Rich-based implementations)
    on_progress: ProgressCallback = _noop_progress
    on_secret_prompt: SecretPromptCallback = _noop_secret_prompt
    on_hint_prompt: HintPromptCallback = _noop_hint_prompt

    # Analysis result (set by Analyze node)
    # Import here to avoid circular import
    analysis: Any = None

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
