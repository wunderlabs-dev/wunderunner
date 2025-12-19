# Design: RESEARCH → PLAN → IMPLEMENT Pipeline

**Date:** 2025-12-18
**Status:** Approved
**Replaces:** Verification loop backbone (pydantic-graph state machine)

## Overview

Replace wunderunner's current verification loop with a three-phase pipeline inspired by ACE-FCA (Advanced Context Engineering for Coding Agents). The key insight: context window contents are the only lever for output quality. Each phase produces a compacted artifact that becomes input for the next phase, preventing context accumulation and drift.

## Problem Statement

The current verification loop (`Analyze → Generate → Validate → Build → Improve → loop`) fails in multiple ways:

1. **Misdiagnosis** — ImproveDockerfile agent sees error + accumulated context, not a researched understanding
2. **Oscillation** — Fixes revert previous fixes despite regression checker
3. **Context noise** — Each iteration adds to conversation_history without compaction
4. **Slow convergence** — Noisy context → bad fixes → more iterations → more noise

## Solution: Three-Phase Pipeline with Compaction

```
┌─────────────────────────────────────────────────────────────┐
│                    RESEARCH PHASE                           │
│  (parallel specialist subagents → synthesize → research.md) │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    .wunderunner/research.md
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      PLAN PHASE                             │
│  (reads research.md → generates exact content → plan.md)    │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    .wunderunner/plan.md
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    IMPLEMENT PHASE                          │
│  (reads plan.md → writes files → build → verify)            │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    Success or Error
```

### Key Principles

- **Fresh LLM context per phase** — no accumulation across phases
- **Artifacts are markdown files on disk** — inspectable, cacheable, debuggable
- **PLAN contains exact file contents** — IMPLEMENT just writes, no interpretation
- **Autonomous by default** — `--review` flag for human gates at research/plan stages

## Phase Details

### RESEARCH Phase

Parallel specialist subagents, each answering a specific question:

| Specialist | Question | Output |
|------------|----------|--------|
| runtime-detector | What language, framework, version? | `{language, version, framework, entrypoint}` |
| dependency-analyzer | What deps, native libs, build cmd? | `{package_manager, native_deps, build_cmd}` |
| config-finder | What env vars, secrets, config files? | `{env_vars[], config_files[]}` |
| service-detector | What databases, queues, caches? | `{services[]}` |

**Subagent characteristics:**
- Fresh context (no conversation history)
- Tools: Read, Glob, Grep (filesystem only)
- Output: Structured JSON (not prose)
- Model: Haiku/Sonnet (fast, cheap)
- Framing: Documentarian ("report what exists, do NOT suggest improvements") + light expertise

**Orchestrator** receives all outputs and synthesizes into `research.md`.

### PLAN Phase

Single agent with fresh context. Reads only `research.md` and `fixes.json` (active constraints).

**Output: `plan.md`**

```markdown
# Containerization Plan

## Summary
Python 3.11 FastAPI app with PostgreSQL. Single-stage build using uv.

## Constraints Honored
- [x] MUST use python:3.11-slim (from fix #2)

## Files

### Dockerfile
```dockerfile
FROM python:3.11-slim
...exact content...
```

### docker-compose.yaml
```yaml
...exact content...
```

## Verification
1. `docker compose build` → exit 0
2. `docker compose up -d` → containers start
3. `curl localhost:8000/health` → 200 OK

## Reasoning
- Used slim image to minimize size
- uv for fast dependency resolution
```

### IMPLEMENT Phase

Mostly code, minimal LLM:

1. Parse `plan.md`
2. Extract code blocks (Dockerfile, docker-compose.yaml)
3. Write files to project directory
4. Execute verification steps
5. Return success or error details

## Error Handling Flow

When IMPLEMENT fails:

```
[IMPLEMENT fails]
        ↓
    .wunderunner/logs/attempt-N.log
        ↓
┌─ ERROR-RESEARCH ─┐
│  Inputs:         │
│  - Error logs    │
│  - research.md   │
│  - fixes.json    │
│                  │
│  Output:         │
│  - error-analysis.md
└──────────────────┘
        ↓
┌─ FIX-PLAN ───────┐
│  Inputs:         │
│  - error-analysis.md
│  - plan.md       │
│  - constraints   │
│                  │
│  Output:         │
│  - fix-plan.md   │
└──────────────────┘
        ↓
    IMPLEMENT (loop)
```

### error-analysis.md Structure

