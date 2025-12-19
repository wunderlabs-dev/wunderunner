# RESEARCH-PLAN-IMPLEMENT Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the verification loop backbone with a three-phase pipeline (RESEARCH → PLAN → IMPLEMENT) that uses file-based artifact handoff and fresh LLM context per phase.

**Architecture:** Parallel specialist subagents produce structured findings, synthesized into `research.md`. A plan agent generates exact file contents in `plan.md`. Implement phase writes files and runs verification. Errors trigger ERROR-RESEARCH → FIX-PLAN cycle with constraint tracking in `fixes.json`.

**Tech Stack:**
- Pydantic AI agents with `defer_model_check=True`
- Pydantic v2 models for structured data
- `asyncio.gather()` for parallel specialist execution
- Markdown artifacts on disk (`.wunderunner/`)
- Existing filesystem tools from `wunderunner.agents.tools`

**Design Document:** `docs/plans/2025-12-18-research-plan-implement-design.md`

---

## File Structure (New)

```
src/wunderunner/
├── pipeline/                    # NEW: RPI pipeline module
│   ├── __init__.py
│   ├── models.py               # Artifact models (ResearchFindings, Plan, Fix, etc.)
│   ├── artifacts.py            # Read/write markdown artifacts
│   ├── research/               # RESEARCH phase
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # Spawns specialists, synthesizes
│   │   ├── specialists/        # Individual specialist agents
│   │   │   ├── __init__.py
│   │   │   ├── runtime.py
│   │   │   ├── dependencies.py
│   │   │   ├── config.py
│   │   │   └── services.py
│   │   └── synthesis.py        # Combine specialist outputs → research.md
│   ├── plan/                   # PLAN phase
│   │   ├── __init__.py
│   │   └── agent.py            # Generate exact Dockerfile/compose
│   ├── implement/              # IMPLEMENT phase
│   │   ├── __init__.py
│   │   ├── executor.py         # Parse plan, write files
│   │   └── verify.py           # Run docker build/start/healthcheck
│   ├── errors/                 # Error handling
│   │   ├── __init__.py
│   │   ├── research.py         # ERROR-RESEARCH agent
│   │   ├── fix_plan.py         # FIX-PLAN agent
│   │   └── constraints.py      # Constraint management
│   └── runner.py               # Main pipeline orchestrator
```

## Implementation Order

1. **Models** (Part 1) — Define all Pydantic models for artifacts
2. **Research Phase** (Part 2) — Specialists + orchestrator + synthesis
3. **Plan Phase** (Part 3) — Plan generation agent
4. **Implement Phase** (Part 4) — File writing + verification
5. **Error Handling** (Part 5) — ERROR-RESEARCH, FIX-PLAN, constraints
6. **CLI Integration** (Part 6) — Wire up with feature flag

---

## Testing Strategy

- Unit tests for each specialist agent (mock filesystem)
- Unit tests for artifact parsing/writing
- Integration tests for full pipeline (mock LLM responses)
- Use existing fixtures from `conftest.py` where applicable
- Follow TDD: write failing test → implement → verify pass → commit

## Key Patterns from Existing Codebase

**Agent creation pattern** (from `agents/analysis/project_structure.py`):
```python
agent = Agent(
    model=get_model(AgentType.ENUM_VALUE),
    output_type=OutputModel,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)
register_tools(agent)
```

**Async file I/O** (from `storage/context.py`):
```python
async with aiofiles.open(path) as f:
    content = await f.read()
return Model.model_validate_json(content)
```

**Test fixtures** (from `conftest.py`):
```python
@pytest.fixture
def node_analysis() -> Analysis:
    return Analysis(...)
```
