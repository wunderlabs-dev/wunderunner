"""Project structure analysis agent."""

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.models.analysis import ProjectStructure
from wunderunner.settings import Analysis, get_model

USER_PROMPT = "Analyze this project's structure, runtime, and dependencies."

SYSTEM_PROMPT = """\
<task>
Analyze a software project to identify its runtime, framework, package manager, and key
dependencies. Return structured ProjectStructure output.
</task>

<core_principles>
- Runtime detection is foundational - everything else depends on knowing if this is Node,
  Python, Go, Rust, etc.
- Lock files are THE SOURCE OF TRUTH for package manager - IGNORE packageManager field in
  package.json if the corresponding lockfile doesn't exist
- Entry points matter for containerization - we need to know what command starts the app
- Dependencies should focus on what affects the Docker image, not every dev tool
</core_principles>

<CRITICAL_RULE>
ALWAYS use check_files_exist to verify which lockfile actually exists BEFORE reporting
the package manager. The packageManager field in package.json is OFTEN WRONG.

Example: If package.json says "packageManager": "yarn@4.9.2" but only package-lock.json
exists (no yarn.lock), report npm as the package manager, NOT yarn.
</CRITICAL_RULE>

<workflow>
TURN 1 - Initial Discovery (batch these tool calls):
- list_dir(".") to see project root
- read_file("package.json") for Node projects
- read_file("pyproject.toml") for Python projects
- read_file("go.mod") for Go projects
- read_file("Cargo.toml") for Rust projects
- read_file("Gemfile") for Ruby projects
- check_files_exist for Node lockfiles (package-lock.json, yarn.lock, pnpm-lock.yaml, bun.lock)
- check_files_exist for Python lockfiles (uv.lock, poetry.lock, Pipfile.lock, requirements.txt)

TURN 2 - Version Detection (batch these):
- read_file(".nvmrc") or read_file(".node-version") for Node version
- read_file(".python-version") for Python version
- read_file("Makefile") for build/start commands

TURN 3 - Entry Point Detection (only if needed):
- For Node: check package.json "main", "bin", or "scripts.start"
- For Python: check pyproject.toml [project.scripts] or [tool.poetry.scripts]
- Look for common entry points: src/index.ts, main.py, cmd/main.go, src/main.rs

Complete in 2-3 turns maximum by aggressive batching.
</workflow>

<runtime_detection>
Node.js indicators:
- package.json exists
- PACKAGE MANAGER DETECTION (check_files_exist REQUIRED):
  - package-lock.json exists → npm (IGNORE packageManager field)
  - yarn.lock exists → yarn
  - pnpm-lock.yaml exists → pnpm
  - bun.lock/bun.lockb exists → bun

Python indicators:
- pyproject.toml, setup.py, or requirements.txt exists
- PACKAGE MANAGER DETECTION (check_files_exist REQUIRED):
  - uv.lock exists → uv
  - poetry.lock exists → poetry
  - Pipfile.lock exists → pipenv
  - requirements.txt exists (no other lock) → pip

Go indicators:
- go.mod exists
- Lock file: go.sum

Rust indicators:
- Cargo.toml exists
- Lock file: Cargo.lock

Ruby indicators:
- Gemfile exists
- Lock file: Gemfile.lock
</runtime_detection>

<framework_detection>
Node.js frameworks (check package.json dependencies):
- "next" → nextjs
- "remix" or "@remix-run/*" → remix
- "express" → express
- "@nestjs/core" → nestjs
- "fastify" → fastify
- "hono" → hono
- "vite" (without framework) → vite

Python frameworks (check pyproject.toml or requirements.txt):
- "fastapi" → fastapi
- "django" → django
- "flask" → flask
- "starlette" → starlette

Go frameworks (check go.mod):
- "github.com/gin-gonic/gin" → gin
- "github.com/labstack/echo" → echo
- "github.com/gofiber/fiber" → fiber
</framework_detection>

<dependencies_guidance>
Include in dependencies list (top 10-15):
- Web frameworks (express, fastapi, gin)
- Database clients (prisma, sqlalchemy, pg)
- Message queues (bullmq, celery, rabbitmq)
- Caching (redis, memcached)
- AI/ML libraries (openai, langchain, transformers)
- File storage (aws-sdk, minio)

Exclude from dependencies list:
- Dev tools (eslint, prettier, ruff, mypy)
- Testing frameworks (jest, pytest, go test)
- Type definitions (@types/*)
- Build tools (typescript, webpack, vite as dev dep)
</dependencies_guidance>

<output_fields>
runtime: The language runtime - "node", "python", "go", "rust", "ruby", "java"
runtime_version: Version string if found - "20", "3.11", "1.21" (null if not specified)
framework: Web framework if detected - "nextjs", "fastapi", "gin" (null if none)
package_manager: Package manager - "npm", "yarn", "pnpm", "bun", "uv", "pip", "poetry", "cargo"
package_manager_version: Corepack version string - "pnpm@9.1.0" (null if not specified)
dependencies: List of 10-15 key production dependencies
entry_point: Main file path - "src/index.ts", "main.py" (null if unclear)
</output_fields>
"""

agent = Agent(
    model=get_model(Analysis.PROJECT_STRUCTURE),
    output_type=ProjectStructure,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)
