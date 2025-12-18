"""Tests for plan.md parser."""

from wunderunner.pipeline.implement.parser import ParsedPlan, parse_plan


def test_parse_plan_extracts_dockerfile():
    """parse_plan extracts Dockerfile content from code block."""
    plan_md = """# Containerization Plan

## Summary
Python app

## Files

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
CMD ["python", "app.py"]
```

## Reasoning
Simple setup
"""
    result = parse_plan(plan_md)

    assert isinstance(result, ParsedPlan)
    assert result.dockerfile is not None
    assert "FROM python:3.11-slim" in result.dockerfile
    assert result.compose is None


def test_parse_plan_extracts_compose():
    """parse_plan extracts docker-compose.yaml content."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM node:20-slim
```

### docker-compose.yaml
```yaml
services:
  app:
    build: .
    ports:
      - "3000:3000"
```

## Verification
1. `docker compose build` → exit 0
"""
    result = parse_plan(plan_md)

    assert result.dockerfile is not None
    assert result.compose is not None
    assert "services:" in result.compose
    assert "build: ." in result.compose


def test_parse_plan_extracts_verification():
    """parse_plan extracts verification steps."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM python:3.11
```

## Verification
1. `docker build -t app .` → exit 0
2. `docker run -d -p 8000:8000 app` → container starts
3. `curl localhost:8000/health` → 200 OK
"""
    result = parse_plan(plan_md)

    assert len(result.verification_steps) == 3
    assert result.verification_steps[0].command == "docker build -t app ."
    assert result.verification_steps[0].expected == "exit 0"


def test_parse_plan_handles_missing_sections():
    """parse_plan handles minimal plan."""
    plan_md = """# Containerization Plan

## Files

### Dockerfile
```dockerfile
FROM alpine
```
"""
    result = parse_plan(plan_md)

    assert result.dockerfile == "FROM alpine"
    assert result.compose is None
    assert result.verification_steps == []
