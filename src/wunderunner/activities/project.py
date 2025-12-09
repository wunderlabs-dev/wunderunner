"""Project analysis activity."""

from dataclasses import dataclass
from pathlib import Path

from wunderunner.exceptions import AnalyzeError


@dataclass
class Analysis:
    """Result of project analysis."""

    # TODO: Add actual analysis fields
    framework: str | None = None
    runtime: str | None = None
    dependencies: list[str] | None = None


async def analyze(path: Path, rebuild: bool = False) -> Analysis:
    """Analyze project structure and dependencies.

    Raises:
        AnalyzeError: If analysis fails.
    """
    # TODO: Implement with pydantic-ai agent
    raise NotImplementedError
