"""Service-detector specialist agent.

Identifies: backing services (databases, caches, queues).
Documentarian framing: reports what exists, does NOT suggest alternatives.
"""

from pathlib import Path

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.pipeline.models import ServiceFindings
from wunderunner.settings import Analysis, get_model

SYSTEM_PROMPT = """\
You are analyzing a software project to identify its backing services.

YOUR ONLY JOB IS TO REPORT WHAT EXISTS. Do NOT:
- Suggest different databases
- Recommend managed services
- Critique architecture choices
- Add editorial commentary

Focus on facts only.

<service_detection>
Check these sources:

1. Existing docker-compose.yaml:
   - Look for service images: postgres, mysql, redis, rabbitmq, mongo, etc.
   - Extract version from image tag

2. Dependencies:
   - psycopg2, asyncpg, pg → postgres
   - mysql-connector, pymysql → mysql
   - redis, ioredis → redis
   - pika, aio-pika, amqplib → rabbitmq
   - pymongo, motor → mongodb
   - elasticsearch-py → elasticsearch

3. Environment variables:
   - DATABASE_URL, POSTGRES_* → postgres
   - MYSQL_* → mysql
   - REDIS_URL, REDIS_* → redis
   - RABBITMQ_*, AMQP_URL → rabbitmq
   - MONGO_*, MONGODB_URI → mongodb
</service_detection>

<version_detection>
Extract version from:
- docker-compose image tags: postgres:15 → version "15"
- Package version constraints (less reliable)
- .tool-versions file

If no version specified, leave as null.
</version_detection>

<workflow>
TURN 1 - Check for existing compose and dependencies (batch these):
- read_file("docker-compose.yaml")
- read_file("docker-compose.yml")
- read_file("pyproject.toml")
- read_file("package.json")

TURN 2 - Search for connection code if needed:
- grep("DATABASE_URL|REDIS_URL|MONGO", ".")

Complete in 2 turns maximum.
</workflow>
"""

USER_PROMPT = "Detect all backing services (databases, caches, queues) used by this project."

agent = Agent(
    model=get_model(Analysis.SECRETS),  # Fast model, simple detection
    output_type=ServiceFindings,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)


async def detect_services(project_dir: Path) -> ServiceFindings:
    """Run the service-detector specialist.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ServiceFindings with detected backing services.
    """
    from wunderunner.settings import get_fallback_model

    deps = AgentDeps(project_dir=project_dir)
    result = await agent.run(
        USER_PROMPT,
        deps=deps,
        model=get_fallback_model(Analysis.SECRETS),
    )
    return result.output
