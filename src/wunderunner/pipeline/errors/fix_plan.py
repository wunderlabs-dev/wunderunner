"""FIX-PLAN agent.

Generates surgical fix based on error analysis.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import ErrorAnalysis, FixPlan
from wunderunner.settings import Generation, get_model

SYSTEM_PROMPT = """\
You are generating a fix for a containerization error.

<input>
You receive:
1. Error analysis (diagnosis and suggested approach)
2. Current plan.md (what was tried)
3. Constraints (rules that MUST be honored)
</input>

<task>
Generate a surgical fix that:
1. Addresses the root cause from error analysis
2. Follows the suggested approach
3. Honors all constraints
4. Changes as little as possible
</task>

<output>
summary: Brief description of what this fix does
dockerfile: Complete updated Dockerfile content
compose: Updated docker-compose.yaml if needed (null if unchanged)
changes_description: What changed and why
constraints_honored: Echo back constraints that were honored
</output>

<critical_rules>
- Output COMPLETE file contents, not diffs
- Honor ALL constraints - they exist for a reason
- Make minimal changes - don't refactor unrelated code
- If the suggested approach conflicts with a constraint, find an alternative
</critical_rules>
"""


def _build_user_prompt(
    error_analysis: ErrorAnalysis,
    current_plan: str,
    constraints: list[str],
) -> str:
    """Build user prompt from error analysis and current plan."""
    parts = []

    # Error analysis
    parts.append("## Error Analysis\n")
    parts.append(f"**Summary:** {error_analysis.error_summary}")
    parts.append(f"**Root Cause:** {error_analysis.root_cause}")
    parts.append(f"**Suggested Approach:** {error_analysis.suggested_approach or 'None'}")
    parts.append("")

    # Current plan
    parts.append("## Current Plan\n")
    parts.append(current_plan)
    parts.append("")

    # Constraints
    parts.append("## Constraints (MUST honor)\n")
    if constraints:
        for c in constraints:
            parts.append(f"- {c}")
    else:
        parts.append("None")

    return "\n".join(parts)


agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=FixPlan,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)


async def run_fix_plan(
    project_dir: Path,
    error_analysis: ErrorAnalysis,
    current_plan: str,
    constraints: list[str],
) -> FixPlan:
    """Run FIX-PLAN phase.

    Args:
        project_dir: Project root directory.
        error_analysis: Analysis from ERROR-RESEARCH phase.
        current_plan: Content of current plan.md.
        constraints: Active constraints to honor.

    Returns:
        FixPlan with updated file contents.
    """
    from wunderunner.settings import get_fallback_model

    user_prompt = _build_user_prompt(error_analysis, current_plan, constraints)

    result = await agent.run(
        user_prompt,
        model=get_fallback_model(Generation.DOCKERFILE),
    )
    return result.output
