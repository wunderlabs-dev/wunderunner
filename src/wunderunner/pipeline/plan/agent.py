"""PLAN phase agent.

Generates exact Dockerfile and docker-compose.yaml content from research findings.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.pipeline.models import ContainerizationPlan
from wunderunner.settings import Generation, get_model

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
