"""Diagnostic agent - analyzes errors without modifying project files."""

import logging

from jinja2 import Template
from pydantic import BaseModel
from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.settings import Generation, get_model

logger = logging.getLogger(__name__)

USER_PROMPT = Template("""\
<project_analysis>
{{ analysis | tojson(indent=2) }}
</project_analysis>

<error>
Phase: {{ phase }}
Error: {{ error_type }}
Message: {{ error_message }}
{% if context %}
{{ context }}
{% endif %}
</error>

<dockerfile>
{{ dockerfile }}
</dockerfile>

{% if compose %}
<docker_compose>
{{ compose }}
</docker_compose>
{% endif %}

Analyze the error and determine:
1. What is the root cause?
2. Is this a Dockerfile issue or a project file issue?
3. What specific change would fix it?

Be concise and specific. The diagnosis will be passed to the Dockerfile generation agent.
""")

SYSTEM_PROMPT = """\
<task>
You are a diagnostic agent. When containerization fails (build error, start error, etc.),
you investigate the root cause and provide a diagnosis.

You have read-only tools to:
- read_file: Read any project file
- list_dir: List directory contents
- grep: Search for patterns
- glob: Find files by pattern

Your goal is to DIAGNOSE issues, not fix them. Your diagnosis will be passed to the
Dockerfile generation agent which will decide how to address the issue.
</task>

<diagnosis_approach>
1. Read the error message carefully - it often contains the answer
2. Look at relevant project files to understand the context
3. Determine if the issue is:
   - Dockerfile issue: missing build step, wrong base image, incorrect paths, etc.
   - Project issue: misconfiguration that can't be fixed by Dockerfile changes

4. Provide a specific, actionable diagnosis
</diagnosis_approach>

<common_patterns>
Build failures:
- "Module not found" during build = missing dependency install step
- "Cannot find module X" at runtime = dependency not in production bundle
- "ENOENT: no such file" = wrong WORKDIR or COPY path

Start failures:
- "Could not find production build" = missing build step in Dockerfile
- "command not found" = wrong CMD or missing binary

Health check failures:
- Timeout = slow startup, increase health check start_period
- Connection refused = wrong port or app not binding to 0.0.0.0
- 500 errors = app starting but crashing, check logs for root cause
</common_patterns>

<output>
Return a Diagnosis with:
- root_cause: What specifically caused the error (1-2 sentences)
- is_dockerfile_issue: true if Dockerfile changes can fix it, false if project needs changes
- suggested_fix: Specific change needed (e.g., "Add RUN npm run build before CMD")
- confidence: 0-10 how confident you are in this diagnosis
</output>
"""


class Diagnosis(BaseModel):
    """Result of error diagnosis."""

    root_cause: str
    is_dockerfile_issue: bool
    suggested_fix: str
    confidence: int


agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=Diagnosis,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

# Read-only tools - no write_file or edit_file
register_tools(agent, include_write=False)
