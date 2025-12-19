"""ERROR-RESEARCH agent.

Analyzes build/runtime errors and determines fix approach.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import ErrorAnalysis, FixHistory
from wunderunner.settings import Generation, get_model

SYSTEM_PROMPT = """\
You are analyzing a containerization error to determine the fix approach.

<input>
You receive:
1. Error context (phase, error message, log path)
2. Original research.md (project context)
3. Fix history (previous attempts and their outcomes)
</input>

<task>
1. Understand what went wrong
2. Review what fixes have already been tried
3. Determine if there are untried approaches
4. Recommend whether to continue or stop
</task>

<error_analysis>
Common error patterns and fixes:

BUILD phase:
- "Missing script: X" → Add script to package.json or change CMD
- "Module not found" → Add dependency or fix import path
- "COPY failed: file not found" → Fix path in Dockerfile
- "npm ERR!" → Check package.json, lockfile, or node version
- "pip: No matching distribution" → Check Python version or package name

START phase:
- "Port already in use" → Change port mapping
- "Connection refused" → Service not ready, add healthcheck/wait
- "Permission denied" → Add chmod or run as different user
- "ENOENT" → Missing file, check COPY commands

HEALTHCHECK phase:
- "Connection refused" → App not listening, check port/host
- "404" → Endpoint doesn't exist, check route
- "500" → App error, check logs
</error_analysis>

<exhaustion_check>
Track what approaches have been tried:
- List 3-5 standard approaches for this error type
- Mark each as attempted or not based on fix history
- If all standard approaches are exhausted, recommend "stop"
</exhaustion_check>

<output>
error_summary: Brief description of what failed
root_cause: Your diagnosis of why it failed
fix_history_review: Summary of previous attempts
exhaustion_status: List of approaches with attempted status
recommendation: "continue" or "stop"
suggested_approach: What to try next (null if stopping)
</output>
"""


def _build_user_prompt(
    error_context: dict,
    research_content: str,
    fix_history: FixHistory,
) -> str:
    """Build user prompt from error context and history."""
    parts = []

    # Error context
    parts.append("## Error Context\n")
    parts.append(f"- Phase: {error_context.get('phase', 'UNKNOWN')}")
    parts.append(f"- Error: {error_context.get('error', 'Unknown error')}")
    if error_context.get("log_path"):
        parts.append(f"- Log: {error_context['log_path']}")
    parts.append("")

    # Research context
    parts.append("## Project Research\n")
    parts.append(research_content)
    parts.append("")

    # Fix history
    parts.append("## Fix History\n")
    if fix_history.attempts:
        for attempt in fix_history.attempts:
            parts.append(f"### Attempt {attempt.attempt}")
            parts.append(f"- Phase: {attempt.phase}")
            parts.append(f"- Error: {attempt.error.message}")
            parts.append(f"- Diagnosis: {attempt.diagnosis}")
            parts.append(f"- Outcome: {attempt.outcome}")
            parts.append("")
    else:
        parts.append("No previous attempts.\n")

    return "\n".join(parts)


agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=ErrorAnalysis,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)


async def run_error_research(
    project_dir: Path,
    error_context: dict,
    research_content: str,
    fix_history: FixHistory,
) -> ErrorAnalysis:
    """Run ERROR-RESEARCH phase.

    Args:
        project_dir: Project root directory.
        error_context: Dict with phase, error, log_path.
        research_content: Content of research.md.
        fix_history: Previous fix attempts.

    Returns:
        ErrorAnalysis with diagnosis and recommendation.
    """
    from wunderunner.settings import get_fallback_model

    user_prompt = _build_user_prompt(error_context, research_content, fix_history)

    result = await agent.run(
        user_prompt,
        model=get_fallback_model(Generation.DOCKERFILE),
    )
    return result.output
