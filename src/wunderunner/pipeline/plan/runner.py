"""PLAN phase runner.

Reads research.md, loads constraints, generates plan, writes plan.md.
"""

from pathlib import Path

from wunderunner.pipeline.artifacts import (
    read_fix_history,
    read_research,
    write_plan,
)
from wunderunner.pipeline.models import ConstraintStatus, ContainerizationPlan
from wunderunner.pipeline.plan.agent import generate_plan


async def run_plan(project_dir: Path) -> ContainerizationPlan:
    """Execute PLAN phase.

    Reads research.md artifact, loads any active constraints from fixes.json,
    generates containerization plan, and writes plan.md.

    Args:
        project_dir: Project root directory.

    Returns:
        Generated ContainerizationPlan.

    Raises:
        FileNotFoundError: If research.md doesn't exist.
    """
    # Read research artifact
    research_content = await read_research(project_dir)

    # Load constraints from fix history
    constraints: list[str] = []
    fix_history = await read_fix_history(project_dir)
    if fix_history:
        constraints = [
            c.rule for c in fix_history.active_constraints
            if c.status == ConstraintStatus.HARD
        ]

    # Generate plan
    plan = await generate_plan(project_dir, research_content, constraints)

    # Write artifact
    await write_plan(project_dir, plan)

    return plan
