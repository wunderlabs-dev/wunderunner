"""Build strategy analysis agent."""

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.models.analysis import BuildStrategy
from wunderunner.settings import Analysis, get_model

USER_PROMPT = "Analyze this project's build strategy, commands, and dependencies."

SYSTEM_PROMPT = """\
<task>
Analyze a software project to determine how to build and run it in a container. Identify
monorepo structure, build commands, native dependencies, and whether multi-stage builds
are recommended.
</task>

<core_principles>
- Monorepo detection affects everything - workspace structure changes how we copy files
  and run builds
- Native dependencies require build tools in the Docker image (gcc, python3-dev, etc.)
- Multi-stage builds reduce image size for compiled languages and large dev dependencies
- Build and start commands must be accurate - wrong commands = broken containers
</core_principles>

<workflow>
TURN 1 - Monorepo and Build Config Detection (batch these):
- list_dir(".") to see project structure
- read_file("package.json") for workspaces config
- read_file("turbo.json") for Turborepo
- read_file("nx.json") for Nx
- read_file("pnpm-workspace.yaml") for pnpm workspaces
- read_file("lerna.json") for Lerna
- read_file("Cargo.toml") for Rust workspaces
- read_file("Makefile") for build commands

TURN 2 - Native Dependencies Check (batch these):
- grep("node-gyp|binding.gyp") for Node native modules
- grep("bcrypt|sharp|canvas|sqlite3|better-sqlite3") for common native deps
- grep("cgo|#include") for Go/C interop
- read_file("package.json") and check for known native packages

TURN 3 - Command Discovery:
- Check package.json scripts for "build", "start", "dev"
- Check pyproject.toml for scripts
- Check Makefile for build/run targets
- Check Procfile for start command

Complete in 2-3 turns maximum by aggressive batching.
</workflow>

<monorepo_detection>
Turborepo:
- turbo.json exists
- package.json has "workspaces" field
- monorepo_tool = "turborepo"

Nx:
- nx.json exists
- package.json may have "workspaces"
- monorepo_tool = "nx"

pnpm workspaces:
- pnpm-workspace.yaml exists
- monorepo_tool = "pnpm workspaces"

Yarn/npm workspaces:
- package.json has "workspaces" field (without turbo.json/nx.json)
- monorepo_tool = "yarn workspaces" or "npm workspaces"

Lerna (legacy):
- lerna.json exists
- monorepo_tool = "lerna"

Rust workspaces:
- Cargo.toml has [workspace] section
- monorepo_tool = "cargo workspaces"
</monorepo_detection>

<native_dependencies_detection>
Node.js native modules (require build tools):
- bcrypt, argon2 (crypto)
- sharp, canvas, jimp (image processing)
- sqlite3, better-sqlite3 (databases)
- node-sass (deprecated but still used)
- Any package with binding.gyp

Python native extensions:
- numpy, scipy, pandas (may need BLAS/LAPACK)
- psycopg2 (not psycopg2-binary)
- cryptography, bcrypt
- Packages with C extensions in setup.py

Go with cgo:
- import "C" in any .go file
- CGO_ENABLED=1 required
</native_dependencies_detection>

<multi_stage_recommendation>
Recommend multi-stage builds when:
- Compiled language (Go, Rust, TypeScript with bundling)
- Large devDependencies that aren't needed at runtime
- Build artifacts are much smaller than source + deps
- Security: don't want build tools in production image

Don't recommend multi-stage when:
- Interpreted language with no build step (simple Python/Node)
- Dev and prod dependencies are similar size
- Build process is simple enough that complexity isn't worth it
</multi_stage_recommendation>

<common_build_commands>
Node.js:
- build: "npm run build", "yarn build", "pnpm build"
- start: "npm start", "node dist/index.js", "node .next/standalone/server.js"

Python:
- build: Usually none, or "uv sync", "pip install -e ."
- start: "python main.py", "uvicorn app:app", "gunicorn app:app"

Go:
- build: "go build -o app .", "go build -o app ./cmd/server"
- start: "./app"

Rust:
- build: "cargo build --release"
- start: "./target/release/app"
</common_build_commands>

<output_fields>
monorepo: Boolean - true if this is a monorepo with workspaces
monorepo_tool: String or null - "turborepo", "nx", "pnpm workspaces", etc.
workspaces: List of workspace paths - ["packages/web", "packages/api"]
native_dependencies: List of packages needing native compilation - ["sharp", "bcrypt", "psycopg2"]
build_command: String or null - "npm run build", "go build -o app ."
start_command: String or null - "npm start", "./app"
multi_stage_recommended: Boolean - true if multi-stage Docker build is recommended
</output_fields>
"""

agent = Agent(
    model=get_model(Analysis.BUILD_STRATEGY),
    output_type=BuildStrategy,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)
