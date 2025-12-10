<div align="center">

# wunderunner

### AI-Powered Docker Configuration Generator

**Analyze your project, generate Dockerfiles & docker-compose.yaml, and learn from build errors—all with AI.**

<p align="center">
  <a href="https://github.com/wunderlabs/wunderunner">
    <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat&logo=python&logoColor=white" />
  </a>
  <a href="https://github.com/wunderlabs/wunderunner?tab=MIT-1-ov-file">
    <img src="https://img.shields.io/badge/license-MIT-blue?style=flat" />
  </a>
  <a href="https://github.com/wunderlabs/wunderunner">
    <img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat" />
  </a>
</p>

</div>

---

<table>
<tr>
<td>

**wunderunner (`wxr`)** is a CLI tool that uses AI agents to analyze your codebase and generate production-ready Docker configurations. Point it at any project and it figures out the rest—scanning your dependencies, generating optimized Dockerfiles, and building containers.

**Self-healing by design.** When builds fail, wunderunner doesn't just report errors—it analyzes logs, identifies the root cause, fixes the configuration, and tries again. This iterative loop continues until your container runs successfully or the issue requires human intervention.

Built with [Pydantic AI](https://ai.pydantic.dev/) for structured agent workflows. Inspired by [Repo2Run](https://github.com/bytedance/Repo2Run) and [Railpack](https://github.com/railwayapp/railpack).

</td>
</tr>
</table>

---

## Quick Start

```bash
# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Run on any project
uvx wunderunner /path/to/your/project
```

That's it. wunderunner analyzes your project and generates Docker configs.

---

## How It Works

```mermaid
flowchart TD
    Analyze[🔍 Analyze Project] --> secrets{Secrets?}
    secrets -->|yes| CollectSecrets[🔐 Collect Secrets]
    secrets -->|no| Dockerfile
    CollectSecrets --> Dockerfile

    Dockerfile[📄 Generate Dockerfile] --> Validate[✅ Validate]
    Validate -->|pass| Services[🐳 Generate Compose]
    Services --> Build[🔨 Build Image]
    Build --> Start[🚀 Start Containers]
    Start --> Healthcheck[💓 Healthcheck]
    Healthcheck -->|healthy| Success((✨ Success))

    Validate -->|fail| RetryOrHint
    Build -->|fail| FixProject[🔧 Fix Project]
    Start -->|fail| FixProject
    Healthcheck -->|fail| FixProject

    FixProject -->|fixed| Dockerfile
    FixProject -->|can't fix| RetryOrHint

    RetryOrHint{Retry?} -->|attempts left| Dockerfile
    RetryOrHint -->|exhausted| HumanHint[💬 Ask Human]
    HumanHint --> Dockerfile
```

**The loop continues until success.** Each failure feeds back as a learning—informing the next generation attempt with specific context about what went wrong and how to fix it.

---

## Features

| Feature | Description |
|---------|-------------|
| **Project Analysis** | Reads package.json, requirements.txt, Cargo.toml, go.mod, and more |
| **Smart Defaults** | Chooses appropriate base images, build stages, and runtime configs |
| **Self-Healing Builds** | Automatically diagnoses failures, fixes configs, and retries |
| **Iterative Learning** | Each error informs the next attempt until the build succeeds |

---

## Key Concepts

### Human in the Loop

When automatic retries are exhausted, wunderunner asks for help instead of giving up. You provide a hint—maybe the project needs a specific system dependency, or uses an unconventional setup. Your hint becomes part of the context for the next attempt.

```
❌ Build failed after 3 attempts
💬 What should I know about this project?
> This uses puppeteer and needs chromium installed

✓ Got it. Retrying with that context...
```

### Learnings & Context

Every failure teaches the system something. Learnings accumulate across retry cycles:

- **Phase**: Where it failed (build, start, healthcheck)
- **Error type**: What kind of failure occurred
- **Error message**: The actual error output
- **Context**: Additional info (previous fixes tried, human hints)

The Dockerfile generator receives all learnings, allowing it to avoid repeating mistakes and build on what worked.

### Caching

Analysis results are cached in `.wunderunner/` to avoid re-scanning unchanged projects:

```bash
wxr /path/to/project           # Uses cache if available
wxr /path/to/project --rebuild # Ignores cache, fresh analysis
```

Cached artifacts:
- Project structure analysis
- Detected runtime and framework
- Environment variables and secrets
- Generated Dockerfile and docker-compose.yaml

### Runtime Healing

Failures during build, start, or healthcheck trigger the **FixProject** agent. This agent can:

- Modify project files (add missing configs, fix entry points)
- Update package dependencies
- Add required system packages to Dockerfile
- Fix environment variable issues

If FixProject succeeds, it resets the retry counter—giving the workflow fresh attempts with the fixed configuration.

---

**License:** MIT | **Python:** 3.11+ | **CLI:** `wxr`
