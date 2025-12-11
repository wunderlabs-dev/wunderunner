"""Docker Compose generation agent."""

from jinja2 import Template
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from wunderunner.settings import Generation, get_model


class ComposeResult(BaseModel):
    """Result of docker-compose.yaml generation."""

    compose_yaml: str = Field(
        description="The complete docker-compose.yaml content. Must be valid YAML. "
        "Start with 'services:' - no version needed for modern Docker Compose."
    )


USER_PROMPT = Template("""\
<project>
Runtime: {{ analysis.project_structure.runtime }}
Framework: {{ analysis.project_structure.framework or 'none' }}
Port: {{ analysis.project_structure.port or 3000 }}
</project>

<dockerfile>
{{ dockerfile }}
</dockerfile>

{% if services %}
<services_to_create>
Create these service containers alongside the app:
{% for svc in services %}
- {{ svc.type }}: wire env vars {{ svc.env_vars | join(', ') }}
{% endfor %}
</services_to_create>
{% endif %}

{% if learnings %}
<previous_errors>
{% for learning in learnings %}
- [{{ learning.phase }}] {{ learning.error_message }}
{% endfor %}
</previous_errors>
{% endif %}

{% if existing_compose %}
<current_compose>
{{ existing_compose }}
</current_compose>
Fix the errors and return improved docker-compose.yaml.
{% else %}
Generate a docker-compose.yaml for this project.
{% endif %}
""")

SYSTEM_PROMPT = """\
Generate a docker-compose.yaml file.

RULES:
1. Start with "services:" (no version declaration needed)
2. Match the port from the Dockerfile's EXPOSE
3. Use "build: ." to build from the Dockerfile
4. NEVER add volumes - no volumes section, no volume mounts
5. Do NOT add health checks unless the app has a /health endpoint

SERVICE CONTAINERS:
If <services_to_create> is provided, add those containers using these templates:

postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
    POSTGRES_DB: app
  ports:
    - "5432:5432"

redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"

mysql:
  image: mysql:8
  environment:
    MYSQL_ROOT_PASSWORD: root
    MYSQL_DATABASE: app
  ports:
    - "3306:3306"

mongodb:
  image: mongo:7
  ports:
    - "27017:27017"

WIRING ENV VARS:
For each service, add environment variables to the app container:
- *_HOST vars → service name (e.g., DATABASE_HOST: postgres)
- *_USER vars → "postgres" for postgres, "app" for mysql
- *_PASS/*_PASSWORD vars → "postgres" for postgres, "app" for mysql
- *_PORT vars → service port (5432, 6379, 3306, 27017)
- *_URL vars → full connection URL (e.g., postgres://postgres:postgres@postgres:5432/app)

APP ORDERING:
When services exist, add depends_on to the app:
  app:
    depends_on:
      - postgres
      - redis

NEVER add volumes. Volumes cause mount conflicts with Dockerfile operations.
"""

agent = Agent(
    model=get_model(Generation.COMPOSE),
    output_type=ComposeResult,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

# No tools needed - this agent has all info from the prompt (Dockerfile, analysis, errors)
