"""Read/write artifact files to .wunderunner directory."""

from pathlib import Path

import aiofiles

from wunderunner.pipeline.models import ContainerizationPlan, FixHistory, ResearchResult
from wunderunner.pipeline.research.synthesis import synthesize_research
from wunderunner.settings import get_settings


def get_artifact_path(project_dir: Path, filename: str) -> Path:
    """Get path to an artifact file in .wunderunner directory.

    Args:
        project_dir: Project root directory.
        filename: Artifact filename (research.md, plan.md, etc.)

    Returns:
        Full path to artifact file.
    """
    settings = get_settings()
    return project_dir / settings.cache_dir / filename


async def write_research(project_dir: Path, result: ResearchResult) -> Path:
    """Write research.md artifact.

    Args:
        project_dir: Project root directory.
        result: ResearchResult from RESEARCH phase.

    Returns:
        Path to written file.
    """
    content = synthesize_research(result)
    path = get_artifact_path(project_dir, "research.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(content)

    return path


async def read_research(project_dir: Path) -> str:
    """Read research.md artifact content.

    Args:
        project_dir: Project root directory.

    Returns:
        Markdown content of research.md.

    Raises:
        FileNotFoundError: If research.md doesn't exist.
    """
    path = get_artifact_path(project_dir, "research.md")
    async with aiofiles.open(path) as f:
        return await f.read()


async def write_plan(project_dir: Path, plan: ContainerizationPlan) -> Path:
    """Write plan.md artifact.

    Args:
        project_dir: Project root directory.
        plan: ContainerizationPlan from PLAN phase.

    Returns:
        Path to written file.
    """
    content = _format_plan(plan)
    path = get_artifact_path(project_dir, "plan.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(content)

    return path


def _format_plan(plan: ContainerizationPlan) -> str:
    """Format ContainerizationPlan as markdown."""
    sections = ["# Containerization Plan\n"]

    sections.append(f"## Summary\n{plan.summary}\n")

    if plan.constraints_honored:
        sections.append("## Constraints Honored\n")
        for c in plan.constraints_honored:
            sections.append(f"- [x] {c}")
        sections.append("")

    sections.append("## Files\n")
    sections.append("### Dockerfile\n```dockerfile")
    sections.append(plan.dockerfile)
    sections.append("```\n")

    if plan.compose:
        sections.append("### docker-compose.yaml\n```yaml")
        sections.append(plan.compose)
        sections.append("```\n")

    if plan.verification:
        sections.append("## Verification\n")
        for i, step in enumerate(plan.verification, 1):
            sections.append(f"{i}. `{step.command}` → {step.expected}")
        sections.append("")

    sections.append(f"## Reasoning\n{plan.reasoning}\n")

    return "\n".join(sections)


async def read_plan(project_dir: Path) -> str:
    """Read plan.md artifact content.

    Args:
        project_dir: Project root directory.

    Returns:
        Markdown content of plan.md.

    Raises:
        FileNotFoundError: If plan.md doesn't exist.
    """
    path = get_artifact_path(project_dir, "plan.md")
    async with aiofiles.open(path) as f:
        return await f.read()


async def write_fix_history(project_dir: Path, history: FixHistory) -> Path:
    """Write fixes.json artifact.

    Args:
        project_dir: Project root directory.
        history: FixHistory with attempts and constraints.

    Returns:
        Path to written file.
    """
    path = get_artifact_path(project_dir, "fixes.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(history.model_dump_json(indent=2))

    return path


async def read_fix_history(project_dir: Path) -> FixHistory | None:
    """Read fixes.json artifact.

    Args:
        project_dir: Project root directory.

    Returns:
        FixHistory if file exists, None otherwise.
    """
    path = get_artifact_path(project_dir, "fixes.json")
    if not path.exists():
        return None

    async with aiofiles.open(path) as f:
        content = await f.read()

    return FixHistory.model_validate_json(content)
