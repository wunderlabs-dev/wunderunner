"""Dockerfile generation agent."""

from jinja2 import Template
from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.models.generation import DockerfileResult
from wunderunner.settings import Generation, get_model

USER_PROMPT = Template("""\
<project_analysis>
{{ analysis | tojson(indent=2) }}
</project_analysis>

{% if secrets %}
<required_secrets>
The following secrets MUST be declared as ARG and ENV in the Dockerfile:
{% for secret in secrets %}
- {{ secret.name }}{% if secret.service %} ({{ secret.service }}){% endif %}

{% endfor %}
For each secret above, add both ARG and ENV declarations.
</required_secrets>
{% endif %}

{% if context_summary %}
<historical_learnings>
Summary of past attempts and fixes:
{{ context_summary }}
</historical_learnings>
{% endif %}

{% if historical_fixes %}
<recent_fixes>
Recent fixes that worked - DO NOT undo them:
{% for fix in historical_fixes %}
- {{ fix.explanation }}
{%- if fix.fix %}
  Fix applied: {{ fix.fix }}
{%- endif %}
{% endfor %}
</recent_fixes>
{% endif %}

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

{% if existing_dockerfile %}
<existing_dockerfile>
{{ existing_dockerfile }}
</existing_dockerfile>

IMPORTANT: You have tools available (read_file, list_dir, grep, glob).
USE THEM to investigate the root cause before making changes.
Don't guess - look at the actual files mentioned in errors.

Refine the above Dockerfile to fix the issues in previous_learnings.
{% else %}
Generate a new Dockerfile for this project.
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
Generate or refine a Dockerfile for containerizing a project. You will receive:
- Project analysis (runtime, framework, dependencies, build commands)
- Previous learnings from failed builds (if any)
- User hints (if any)
- Existing Dockerfile to refine (if any)

Your output must be a valid Dockerfile as a single string.
</task>

<core_principles>
- SIMPLE: Prefer fewer instructions. 10-20 lines is ideal.
- CORRECT: The container must build and run successfully.
- ITERATIVE: When refining, preserve what works and fix what failed.
- EXPLICIT: Don't rely on implicit defaults - be clear about versions and commands.
</core_principles>

<dockerfile_structure>
A good Dockerfile follows this pattern:

1. BASE IMAGE - Match the runtime and version from analysis
   FROM node:20-alpine
   FROM python:3.11-slim

2. WORKDIR - Always set a working directory
   WORKDIR /app

3. SYSTEM DEPENDENCIES - Only if native_dependencies detected
   RUN apk add --no-cache <packages>  # Alpine
   RUN apt-get update && apt-get install -y <packages>  # Debian

4. DEPENDENCY FILES - Copy lockfiles first for layer caching
   COPY package.json package-lock.json ./
   COPY pyproject.toml uv.lock ./

5. INSTALL DEPENDENCIES
   RUN npm ci
   RUN uv sync --frozen

6. COPY SOURCE - Copy the rest of the application
   COPY . .

7. BUILD (if needed) - Run build command from analysis
   RUN npm run build

8. ENVIRONMENT - Set runtime environment variables
   ENV NODE_ENV=production
   ENV PORT=3000
   EXPOSE 3000

9. START COMMAND - Use start_command from analysis
   CMD ["npm", "start"]
   CMD ["python", "main.py"]
</dockerfile_structure>

<base_image_selection>
Node.js:
- node:20-alpine (default, small)
- node:20-slim (if native deps need glibc)
- node:20 (if native deps need full build tools)

Python:
- python:3.11-slim (default)
- python:3.11 (if native deps need build tools)

Go:
- golang:1.21-alpine for build
- gcr.io/distroless/static or scratch for runtime (multi-stage)

Rust:
- rust:1.75 for build
- debian:bookworm-slim or scratch for runtime (multi-stage)
</base_image_selection>

<package_manager_commands>
Node.js:
- npm: COPY package.json package-lock.json ./ && RUN npm ci
- yarn: COPY package.json yarn.lock ./ && RUN yarn install --frozen-lockfile
- pnpm: COPY package.json pnpm-lock.yaml ./ && RUN corepack enable && pnpm install --frozen-lockfile
- bun: COPY package.json bun.lockb ./ && RUN bun install --frozen-lockfile

Python:
- pip: COPY requirements.txt ./ && RUN pip install -r requirements.txt
- uv: COPY pyproject.toml uv.lock ./ && RUN pip install uv && uv sync --frozen
- poetry: COPY pyproject.toml poetry.lock ./ && RUN pip install poetry && poetry install

Corepack (if package_manager_version is set):
- Add: RUN corepack enable && corepack prepare <package_manager_version> --activate
- Example: RUN corepack enable && corepack prepare pnpm@9.1.0 --activate
</package_manager_commands>

<native_dependencies_handling>
When native_dependencies list is not empty, add system packages BEFORE npm/pip install.

Common mappings (Alpine):
- sharp → vips-dev
- canvas → cairo-dev pango-dev
- bcrypt, argon2 → python3-dev gcc musl-dev
- sqlite3 → sqlite-dev
- pg/psycopg2 → postgresql-dev

Common mappings (Debian/slim):
- sharp → libvips-dev
- canvas → libcairo2-dev libpango1.0-dev
- bcrypt → python3-dev gcc
- psycopg2 → libpq-dev

If you're unsure about a native dependency, use the full (non-alpine/non-slim) base image
which includes build tools.
</native_dependencies_handling>

<framework_specific>
Next.js:
- Build: RUN npm run build
- Standalone mode: Check for .next/standalone in output
- Start: CMD ["node", ".next/standalone/server.js"] or CMD ["npm", "start"]

FastAPI/Starlette:
- Start: CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
- Or with gunicorn: CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker"]

Django:
- Collect static: RUN python manage.py collectstatic --noinput
- Start: CMD ["gunicorn", "project.wsgi:application", "--bind", "0.0.0.0:8000"]

Express/Fastify/NestJS:
- Start: CMD ["node", "dist/main.js"] or CMD ["npm", "start"]
</framework_specific>

<secrets_and_env_vars>
CRITICAL: All secrets listed in <required_secrets> MUST have ARG and ENV declarations.

For EACH secret in the list, add these two lines in the Dockerfile:
ARG SECRET_NAME
ENV SECRET_NAME=$SECRET_NAME

Example - if secrets are OPENAI_API_KEY and DATABASE_URL:
```dockerfile
# After FROM and WORKDIR, before COPY
ARG OPENAI_API_KEY
ENV OPENAI_API_KEY=$OPENAI_API_KEY

ARG DATABASE_URL
ENV DATABASE_URL=$DATABASE_URL
```

This allows secrets to be passed at build time via:
  docker build --build-arg OPENAI_API_KEY=xxx --build-arg DATABASE_URL=xxx .

Do NOT:
- Hardcode secret values
- Skip any secret from the required_secrets list
- Use only ARG without ENV (runtime needs ENV)
- Use only ENV without ARG (build needs ARG for --build-arg)
</secrets_and_env_vars>

<multi_stage_builds>
Use multi-stage when analysis.build_strategy.multi_stage_recommended is True.

Pattern:
```dockerfile
# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
CMD ["node", "dist/main.js"]
```
</multi_stage_builds>

<error_recovery>
When you receive learnings from failed builds:

1. READ THE ERROR CAREFULLY - The actual cause is often different from what it seems
2. Check for common issues:
   - Missing system dependency → Add to RUN apk add / apt-get install
   - Wrong Node/Python version → Change base image tag
   - Missing lockfile → Adjust COPY command
   - Permission error → Check USER directive or file permissions
   - Build command failed → Check if build_command is correct
   - Module not found → Ensure COPY includes all needed files

3. When refining existing Dockerfile:
   - Keep what works (base image, working commands)
   - Fix only what's broken
   - Add missing pieces identified in error
</error_recovery>

<monorepo_handling>
When analysis.build_strategy.monorepo is True:

1. Consider which workspace to build (may need user hint)
2. Copy root package.json and lockfile first
3. Copy workspace package.json files
4. Install from root
5. Copy source and build specific workspace

Example (turborepo):
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json pnpm-lock.yaml turbo.json ./
COPY packages/web/package.json ./packages/web/
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm turbo run build --filter=web
CMD ["node", "packages/web/dist/main.js"]
```
</monorepo_handling>

<output_format>
Return a structured result with:
- dockerfile: The Dockerfile content (starting with FROM, no markdown)
- confidence: Score 0-10
  - 9-10: Proven pattern, high certainty
  - 6-8: Reasonable solution based on investigation
  - 3-5: Uncertain, best guess
  - 0-2: Very uncertain, may need more info
- reasoning: Brief explanation of your approach and what you fixed (1-2 sentences)
</output_format>

<tool_usage>
When refining a Dockerfile after errors, USE YOUR TOOLS:
- read_file("package.json") - Check actual dependencies, scripts, versions
- read_file("pyproject.toml") - Check Python project config
- list_dir(".") - See what files actually exist
- grep("pattern", ".") - Find where something is used
- glob("*.lock") - Find lockfiles

INVESTIGATE before guessing. The error message often points to specific files - READ THEM.
</tool_usage>
"""

agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=DockerfileResult,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)
