"""Dockerfile generation agent."""

from jinja2 import Template
from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.models.generation import DockerfileResult
from wunderunner.settings import Generation, get_model

# Runtime-specific templates for development containers
# No build steps - dev servers handle compilation on the fly
RUNTIME_TEMPLATES = {
    "node": """\
# Node.js development container
FROM node:{{ version }}-alpine
WORKDIR /app
COPY package.json {% if lockfile %}{{ lockfile }} {% endif %}./
RUN npm install
COPY . .
EXPOSE {{ port }}
CMD {{ start_command }}
""",
    "python": """\
# Python development container
FROM python:{{ version }}-slim
WORKDIR /app
{% if package_manager == "uv" %}
COPY pyproject.toml {% if lockfile %}{{ lockfile }} {% endif %}./
RUN pip install uv && uv sync
{% elif package_manager == "poetry" %}
COPY pyproject.toml {% if lockfile %}{{ lockfile }} {% endif %}./
RUN pip install poetry && poetry install
{% elif package_manager == "pip" %}
COPY requirements.txt ./
RUN pip install -r requirements.txt
{% else %}
COPY pyproject.toml ./
RUN pip install -e .
{% endif %}
COPY . .
EXPOSE {{ port }}
CMD {{ start_command }}
""",
    "go": """\
# Go development container
FROM golang:{{ version }}-alpine
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
EXPOSE {{ port }}
CMD {{ start_command }}
""",
    "rust": """\
# Rust development container
FROM rust:{{ version }}
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
EXPOSE {{ port }}
CMD {{ start_command }}
""",
}

USER_PROMPT = Template("""\
<project>
Runtime: {{ runtime }}
{% if framework %}Framework: {{ framework }}{% endif %}
Package manager: {{ package_manager }}
{% if lockfile %}Lockfile: {{ lockfile }}{% endif %}
Start: {{ start_command }}
Port: {{ port }}
</project>

<pattern>
{{ runtime_template }}
</pattern>

{% if secrets %}
<secrets>
Declare these as ARG + ENV:
{% for s in secrets %}- {{ s.name }}
{% endfor %}
</secrets>
{% endif %}

{% if learnings %}
<errors_to_fix>
{% for l in learnings %}
[{{ l.phase }}] {{ l.error_message }}
{% endfor %}
</errors_to_fix>
{% endif %}

{% if existing_dockerfile %}
<current_dockerfile>
{{ existing_dockerfile }}
</current_dockerfile>

Fix the errors above.
{% else %}
Generate a Dockerfile based on the pattern above.
{% endif %}

{% if hints %}
<hints>
{% for h in hints %}{{ h }}
{% endfor %}
</hints>
{% endif %}\
""")

SYSTEM_PROMPT = """\
<task>
Generate a development Dockerfile based on the pattern and project info provided.
</task>

<context>
The prompt contains ALL info you need: runtime, framework, package manager, lockfile,
build/start commands, port, and a pre-filled pattern template. This was extracted from
a prior analysis of the project.

You have tools available but typically won't need them - the analysis is complete.
If you do use tools, batch multiple calls together (e.g., read 3 files in one response).
Maximum 3 tool calls total.
</context>

<rules>
<rule>Copy lockfile and install deps BEFORE copying source (layer caching)</rule>
<rule>Include dev dependencies - this is a development container</rule>
<rule>If secrets are listed, add ARG + ENV for each before any RUN that needs them</rule>
<rule>Keep it simple - 10-20 lines is ideal</rule>
</rules>

<output>
- dockerfile: Valid Dockerfile starting with FROM
- confidence: 0-10 (10 = certain, 5 = reasonable guess, 0 = very uncertain)
- reasoning: What you did and why (1-2 sentences)
</output>
"""

agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=DockerfileResult,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)


def get_runtime_template(runtime: str, analysis: dict) -> str:
    """Get the appropriate runtime template with variables filled in."""
    template_str = RUNTIME_TEMPLATES.get(runtime, RUNTIME_TEMPLATES.get("node", ""))
    template = Template(template_str)

    # Extract relevant info from analysis
    project = analysis.get("project_structure", {})
    build = analysis.get("build_strategy", {})

    return template.render(
        version=project.get("runtime_version", "20"),
        lockfile=build.get("lockfile"),
        package_manager=build.get("package_manager", "npm"),
        start_command=build.get("start_command", '["npm", "start"]'),
        port=project.get("port", 3000),
        binary_name=project.get("name", "app"),
    )
