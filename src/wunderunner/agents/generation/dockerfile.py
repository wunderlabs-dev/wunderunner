"""Dockerfile generation agent."""

from jinja2 import Template
from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.models.generation import DockerfileResult
from wunderunner.settings import Generation, get_model

# Runtime-specific templates - only the relevant one is included in the prompt
RUNTIME_TEMPLATES = {
    "node": """\
# Node.js Dockerfile pattern:
FROM node:{{ version }}-alpine
WORKDIR /app
{% if lockfile == "package-lock.json" %}
COPY package.json package-lock.json ./
RUN npm ci --only=production
{% elif lockfile == "yarn.lock" %}
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile --production
{% elif lockfile == "pnpm-lock.yaml" %}
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile --prod
{% elif lockfile == "bun.lockb" %}
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile --production
{% else %}
COPY package.json ./
RUN npm install --only=production
{% endif %}
COPY . .
{% if build_command %}
RUN {{ build_command }}
{% endif %}
ENV NODE_ENV=production
EXPOSE {{ port }}
CMD {{ start_command }}
""",
    "python": """\
# Python Dockerfile pattern:
FROM python:{{ version }}-slim
WORKDIR /app
{% if package_manager == "uv" %}
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
{% elif package_manager == "poetry" %}
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev
{% elif package_manager == "pip" %}
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
{% else %}
COPY pyproject.toml ./
RUN pip install .
{% endif %}
COPY . .
EXPOSE {{ port }}
CMD {{ start_command }}
""",
    "go": """\
# Go Dockerfile pattern (multi-stage):
FROM golang:{{ version }}-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o main .

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/main .
EXPOSE {{ port }}
CMD ["./main"]
""",
    "rust": """\
# Rust Dockerfile pattern (multi-stage):
FROM rust:{{ version }} AS builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=builder /app/target/release/{{ binary_name }} .
EXPOSE {{ port }}
CMD ["./{{ binary_name }}"]
""",
}

USER_PROMPT = Template("""\
<project>
Runtime: {{ runtime }}
{% if framework %}Framework: {{ framework }}{% endif %}
Package manager: {{ package_manager }}
{% if lockfile %}Lockfile: {{ lockfile }}{% endif %}
{% if build_command %}Build: {{ build_command }}{% endif %}
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

Fix the errors above. Use tools to investigate if needed.
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
Generate a Dockerfile. Follow the pattern provided but adapt to the specific project.

Rules:
1. Copy lockfile and install deps BEFORE copying source (layer caching)
2. Use --frozen-lockfile or equivalent (reproducible builds)
3. Set NODE_ENV=production or equivalent for production builds
4. If secrets are listed, add ARG + ENV for each before any RUN that needs them
5. Keep it simple - 10-20 lines is ideal

When fixing errors:
- Read the error message carefully
- Use tools (read_file, grep) to investigate actual files
- Fix only what's broken, keep what works

Output:
- dockerfile: Valid Dockerfile starting with FROM
- confidence: 0-10 (10 = certain, 5 = reasonable guess, 0 = very uncertain)
- reasoning: What you did and why (1-2 sentences)
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
        build_command=build.get("build_command"),
        start_command=build.get("start_command", '["npm", "start"]'),
        port=project.get("port", 3000),
        binary_name=project.get("name", "app"),
    )