```markdown
# Error Analysis (Attempt 2)

## Error Summary
BUILD failed: pip cannot find package 'torch' with CUDA support

## Root Cause
Base image python:3.11-slim lacks CUDA libraries.

## Fix History Review
- Attempt 1: Changed base image (unrelated)
- No previous torch/CUDA attempts

## Exhaustion Status
- [ ] Try CPU-only torch (not yet attempted)
- [ ] Try nvidia/cuda base image (not yet attempted)

**Recommendation:** Continue — unexplored options remain
```

## Fix History & Constraints

### fixes.json Schema

```json
{
  "project": "my-fastapi-app",
  "created_at": "2024-01-15T10:00:00Z",
  "attempts": [
    {
      "attempt": 1,
      "timestamp": "2024-01-15T10:05:00Z",
      "phase": "BUILD",
      "error": {
        "type": "missing_dependency",
        "message": "ModuleNotFoundError: No module named 'pandas'",
        "exit_code": 1
      },
      "diagnosis": "pandas imported but not in requirements",
      "changes": [
        {
          "file": "Dockerfile",
          "before": "RUN pip install -r requirements.txt",
          "after": "RUN pip install -r requirements.txt pandas"
        }
      ],
      "outcome": "success"
    }
  ],
  "active_constraints": [
    {
      "id": "c1",
      "rule": "MUST include pandas in pip install",
      "reason": "Required by app.py import",
      "from_attempt": 1,
      "added_at": "2024-01-15T10:05:00Z",
      "success_count": 0,
      "status": "hard"
    }
  ]
}
```

### Constraint Lifecycle

```
Fix succeeds → constraint added (status: "hard", success_count: 0)
        ↓
Next successful build → success_count++
        ↓
success_count >= 3 → status: "soft" (can be reconsidered)
        ↓
Constraint violated & causes failure → reset to "hard"
```

## Termination Conditions

Two conditions work together:

1. **Hard ceiling:** `max_attempts` (default: 5)
2. **Constraint saturation:** ERROR-RESEARCH reports "all standard approaches exhausted"

Exit states:

| Exit | Meaning | User Action |
|------|---------|-------------|
| Success | Container builds and passes healthcheck | Deploy |
| Max attempts | Tried N times, still failing | Check logs, run with `--review` |
| Saturated | Out of ideas | Manual intervention needed |

## Caching & Incremental Runs

### Cache Invalidation

| Artifact | Invalidated When |
|----------|------------------|
| research.md | Project files modified (pyproject.toml, package.json, etc.) |
| plan.md | research.md regenerated OR constraints changed |
| fixes.json | Never invalidated (append-only history) |

### CLI Flags

```bash
wxr containerize ./project              # use cache when valid
wxr containerize ./project --rebuild    # force re-run RESEARCH
wxr containerize ./project --replan     # force re-run PLAN
wxr containerize ./project --fresh      # ignore all cache
wxr containerize ./project --review     # human gates at research/plan
```

## Artifact Directory Structure

```
.wunderunner/
├── research.md          # RESEARCH output
├── plan.md              # PLAN output
├── fixes.json           # Fix history with constraints
├── error-analysis.md    # ERROR-RESEARCH output
├── fix-plan.md          # FIX-PLAN output
└── logs/
    ├── attempt-1.log
    └── attempt-2.log
```

## Migration Strategy

**Parallel implementation** alongside current architecture:

1. Build new pipeline in separate module (`wunderunner/pipeline/`)
2. Feature flag to switch between old and new
3. Validate new pipeline on test projects
4. Deprecate old architecture after validation

### Components to Reuse

| Component | Reuse? | Notes |
|-----------|--------|-------|
| Docker build/run code | Keep | `activities/docker.py` |
| Service detection logic | Adapt | Becomes specialist agent |
| Validation rubric | Keep | Validate plan.md before IMPLEMENT |
| Settings/config | Keep | Model selection, API keys |
| CLI structure | Adapt | New flags |

### Components to Replace

| Current | New |
|---------|-----|
| Pydantic Graph state machine | Linear pipeline with error loop |
| `ContainerizeState` accumulation | Artifacts on disk |
| `ImproveDockerfile` agent | ERROR-RESEARCH + FIX-PLAN |
| `conversation_history` | No history — artifacts are context |
| Regression checker | Constraints in fixes.json |

## References

- [ACE-FCA: Advanced Context Engineering for Coding Agents](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)
- HumanLayer researcher implementation patterns
