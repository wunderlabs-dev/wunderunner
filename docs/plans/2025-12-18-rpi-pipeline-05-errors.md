## Part 5: Error Handling Flow

When IMPLEMENT fails, we run ERROR-RESEARCH → FIX-PLAN → IMPLEMENT cycle with constraint tracking.

---

### Task 5.1: Create errors module structure

**Files:**
- Create: `src/wunderunner/pipeline/errors/__init__.py`

**Step 1: Create directory and init file**

```bash
mkdir -p src/wunderunner/pipeline/errors
```

```python
# src/wunderunner/pipeline/errors/__init__.py
"""Error handling - ERROR-RESEARCH and FIX-PLAN phases."""

from wunderunner.pipeline.errors.research import run_error_research
from wunderunner.pipeline.errors.fix_plan import run_fix_plan
from wunderunner.pipeline.errors.constraints import (
    update_constraints,
    increment_success_counts,
)

__all__ = [
    "run_error_research",
    "run_fix_plan",
    "update_constraints",
    "increment_success_counts",
]
```

**Step 2: Commit**

```bash
git add src/wunderunner/pipeline/errors/
git commit -m "feat(pipeline): add errors module structure"
```

---

### Task 5.2: Add constraint management

**Files:**
- Create: `src/wunderunner/pipeline/errors/constraints.py`
- Test: `tests/test_pipeline_constraints.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_constraints.py
"""Tests for constraint management."""

import pytest
from wunderunner.pipeline.models import (
    FixHistory,
    FixAttempt,
    FixError,
    Constraint,
    ConstraintStatus,
)
from wunderunner.pipeline.errors.constraints import (
    update_constraints,
    increment_success_counts,
    derive_constraint,
)


def test_derive_constraint_creates_hard_constraint():
    """derive_constraint creates a hard constraint from fix attempt."""
    attempt = FixAttempt(
        attempt=1,
        phase="BUILD",
        error=FixError(type="missing_dependency", message="No module pandas"),
        diagnosis="pandas not installed",
        outcome="success",
    )

    constraint = derive_constraint(attempt, "MUST include pandas in pip install")

    assert constraint.status == ConstraintStatus.HARD
    assert constraint.rule == "MUST include pandas in pip install"
    assert constraint.from_attempt == 1
    assert constraint.success_count == 0


def test_increment_success_counts_increments():
    """increment_success_counts adds 1 to all constraint success_count."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1, success_count=0),
            Constraint(id="c2", rule="rule2", reason="r2", from_attempt=2, success_count=2),
        ],
    )

    updated = increment_success_counts(history)

    assert updated.active_constraints[0].success_count == 1
    assert updated.active_constraints[1].success_count == 3


def test_increment_success_counts_makes_soft_at_threshold():
    """Constraints become soft after 3 successful builds."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1, success_count=2),
        ],
    )

    updated = increment_success_counts(history)

    assert updated.active_constraints[0].success_count == 3
    assert updated.active_constraints[0].status == ConstraintStatus.SOFT


def test_update_constraints_adds_new():
    """update_constraints adds new constraint to history."""
    history = FixHistory(project="test", active_constraints=[])
    new_constraint = Constraint(id="c1", rule="rule1", reason="r1", from_attempt=1)

    updated = update_constraints(history, new_constraint)

    assert len(updated.active_constraints) == 1
    assert updated.active_constraints[0].rule == "rule1"


def test_update_constraints_resets_violated():
    """update_constraints resets violated constraint to hard."""
    history = FixHistory(
        project="test",
        active_constraints=[
            Constraint(
                id="c1", rule="rule1", reason="r1", from_attempt=1,
                success_count=5, status=ConstraintStatus.SOFT,
            ),
        ],
    )

    # Same rule, new attempt = was violated
    new_constraint = Constraint(id="c1-v2", rule="rule1", reason="violated", from_attempt=3)

    updated = update_constraints(history, new_constraint, violated=True)

    assert len(updated.active_constraints) == 1
    assert updated.active_constraints[0].status == ConstraintStatus.HARD
    assert updated.active_constraints[0].success_count == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_constraints.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write constraint management**

```python
# src/wunderunner/pipeline/errors/constraints.py
"""Constraint management for fix history."""

from wunderunner.pipeline.models import (
    FixHistory,
    FixAttempt,
    Constraint,
    ConstraintStatus,
)

SOFT_THRESHOLD = 3  # Constraints become soft after this many successes


def derive_constraint(attempt: FixAttempt, rule: str) -> Constraint:
    """Create a constraint from a successful fix attempt.

    Args:
        attempt: The fix attempt that succeeded.
        rule: The constraint rule text.

    Returns:
        New hard constraint.
    """
    return Constraint(
        id=f"c{attempt.attempt}",
        rule=rule,
        reason=attempt.diagnosis,
        from_attempt=attempt.attempt,
        success_count=0,
        status=ConstraintStatus.HARD,
    )


