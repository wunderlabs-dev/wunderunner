"""Dockerfile generation agent."""

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.settings import Generation, get_model

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
For secrets (env vars with secret=True in analysis):
- Do NOT hardcode values in Dockerfile
- Use ARG for build-time secrets if needed during build
- Use ENV to declare runtime variables (values provided at container start)

Pattern for build-time secrets:
ARG DATABASE_URL
ENV DATABASE_URL=$DATABASE_URL

Pattern for runtime-only secrets (preferred):
- Just document in comments or don't include - they'll be passed via docker run -e
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
Return ONLY the Dockerfile content as a string. No markdown, no explanation, no code blocks.
Just the raw Dockerfile content starting with FROM.
</output_format>
"""

agent = Agent(
    model=get_model(Generation.DOCKERFILE),
    output_type=str,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)
