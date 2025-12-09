"""Docker Compose generation agent."""

from jinja2 import Template
from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.settings import Generation, get_model

USER_PROMPT = Template("""\
<project_analysis>
{{ analysis | tojson(indent=2) }}
</project_analysis>

<dockerfile>
{{ dockerfile }}
</dockerfile>

{% if learnings %}
<previous_learnings>
{% for learning in learnings %}
- [{{ learning.phase }}] {{ learning.error_type }}: {{ learning.error_message }}
{%- if learning.context %}
  Context: {{ learning.context }}
{%- endif %}
{% endfor %}
</previous_learnings>
{% endif %}

{% if existing_compose %}
<existing_compose>
{{ existing_compose }}
</existing_compose>
Refine the above docker-compose.yaml to fix the issues.
{% else %}
Generate a new docker-compose.yaml for this project.
{% endif %}

{% if hints %}
<user_hints>
{% for hint in hints %}
- {{ hint }}
{% endfor %}
</user_hints>
{% endif %}\
""")

SYSTEM_PROMPT = """\
<task>
Generate or refine a docker-compose.yaml file for running the project. You will receive:
- Project analysis (runtime, framework, services needed)
- The Dockerfile being used
- Previous learnings from failed starts (if any)
- User hints (if any)
- Existing docker-compose.yaml to refine (if any)

Your output must be valid YAML for docker-compose v3.8+ format.
</task>

<core_principles>
- SIMPLE: Minimal services needed. Don't add unnecessary databases or caches.
- CORRECT: The compose file must work with the provided Dockerfile.
- ITERATIVE: When refining, preserve what works and fix what failed.
- EXPLICIT: Be clear about ports, volumes, and environment variables.
</core_principles>

<compose_structure>
A good docker-compose.yaml follows this pattern:

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: .wunderunner/Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
    volumes:
      - .:/app
      - /app/node_modules
    depends_on:
      - db

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: password
      POSTGRES_DB: app
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```
</compose_structure>

<service_detection>
Based on the analysis, add supporting services:

**Databases:**
- PostgreSQL: If env vars contain DATABASE_URL, POSTGRES_*, or pg/psycopg in deps
- MySQL: If env vars contain MYSQL_*, or mysql in deps
- MongoDB: If env vars contain MONGO_*, MONGODB_*, or mongoose in deps
- Redis: If env vars contain REDIS_*, or redis/ioredis in deps

**Message Queues:**
- RabbitMQ: If env vars contain RABBITMQ_*, AMQP_*, or amqplib in deps
- Kafka: If kafka* in deps

**Search:**
- Elasticsearch: If elastic* in deps or ELASTICSEARCH_* env vars
</service_detection>

<port_mapping>
Common default ports:
- Node.js: 3000
- Python (FastAPI/Flask): 8000
- Django: 8000
- Go: 8080
- Rust: 8080
- Next.js: 3000
- Vite: 5173
- Ruby/Rails: 3000

Use the port from:
1. PORT env var if specified
2. EXPOSE in Dockerfile
3. Common defaults above
</port_mapping>

<environment_variables>
Pass environment variables to the container:

For secrets (secret=True in analysis):
```yaml
environment:
  - DATABASE_URL  # Value passed at runtime via .env
```

For non-secrets with defaults:
```yaml
environment:
  - NODE_ENV=production
  - PORT=3000
```
</environment_variables>

<volumes>
Development volumes for live reload:
```yaml
volumes:
  - .:/app           # Mount project for live changes
  - /app/node_modules  # Exclude node_modules (use container's)
```

Production volumes (persistent data only):
```yaml
volumes:
  - postgres_data:/var/lib/postgresql/data
```
</volumes>

<healthchecks>
Add healthchecks for reliability:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

For databases:
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U $POSTGRES_USER"]
  interval: 5s
  timeout: 5s
  retries: 5
```
</healthchecks>

<depends_on>
Use depends_on with conditions for proper startup order:

```yaml
depends_on:
  db:
    condition: service_healthy
```
</depends_on>

<error_recovery>
When you receive learnings from failed starts:

1. READ THE ERROR CAREFULLY
2. Common issues:
   - Port already in use → Change the host port mapping
   - Container exit immediately → Check CMD in Dockerfile
   - Database connection refused → Add depends_on with health check
   - Permission denied → Check volume mount permissions
   - Environment variable missing → Add to environment section
</error_recovery>

<output_format>
Return ONLY the docker-compose.yaml content as a string. No markdown, no explanation.
Just the raw YAML content starting with "version:".
</output_format>
"""

agent = Agent(
    model=get_model(Generation.COMPOSE),
    output_type=str,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)
