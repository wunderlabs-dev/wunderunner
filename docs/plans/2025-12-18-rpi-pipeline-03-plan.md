## Part 3: Plan Phase

The PLAN phase reads `research.md` and generates exact file contents in `plan.md`.

---

### Task 3.1: Create plan module structure

**Files:**
- Create: `src/wunderunner/pipeline/plan/__init__.py`

**Step 1: Create directory and init file**

```bash
mkdir -p src/wunderunner/pipeline/plan
```

```python
# src/wunderunner/pipeline/plan/__init__.py
"""PLAN phase - generate exact containerization content."""

from wunderunner.pipeline.plan.agent import generate_plan

__all__ = ["generate_plan"]
```

**Step 2: Commit**

```bash
git add src/wunderunner/pipeline/plan/
git commit -m "feat(pipeline): add plan phase module structure"
```

---

### Task 3.2: Add plan generation agent

**Files:**
- Create: `src/wunderunner/pipeline/plan/agent.py`
- Test: `tests/test_pipeline_plan_agent.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_plan_agent.py
"""Tests for PLAN phase agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import ContainerizationPlan, VerificationStep
from wunderunner.pipeline.plan.agent import generate_plan


@pytest.fixture
def research_content() -> str:
    """Sample research.md content."""
    return """# Project Research

## Runtime
- **Language:** python
- **Version:** 3.11
- **Framework:** fastapi
- **Entrypoint:** src/main.py

## Dependencies
- **Package Manager:** uv
- **Start Command:** `uvicorn src.main:app --host 0.0.0.0`

## Configuration

### Environment Variables
| Name | Required | Secret | Service | Default |
|------|----------|--------|---------|---------|
| DATABASE_URL | Yes | Yes | postgres | - |

## Backing Services
- **postgres** (v15) → `DATABASE_URL`
"""


@pytest.mark.asyncio
async def test_generate_plan_returns_containerization_plan(tmp_path: Path, research_content: str):
    """generate_plan returns ContainerizationPlan with exact content."""
    mock_plan = ContainerizationPlan(
        summary="Python 3.11 FastAPI app with PostgreSQL",
        dockerfile="""FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY src/ ./src/
ARG DATABASE_URL
ENV DATABASE_URL=${DATABASE_URL}
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0"]
""",
        compose="""services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
    environment:
      - DATABASE_URL
  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=postgres
""",
        verification=[
            VerificationStep(command="docker compose build", expected="exit 0", phase="BUILD"),
            VerificationStep(command="docker compose up -d", expected="containers start", phase="START"),
        ],
        reasoning="Using uv for fast dependency resolution, slim image for size",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.agent.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await generate_plan(tmp_path, research_content, constraints=[])

    assert isinstance(result, ContainerizationPlan)
    assert "FROM python:3.11" in result.dockerfile
    assert "postgres:15" in result.compose
    assert len(result.verification) == 2


@pytest.mark.asyncio
async def test_generate_plan_honors_constraints(tmp_path: Path, research_content: str):
    """generate_plan includes constraints in output."""
    constraints = ["MUST use python:3.11-slim base image", "MUST include pandas"]

    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\n",
        verification=[],
        reasoning="Honoring constraints",
        constraints_honored=constraints,
    )

    with patch(
        "wunderunner.pipeline.plan.agent.agent.run",
        new_callable=AsyncMock,
        return_value=AsyncMock(output=mock_plan),
    ):
        result = await generate_plan(tmp_path, research_content, constraints=constraints)

    assert result.constraints_honored == constraints
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_plan_agent.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write plan generation agent**

```python
# src/wunderunner/pipeline/plan/agent.py
"""PLAN phase agent.

Generates exact Dockerfile and docker-compose.yaml content from research findings.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import ContainerizationPlan
from wunderunner.settings import get_model, Generation

SYSTEM_PROMPT = """\
You are generating containerization files for a software project.

Your output must contain EXACT, COMPLETE file contents - not instructions or placeholders.
The IMPLEMENT phase will write your output directly to disk without modification.

<input>
You receive:
1. research.md - Project analysis from RESEARCH phase
2. constraints - Rules from previous fixes that MUST be honored

Read the research carefully. Generate files that match the project's actual configuration.
</input>

<output_requirements>
dockerfile: Complete, valid Dockerfile content
- Start with appropriate base image for the runtime
- Install dependencies using the detected package manager
- Handle secrets with ARG/ENV pattern
- Set correct WORKDIR, COPY, EXPOSE, CMD

compose (optional): Complete docker-compose.yaml if services detected
- Include app service with build context
- Add backing services (postgres, redis, etc.) with correct images
- Wire up environment variables
- Set depends_on relationships

verification: List of commands to verify the build works
- BUILD phase: docker compose build or docker build
- START phase: docker compose up -d or docker run
- HEALTHCHECK phase: curl or wget to health endpoint if applicable

reasoning: Brief explanation of your choices
- Why this base image?
- Why this dependency installation approach?
- Any trade-offs made?

constraints_honored: Echo back any constraints you were given
- Include exact constraint text
- Only list constraints you actually honored
</output_requirements>

<dockerfile_patterns>
Python with uv:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY src/ ./src/
# Secrets via ARG/ENV
ARG DATABASE_URL
ENV DATABASE_URL=${DATABASE_URL}
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0"]
```

Python with pip:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0"]
```

Node.js with npm:
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

Node.js with pnpm:
```dockerfile
FROM node:20-slim
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod
COPY . .
EXPOSE 3000
CMD ["pnpm", "start"]
```
</dockerfile_patterns>

