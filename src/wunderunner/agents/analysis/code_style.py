"""Code style analysis agent."""

from pydantic_ai import Agent

from wunderunner.agents.tools import AgentDeps, register_tools
from wunderunner.models.analysis import CodeStyle
from wunderunner.settings import Analysis, get_model

USER_PROMPT = "Analyze this project's code style, tooling, and Docker configuration."

SYSTEM_PROMPT = """\
<task>
Analyze a project's code style, tooling, and existing Docker configuration. This helps
determine if we should respect existing patterns and avoid overwriting Docker files.
</task>

<core_principles>
- Existing Docker files might be intentional - don't blindly overwrite
- TypeScript detection affects Dockerfile build steps
- Test framework detection helps with CI/CD recommendations
- Linting/formatting tools indicate code quality standards
</core_principles>

<workflow>
TURN 1 - Root Directory Scan (batch these):
- list_dir(".") to see all config files
- read_file("package.json") for dependencies and scripts
- read_file("pyproject.toml") for Python tooling
- file_stats("Dockerfile") to check if it exists
- file_stats("docker-compose.yaml") or file_stats("docker-compose.yml")

TURN 2 - TypeScript and Tooling Detection (batch these):
- file_stats("tsconfig.json") for TypeScript
- glob("*.ts") or glob("*.tsx") for TypeScript files
- file_stats(".eslintrc.json") or file_stats("eslint.config.js")
- file_stats(".prettierrc") or file_stats(".prettierrc.json")
- file_stats("ruff.toml") or check pyproject.toml for [tool.ruff]

TURN 3 - Test Framework Detection:
- Check package.json for jest, vitest, mocha in devDependencies
- Check pyproject.toml for pytest
- Look for test directories: tests/, __tests__/, spec/
- Check for test scripts in package.json or Makefile

Complete in 2-3 turns maximum by aggressive batching.
</workflow>

<typescript_detection>
TypeScript is used if ANY of:
- tsconfig.json exists
- "typescript" in package.json dependencies or devDependencies
- .ts or .tsx files exist in src/

TypeScript affects Docker builds:
- Need tsc or bundler (esbuild, swc, vite) in build step
- May need separate build stage in multi-stage Dockerfile
- Output typically goes to dist/ or build/
</typescript_detection>

<linting_detection>
ESLint indicators:
- .eslintrc, .eslintrc.json, .eslintrc.js, .eslintrc.yml
- eslint.config.js, eslint.config.mjs (flat config)
- "eslint" in package.json devDependencies

Prettier indicators:
- .prettierrc, .prettierrc.json, .prettierrc.js, .prettierrc.yml
- prettier.config.js
- "prettier" in package.json devDependencies

Python linting (ruff, black, flake8):
- ruff.toml, .ruff.toml
- [tool.ruff] in pyproject.toml
- [tool.black] in pyproject.toml
</linting_detection>

<test_framework_detection>
Node.js test frameworks (check package.json devDependencies):
- "jest" → test_framework: "jest"
- "vitest" → test_framework: "vitest"
- "mocha" → test_framework: "mocha"
- "@playwright/test" → test_framework: "playwright"

Python test frameworks (check pyproject.toml):
- "pytest" in dependencies → test_framework: "pytest"
- [tool.pytest] section → test_framework: "pytest"

Go:
- *_test.go files exist → test_framework: "go test"

Rust:
- #[test] in source files → test_framework: "cargo test"
</test_framework_detection>

<docker_detection>
Check for existing Docker configuration:

Dockerfile exists if:
- file_stats("Dockerfile") succeeds (file exists)
- Variations: Dockerfile.prod, Dockerfile.dev

docker-compose exists if:
- file_stats("docker-compose.yaml") succeeds
- file_stats("docker-compose.yml") succeeds
- Variations: docker-compose.prod.yaml, compose.yaml

If Docker files exist, we may want to:
- Warn user before overwriting
- Analyze existing config for patterns to preserve
- Offer to enhance rather than replace
</docker_detection>

<output_format>
Return CodeStyle object:
- uses_typescript: true if TypeScript is configured
- uses_eslint: true if ESLint is configured
- uses_prettier: true if Prettier is configured
- test_framework: Name of test framework or null (e.g., "jest", "pytest")
- dockerfile_exists: true if Dockerfile exists in project root
- compose_exists: true if docker-compose.yaml/yml exists
</output_format>
"""

agent = Agent(
    model=get_model(Analysis.CODE_STYLE),
    output_type=CodeStyle,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)

register_tools(agent)
