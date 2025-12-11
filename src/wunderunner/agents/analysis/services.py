"""Service detection agent - identifies external services from env vars."""

from jinja2 import Template
from pydantic_ai import Agent

from wunderunner.models.analysis import DetectedService
from wunderunner.settings import Analysis, get_model

USER_PROMPT = Template("""\
<env_vars>
{% for var in env_vars %}
- {{ var.name }}{% if var.secret %} (secret){% endif %}\
{% if var.service %} [{{ var.service }}]{% endif %}

{% endfor %}
</env_vars>

Analyze these environment variables and identify which external services they imply.
Group related variables by service.
""")

SYSTEM_PROMPT = """\
<task>
Analyze environment variables and identify external services they imply.
Group related variables by service and return a list of DetectedService objects.
</task>

<supported_services>
Only detect these services:
- postgres: Database (DATABASE_*, DB_*, POSTGRES_*, PG_*)
- mysql: Database (MYSQL_*, DB_* when MySQL is implied)
- redis: Cache/queue (REDIS_*, CACHE_*)
- mongodb: Document store (MONGO_*, MONGODB_*)
</supported_services>

<grouping_rules>
Use semantic reasoning to group variables:
- DATABASE_HOST, DATABASE_USER, DATABASE_PASS, DATABASE_PORT → postgres (one service)
- DB_CONNECTION_STRING → postgres or mysql (infer from context)
- REDIS_URL alone → redis
- Multiple MONGO_* vars → mongodb (one service)

Do NOT create multiple services for the same database.
Do NOT detect services outside the supported list.
</grouping_rules>

<confidence_scoring>
- 1.0: Explicit service name (POSTGRES_*, REDIS_URL, MONGODB_URI)
- 0.8: Strong pattern match (DATABASE_URL typically postgres)
- 0.6: Reasonable inference (DB_HOST + DB_USER + DB_PASS)
- 0.4: Weak inference (ambiguous patterns)
</confidence_scoring>

<output>
Return list of DetectedService:
- type: Service type ("postgres", "mysql", "redis", "mongodb")
- env_vars: List of variable names that belong to this service
- confidence: 0-1 confidence score
</output>
"""

agent = Agent(
    model=get_model(Analysis.ENV_VARS),  # Reuse env vars model config
    output_type=list[DetectedService],
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)