def increment_success_counts(history: FixHistory) -> FixHistory:
    """Increment success_count for all constraints after successful build.

    Constraints become soft after reaching SOFT_THRESHOLD successes.

    Args:
        history: Current fix history.

    Returns:
        Updated fix history with incremented counts.
    """
    updated_constraints = []

    for constraint in history.active_constraints:
        new_count = constraint.success_count + 1
        new_status = constraint.status

        if new_count >= SOFT_THRESHOLD and constraint.status == ConstraintStatus.HARD:
            new_status = ConstraintStatus.SOFT

        updated_constraints.append(
            Constraint(
                id=constraint.id,
                rule=constraint.rule,
                reason=constraint.reason,
                from_attempt=constraint.from_attempt,
                added_at=constraint.added_at,
                success_count=new_count,
                status=new_status,
            )
        )

    return FixHistory(
        project=history.project,
        created_at=history.created_at,
        attempts=history.attempts,
        active_constraints=updated_constraints,
    )


def update_constraints(
    history: FixHistory,
    new_constraint: Constraint,
    violated: bool = False,
) -> FixHistory:
    """Add or update a constraint in history.

    If violated=True, resets an existing constraint with same rule to hard.

    Args:
        history: Current fix history.
        new_constraint: Constraint to add or update.
        violated: Whether this is a violated constraint being reset.

    Returns:
        Updated fix history.
    """
    updated_constraints = []

    # Check if constraint with same rule exists
    found_existing = False
    for existing in history.active_constraints:
        if existing.rule == new_constraint.rule:
            found_existing = True
            if violated:
                # Reset to hard with 0 success count
                updated_constraints.append(
                    Constraint(
                        id=new_constraint.id,
                        rule=new_constraint.rule,
                        reason=new_constraint.reason,
                        from_attempt=new_constraint.from_attempt,
                        success_count=0,
                        status=ConstraintStatus.HARD,
                    )
                )
            else:
                # Keep existing
                updated_constraints.append(existing)
        else:
            updated_constraints.append(existing)

    # Add new if not found
    if not found_existing:
        updated_constraints.append(new_constraint)

    return FixHistory(
        project=history.project,
        created_at=history.created_at,
        attempts=history.attempts,
        active_constraints=updated_constraints,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_constraints.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/errors/constraints.py tests/test_pipeline_constraints.py
git commit -m "feat(pipeline): add constraint management"
```

---

### Task 5.3: Add ERROR-RESEARCH agent

**Files:**
- Create: `src/wunderunner/pipeline/errors/research.py`
- Test: `tests/test_pipeline_error_research.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_error_research.py
"""Tests for ERROR-RESEARCH agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import (
    ErrorAnalysis,
    ExhaustionItem,
    FixHistory,
    FixAttempt,
    FixError,
)
from wunderunner.pipeline.errors.research import run_error_research


@pytest.fixture
def error_context() -> dict:
    """Sample error context."""
    return {
        "phase": "BUILD",
        "error": "npm ERR! Missing script: build",
        "log_path": "/tmp/logs/attempt-1.log",
    }


@pytest.fixture
def fix_history() -> FixHistory:
    """Sample fix history with one attempt."""
    return FixHistory(
        project="test",
        attempts=[
            FixAttempt(
                attempt=1,
                phase="BUILD",
                error=FixError(type="syntax", message="Dockerfile syntax error"),
                diagnosis="Missing FROM instruction",
                outcome="success",
            )
        ],
        active_constraints=[],
    )


@pytest.mark.asyncio
async def test_run_error_research_returns_analysis(
    tmp_path: Path, error_context: dict, fix_history: FixHistory
):
    """run_error_research returns ErrorAnalysis."""
    mock_analysis = ErrorAnalysis(
        error_summary="BUILD failed: missing build script",
        root_cause="package.json has no build script",
        fix_history_review="1 previous attempt for syntax error",
        exhaustion_status=[
            ExhaustionItem(approach="Add build script", attempted=False),
            ExhaustionItem(approach="Use different start command", attempted=False),
        ],
        recommendation="continue",
        suggested_approach="Add build script to package.json",
    )

    with patch(
        "wunderunner.pipeline.errors.research.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_analysis),
    ):
        result = await run_error_research(
            project_dir=tmp_path,
            error_context=error_context,
            research_content="# Project Research\n...",
            fix_history=fix_history,
        )

    assert isinstance(result, ErrorAnalysis)
    assert result.recommendation == "continue"
    assert len(result.exhaustion_status) == 2


@pytest.mark.asyncio
async def test_run_error_research_detects_exhaustion(
    tmp_path: Path, error_context: dict
):
    """run_error_research can recommend stopping."""
    history = FixHistory(
        project="test",
        attempts=[
            FixAttempt(attempt=1, phase="BUILD", error=FixError(type="x", message="x"), diagnosis="d", outcome="failure"),
            FixAttempt(attempt=2, phase="BUILD", error=FixError(type="x", message="x"), diagnosis="d", outcome="failure"),
            FixAttempt(attempt=3, phase="BUILD", error=FixError(type="x", message="x"), diagnosis="d", outcome="failure"),
        ],
        active_constraints=[],
    )

    mock_analysis = ErrorAnalysis(
        error_summary="Persistent failure",
        root_cause="Unknown",
        fix_history_review="3 failed attempts",
        exhaustion_status=[
            ExhaustionItem(approach="Approach 1", attempted=True),
            ExhaustionItem(approach="Approach 2", attempted=True),
        ],
        recommendation="stop",
        suggested_approach=None,
    )

    with patch(
        "wunderunner.pipeline.errors.research.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_analysis),
    ):
        result = await run_error_research(
            project_dir=tmp_path,
            error_context=error_context,
            research_content="...",
            fix_history=history,
        )

    assert result.recommendation == "stop"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_error_research.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write ERROR-RESEARCH agent**

```python
# src/wunderunner/pipeline/errors/research.py
"""ERROR-RESEARCH agent.

Analyzes build/runtime errors and determines fix approach.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import ErrorAnalysis, FixHistory
from wunderunner.settings import get_model, Generation

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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_error_research.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/errors/research.py tests/test_pipeline_error_research.py
git commit -m "feat(pipeline): add ERROR-RESEARCH agent"
```

---

### Task 5.4: Add FIX-PLAN agent

**Files:**
- Create: `src/wunderunner/pipeline/errors/fix_plan.py`
- Test: `tests/test_pipeline_fix_plan.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_fix_plan.py
"""Tests for FIX-PLAN agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import FixPlan, ErrorAnalysis, ExhaustionItem
from wunderunner.pipeline.errors.fix_plan import run_fix_plan


@pytest.fixture
def error_analysis() -> ErrorAnalysis:
    """Sample error analysis."""
    return ErrorAnalysis(
        error_summary="Missing build script",
        root_cause="package.json has no build script",
        fix_history_review="No previous attempts",
        exhaustion_status=[],
        recommendation="continue",
        suggested_approach="Change CMD to use npm run dev",
    )


@pytest.fixture
def current_plan() -> str:
    """Current plan.md content."""
    return """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "build"]