<compose_patterns>
With PostgreSQL:
```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/app
  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=app
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

With Redis:
```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - redis
    environment:
      - REDIS_URL=redis://redis:6379
  redis:
    image: redis:7-alpine
```
</compose_patterns>

<constraints_handling>
CRITICAL: If constraints are provided, you MUST honor them.

Example constraints:
- "MUST use python:3.11-slim base image" → Use exactly python:3.11-slim
- "MUST include pandas in pip install" → Add pandas to RUN pip install
- "MUST NOT use multi-stage build" → Use single stage

If a constraint conflicts with best practices, honor the constraint anyway.
The constraint exists because a previous fix attempt proved it necessary.
</constraints_handling>
"""


def _build_user_prompt(research_content: str, constraints: list[str]) -> str:
    """Build user prompt from research and constraints."""
    parts = [
        "Generate containerization files based on this research:\n",
        "## Research\n",
        research_content,
        "\n",
    ]

    if constraints:
        parts.append("## Constraints (MUST honor these)\n")
        for c in constraints:
            parts.append(f"- {c}\n")
    else:
        parts.append("## Constraints\nNone - this is the first attempt.\n")

    return "".join(parts)


agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=ContainerizationPlan,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)


async def generate_plan(
    project_dir: Path,
    research_content: str,
    constraints: list[str],
) -> ContainerizationPlan:
    """Generate containerization plan from research.

    Args:
        project_dir: Project root directory (for context, not used by agent).
        research_content: Content of research.md.
        constraints: Active constraints from fixes.json.

    Returns:
        ContainerizationPlan with exact file contents.
    """
    from wunderunner.settings import get_fallback_model

    user_prompt = _build_user_prompt(research_content, constraints)

    result = await agent.run(
        user_prompt,
        model=get_fallback_model(Generation.DOCKERFILE),
    )
    return result.output
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_plan_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/wunderunner/pipeline/plan/agent.py tests/test_pipeline_plan_agent.py
git commit -m "feat(pipeline): add PLAN phase agent"
```

---

### Task 3.3: Add plan phase runner

**Files:**
- Modify: `src/wunderunner/pipeline/plan/__init__.py`
- Create: `src/wunderunner/pipeline/plan/runner.py`
- Test: `tests/test_pipeline_plan_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline_plan_runner.py
"""Tests for PLAN phase runner."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from wunderunner.pipeline.models import ContainerizationPlan
from wunderunner.pipeline.plan.runner import run_plan


@pytest.fixture
def project_with_research(tmp_path: Path) -> Path:
    """Create project with research.md artifact."""
    wunderunner_dir = tmp_path / ".wunderunner"
    wunderunner_dir.mkdir()
    (wunderunner_dir / "research.md").write_text("""# Project Research

## Runtime
- **Language:** python
- **Version:** 3.11

## Dependencies
- **Package Manager:** uv

## Configuration
No environment variables detected.

## Backing Services
No backing services detected.
""")
    return tmp_path


@pytest.mark.asyncio
async def test_run_plan_reads_research_and_generates(project_with_research: Path):
    """run_plan reads research.md and generates plan."""
    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\n",
        verification=[],
        reasoning="Simple Python app",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.runner.generate_plan",
        new_callable=AsyncMock,
        return_value=mock_plan,
    ):
        result = await run_plan(project_with_research)

    assert isinstance(result, ContainerizationPlan)


@pytest.mark.asyncio
async def test_run_plan_writes_artifact(project_with_research: Path):
    """run_plan writes plan.md artifact."""
    mock_plan = ContainerizationPlan(
        summary="Python app",
        dockerfile="FROM python:3.11-slim\nWORKDIR /app\n",
        verification=[],
        reasoning="Simple",
        constraints_honored=[],
    )

    with patch(
        "wunderunner.pipeline.plan.runner.generate_plan",
        new_callable=AsyncMock,
        return_value=mock_plan,
    ):
        await run_plan(project_with_research)

    plan_path = project_with_research / ".wunderunner" / "plan.md"
    assert plan_path.exists()
    content = plan_path.read_text()
    assert "FROM python:3.11-slim" in content


@pytest.mark.asyncio
async def test_run_plan_raises_if_no_research(tmp_path: Path):
    """run_plan raises if research.md missing."""
    with pytest.raises(FileNotFoundError):
        await run_plan(tmp_path)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_plan_runner.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write plan phase runner**

```python
# src/wunderunner/pipeline/plan/runner.py
"""PLAN phase runner.

Reads research.md, loads constraints, generates plan, writes plan.md.
"""

from pathlib import Path

from wunderunner.pipeline.artifacts import (
    read_research,
    write_plan,
    read_fix_history,
)
from wunderunner.pipeline.models import ContainerizationPlan
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
            if c.status.value == "hard"
        ]

    # Generate plan
    plan = await generate_plan(project_dir, research_content, constraints)

    # Write artifact
    await write_plan(project_dir, plan)

    return plan
```

**Step 4: Update __init__.py**

```python
# src/wunderunner/pipeline/plan/__init__.py
"""PLAN phase - generate exact containerization content."""

from wunderunner.pipeline.plan.runner import run_plan

__all__ = ["run_plan"]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_plan_runner.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/wunderunner/pipeline/plan/ tests/test_pipeline_plan_runner.py
git commit -m "feat(pipeline): add PLAN phase runner"
```

---

**Part 3 Complete.** PLAN phase with agent and runner. Next: Part 4 (Implement Phase).
