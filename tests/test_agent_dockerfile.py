"""Tests for Dockerfile generation agent."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from jinja2 import Template

from wunderunner.agents.generation.dockerfile import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    RUNTIME_TEMPLATES,
    agent,
    get_runtime_template,
)
from wunderunner.agents.tools import AgentDeps
from wunderunner.models.generation import DockerfileResult


class TestDockerfilePrompts:
    """Test prompt definitions."""

    def test_system_prompt_exists(self):
        """System prompt is defined and non-empty."""
        assert SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 100

    def test_user_prompt_is_template(self):
        """User prompt is a Jinja2 template."""
        assert USER_PROMPT
        assert isinstance(USER_PROMPT, Template)

    def test_system_prompt_mentions_dockerfile(self):
        """System prompt mentions Dockerfile generation."""
        assert "dockerfile" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_development(self):
        """System prompt clarifies development containers."""
        assert "development" in SYSTEM_PROMPT.lower()


class TestDockerfileAgent:
    """Test agent configuration."""

    def test_agent_has_result_type(self):
        """Agent is configured to return DockerfileResult."""
        assert agent._output_type == DockerfileResult

    def test_agent_has_deps_type(self):
        """Agent uses AgentDeps for dependencies."""
        assert agent._deps_type == AgentDeps

    def test_agent_has_tools(self):
        """Agent has filesystem tools registered."""
        tools = agent._function_toolset.tools
        tool_names = list(tools.keys())
        assert "read_file" in tool_names


class TestRuntimeTemplates:
    """Test RUNTIME_TEMPLATES dictionary."""

    def test_all_runtimes_exist(self):
        """All expected runtime templates are defined."""
        assert "node" in RUNTIME_TEMPLATES
        assert "python" in RUNTIME_TEMPLATES
        assert "go" in RUNTIME_TEMPLATES
        assert "rust" in RUNTIME_TEMPLATES

    def test_node_template_structure(self):
        """Node template has required Dockerfile instructions."""
        template = RUNTIME_TEMPLATES["node"]
        assert "FROM node:" in template
        assert "WORKDIR" in template
        assert "npm install" in template
        assert "COPY" in template

    def test_python_template_structure(self):
        """Python template has required instructions."""
        template = RUNTIME_TEMPLATES["python"]
        assert "FROM python:" in template
        assert "WORKDIR" in template
        assert "pip" in template

    def test_go_template_structure(self):
        """Go template has required instructions."""
        template = RUNTIME_TEMPLATES["go"]
        assert "FROM golang:" in template
        assert "go mod download" in template

    def test_rust_template_structure(self):
        """Rust template has required instructions."""
        template = RUNTIME_TEMPLATES["rust"]
        assert "FROM rust:" in template
        assert "Cargo.toml" in template


class TestGetRuntimeTemplate:
    """Test get_runtime_template function."""

    def test_node_template_renders(self):
        """Node template renders with analysis data."""
        analysis = {
            "project_structure": {"runtime_version": "20", "port": 3000},
            "build_strategy": {
                "start_command": '["npm", "run", "dev"]',
                "lockfile": "package-lock.json",
                "package_manager": "npm",
            },
        }
        result = get_runtime_template("node", analysis)
        assert "FROM node:20-alpine" in result
        assert "package-lock.json" in result
        assert "npm install" in result

    def test_python_pip_template_renders(self):
        """Python template renders with pip."""
        analysis = {
            "project_structure": {"runtime_version": "3.11"},
            "build_strategy": {
                "package_manager": "pip",
                "start_command": '["python", "app.py"]',
            },
        }
        result = get_runtime_template("python", analysis)
        assert "FROM python:3.11-slim" in result
        assert "requirements.txt" in result

    def test_python_uv_template_renders(self):
        """Python template renders with uv."""
        analysis = {
            "project_structure": {"runtime_version": "3.12"},
            "build_strategy": {
                "package_manager": "uv",
                "lockfile": "uv.lock",
                "start_command": '["uv", "run", "app.py"]',
            },
        }
        result = get_runtime_template("python", analysis)
        assert "uv sync" in result
        assert "uv.lock" in result

    def test_python_poetry_template_renders(self):
        """Python template renders with poetry."""
        analysis = {
            "project_structure": {"runtime_version": "3.11"},
            "build_strategy": {
                "package_manager": "poetry",
                "lockfile": "poetry.lock",
                "start_command": '["poetry", "run", "python", "app.py"]',
            },
        }
        result = get_runtime_template("python", analysis)
        assert "poetry install" in result
        assert "poetry.lock" in result

    def test_go_template_renders(self):
        """Go template renders with analysis data."""
        analysis = {
            "project_structure": {"runtime_version": "1.21"},
            "build_strategy": {"start_command": '["go", "run", "."]'},
        }
        result = get_runtime_template("go", analysis)
        assert "FROM golang:1.21-alpine" in result
        assert "go mod download" in result

    def test_rust_template_renders(self):
        """Rust template renders with analysis data."""
        analysis = {
            "project_structure": {"runtime_version": "1.75"},
            "build_strategy": {"start_command": '["cargo", "run"]'},
        }
        result = get_runtime_template("rust", analysis)
        assert "FROM rust:1.75" in result
        assert "Cargo.toml" in result

    def test_unknown_runtime_falls_back_to_node(self):
        """Unknown runtime falls back to node template."""
        analysis = {
            "project_structure": {},
            "build_strategy": {},
        }
        result = get_runtime_template("unknown", analysis)
        assert "FROM node:" in result

    def test_default_version_when_missing(self):
        """Uses default version when not in analysis."""
        analysis = {"project_structure": {}, "build_strategy": {}}
        result = get_runtime_template("node", analysis)
        assert "FROM node:20-alpine" in result  # Default is 20


class TestUserPromptRendering:
    """Test USER_PROMPT template rendering."""

    def test_renders_project_info(self):
        """Template renders project info."""
        rendered = USER_PROMPT.render(
            runtime="node",
            framework="express",
            package_manager="npm",
            lockfile="package-lock.json",
            start_command="npm run dev",
            port=3000,
            runtime_template="FROM node:20",
            secrets=None,
            learnings=None,
            existing_dockerfile=None,
            hints=None,
        )
        assert "node" in rendered
        assert "express" in rendered
        assert "npm" in rendered

    def test_renders_secrets_section(self):
        """Template renders secrets when provided."""
        secrets = [
            MagicMock(name="DATABASE_URL"),
            MagicMock(name="API_KEY"),
        ]
        # Fix mock .name attribute
        secrets[0].name = "DATABASE_URL"
        secrets[1].name = "API_KEY"

        rendered = USER_PROMPT.render(
            runtime="node",
            framework=None,
            package_manager="npm",
            lockfile=None,
            start_command="npm start",
            port=3000,
            runtime_template="FROM node:20",
            secrets=secrets,
            learnings=None,
            existing_dockerfile=None,
            hints=None,
        )
        assert "DATABASE_URL" in rendered
        assert "API_KEY" in rendered
        assert "ARG" in rendered  # Instructions mention ARG

    def test_renders_learnings_section(self):
        """Template renders learnings/errors when provided."""
        learnings = [
            MagicMock(phase="BUILD", error_message="npm ERR! Missing script"),
        ]

        rendered = USER_PROMPT.render(
            runtime="node",
            framework=None,
            package_manager="npm",
            lockfile=None,
            start_command="npm start",
            port=3000,
            runtime_template="FROM node:20",
            secrets=None,
            learnings=learnings,
            existing_dockerfile=None,
            hints=None,
        )
        assert "BUILD" in rendered
        assert "npm ERR!" in rendered

    def test_renders_existing_dockerfile(self):
        """Template renders existing dockerfile for fixes."""
        rendered = USER_PROMPT.render(
            runtime="node",
            framework=None,
            package_manager="npm",
            lockfile=None,
            start_command="npm start",
            port=3000,
            runtime_template="FROM node:20",
            secrets=None,
            learnings=None,
            existing_dockerfile="FROM node:18\nWORKDIR /app",
            hints=None,
        )
        assert "FROM node:18" in rendered
        assert "Fix the errors" in rendered


class TestDockerfileAgentExecution:
    """Test agent execution with mocked LLM."""

    @pytest.mark.asyncio
    async def test_returns_dockerfile_result(self, tmp_path: Path):
        """Agent returns DockerfileResult."""
        mock_result = DockerfileResult(
            dockerfile="FROM node:20\nWORKDIR /app\nCMD npm start",
            confidence=8,
            reasoning="Standard Node.js setup",
        )
        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock(output=mock_result)
            deps = AgentDeps(project_dir=tmp_path)

            result = await agent.run("test prompt", deps=deps)

            assert "FROM node:20" in result.output.dockerfile
            assert result.output.confidence == 8