```
"""


@pytest.mark.asyncio
async def test_run_fix_plan_returns_plan(
    tmp_path: Path, error_analysis: ErrorAnalysis, current_plan: str
):
    """run_fix_plan returns FixPlan with updated Dockerfile."""
    mock_plan = FixPlan(
        summary="Change build command to dev",
        dockerfile="""FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev"]
""",
        changes_description="Changed CMD from 'npm run build' to 'npm run dev'",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.errors.fix_plan.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await run_fix_plan(
            project_dir=tmp_path,
            error_analysis=error_analysis,
            current_plan=current_plan,
            constraints=["MUST use node:20-slim"],
        )

    assert isinstance(result, FixPlan)
    assert "npm run dev" in result.dockerfile
    assert result.changes_description != ""


@pytest.mark.asyncio
async def test_run_fix_plan_honors_constraints(
    tmp_path: Path, error_analysis: ErrorAnalysis, current_plan: str
):
    """run_fix_plan includes honored constraints."""
    constraints = ["MUST use node:20-slim", "MUST NOT use multi-stage"]

    mock_plan = FixPlan(
        summary="Fix",
        dockerfile="FROM node:20-slim\n",
        changes_description="Fixed",
        constraints_honored=constraints,
    )

    with patch(
        "wunderunner.pipeline.errors.fix_plan.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await run_fix_plan(
            project_dir=tmp_path,
            error_analysis=error_analysis,
            current_plan=current_plan,
            constraints=constraints,
        )

    assert result.constraints_honored == constraints
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_fix_plan.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write FIX-PLAN agent**

```python
# src/wunderunner/pipeline/errors/fix_plan.py
"""FIX-PLAN agent.

Generates surgical fix based on error analysis.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import FixPlan, ErrorAnalysis
from wunderunner.settings import get_model, Generation

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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_fix_plan.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/errors/fix_plan.py tests/test_pipeline_fix_plan.py
git commit -m "feat(pipeline): add FIX-PLAN agent"
```

---

### Task 5.5: Add error-analysis artifact writer

**Files:**
- Modify: `src/wunderunner/pipeline/artifacts.py`
- Modify: `tests/test_pipeline_artifacts.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_artifacts.py (append)

from wunderunner.pipeline.models import ErrorAnalysis, ExhaustionItem, FixPlan
from wunderunner.pipeline.artifacts import write_error_analysis, write_fix_plan


@pytest.mark.asyncio
async def test_write_error_analysis(tmp_path: Path):
    """write_error_analysis creates error-analysis.md."""
    analysis = ErrorAnalysis(
        error_summary="Build failed",
        root_cause="Missing dependency",
        fix_history_review="1 attempt",
        exhaustion_status=[ExhaustionItem(approach="Add dep", attempted=False)],
        recommendation="continue",
        suggested_approach="Add pandas to requirements",
    )

    path = await write_error_analysis(tmp_path, analysis, attempt=2)

    assert path.exists()
    content = path.read_text()
    assert "Build failed" in content
    assert "Missing dependency" in content


@pytest.mark.asyncio
async def test_write_fix_plan(tmp_path: Path):
    """write_fix_plan creates fix-plan.md."""
    plan = FixPlan(
        summary="Add missing dependency",
        dockerfile="FROM python:3.11\nRUN pip install pandas\n",
        changes_description="Added pandas",
        constraints_honored=["MUST use python:3.11"],
    )

    path = await write_fix_plan(tmp_path, plan)

    assert path.exists()
    content = path.read_text()
    assert "Add missing dependency" in content
    assert "pip install pandas" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_artifacts.py::test_write_error_analysis -v`
Expected: FAIL with "cannot import name 'write_error_analysis'"

**Step 3: Add error artifact writers**

```python
# src/wunderunner/pipeline/artifacts.py (append)


async def write_error_analysis(
    project_dir: Path, analysis: ErrorAnalysis, attempt: int
) -> Path:
    """Write error-analysis.md artifact.

    Args:
        project_dir: Project root directory.
        analysis: ErrorAnalysis from ERROR-RESEARCH phase.
        attempt: Current attempt number.

    Returns:
        Path to written file.
    """
    content = _format_error_analysis(analysis, attempt)
    path = get_artifact_path(project_dir, "error-analysis.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(content)

    return path


def _format_error_analysis(analysis: ErrorAnalysis, attempt: int) -> str:
    """Format ErrorAnalysis as markdown."""
    sections = [f"# Error Analysis (Attempt {attempt})\n"]

    sections.append(f"## Error Summary\n{analysis.error_summary}\n")
    sections.append(f"## Root Cause\n{analysis.root_cause}\n")
    sections.append(f"## Fix History Review\n{analysis.fix_history_review}\n")

    sections.append("## Exhaustion Status\n")
    for item in analysis.exhaustion_status:
        status = "[x]" if item.attempted else "[ ]"
        sections.append(f"- {status} {item.approach}")
    sections.append("")

    sections.append(f"**Recommendation:** {analysis.recommendation}\n")

    if analysis.suggested_approach:
        sections.append(f"## Suggested Approach\n{analysis.suggested_approach}\n")

    return "\n".join(sections)


async def write_fix_plan(project_dir: Path, plan: FixPlan) -> Path:
    """Write fix-plan.md artifact.

    Args:
        project_dir: Project root directory.
        plan: FixPlan from FIX-PLAN phase.

    Returns:
        Path to written file.
    """
    content = _format_fix_plan(plan)
    path = get_artifact_path(project_dir, "fix-plan.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(path, "w") as f:
        await f.write(content)

    return path


def _format_fix_plan(plan: FixPlan) -> str:
    """Format FixPlan as markdown."""
    sections = ["# Fix Plan\n"]

    sections.append(f"## Summary\n{plan.summary}\n")
    sections.append(f"## Changes\n{plan.changes_description}\n")

    if plan.constraints_honored:
        sections.append("## Constraints Honored\n")
        for c in plan.constraints_honored:
            sections.append(f"- [x] {c}")
        sections.append("")

    sections.append("## Updated Dockerfile\n```dockerfile")
    sections.append(plan.dockerfile)
    sections.append("```\n")

    if plan.compose:
        sections.append("## Updated docker-compose.yaml\n```yaml")
        sections.append(plan.compose)
        sections.append("```\n")

    return "\n".join(sections)
```

**Step 4: Add imports at top of artifacts.py**

```python
# At top of src/wunderunner/pipeline/artifacts.py, update imports:
from wunderunner.pipeline.models import (
    ResearchResult,
    ContainerizationPlan,
    FixHistory,
    ErrorAnalysis,
    FixPlan,
)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_artifacts.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/pipeline/artifacts.py tests/test_pipeline_artifacts.py
git commit -m "feat(pipeline): add error analysis artifact writers"
```

---

**Part 5 Complete.** Error handling with constraint management, ERROR-RESEARCH, and FIX-PLAN. Next: Part 6 (CLI Integration).
