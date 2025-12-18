"""Tests for file writer."""

from pathlib import Path

import pytest

from wunderunner.pipeline.implement.parser import ParsedPlan
from wunderunner.pipeline.implement.writer import write_files


@pytest.mark.asyncio
async def test_write_files_creates_dockerfile(tmp_path: Path):
    """write_files creates Dockerfile in project directory."""
    plan = ParsedPlan(
        dockerfile="FROM python:3.11-slim\nWORKDIR /app\n",
        compose=None,
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    dockerfile_path = tmp_path / "Dockerfile"
    assert dockerfile_path.exists()
    assert "FROM python:3.11-slim" in dockerfile_path.read_text()


@pytest.mark.asyncio
async def test_write_files_creates_compose(tmp_path: Path):
    """write_files creates docker-compose.yaml."""
    plan = ParsedPlan(
        dockerfile="FROM node:20\n",
        compose="services:\n  app:\n    build: .\n",
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    assert "docker-compose.yaml" in files
    compose_path = tmp_path / "docker-compose.yaml"
    assert compose_path.exists()
    assert "services:" in compose_path.read_text()


@pytest.mark.asyncio
async def test_write_files_skips_none_values(tmp_path: Path):
    """write_files skips files with None content."""
    plan = ParsedPlan(
        dockerfile="FROM alpine\n",
        compose=None,
        verification_steps=[],
    )

    files = await write_files(tmp_path, plan)

    assert "Dockerfile" in files
    assert "docker-compose.yaml" not in files
    assert not (tmp_path / "docker-compose.yaml").exists()


@pytest.mark.asyncio
async def test_write_files_overwrites_existing(tmp_path: Path):
    """write_files overwrites existing files."""
    # Create existing Dockerfile
    (tmp_path / "Dockerfile").write_text("FROM old:version\n")

    plan = ParsedPlan(
        dockerfile="FROM new:version\n",
        compose=None,
        verification_steps=[],
    )

    await write_files(tmp_path, plan)

    assert "FROM new:version" in (tmp_path / "Dockerfile").read_text()
