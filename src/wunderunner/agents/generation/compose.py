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
Generate a minimal docker-compose.yaml for this project.
{% endif %}
""")

SYSTEM_PROMPT = """\
Generate a docker-compose.yaml file. Keep it minimal.

RULES:
1. Start with "services:" (no version declaration needed)
2. Match the port from the Dockerfile's EXPOSE
3. Use "build: ." to build from the Dockerfile
4. NEVER add volumes - no volumes section, no volume mounts
5. Do NOT add databases unless explicitly needed
6. Do NOT add health checks unless the app has a /health endpoint

MINIMAL TEMPLATE:
services:
  app:
    build: .
    ports:
      - "3000:3000"

That's it. Only add more if the project actually needs it.
NEVER add volumes. Volumes cause mount conflicts with Dockerfile operations.
"""

agent = Agent(
    model=get_model(Generation.COMPOSE),
    output_type=ComposeResult,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

# No tools needed - this agent has all info from the prompt (Dockerfile, analysis, errors)
