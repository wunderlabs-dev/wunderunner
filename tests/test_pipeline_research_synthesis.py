"""Tests for research synthesis to markdown."""

from wunderunner.pipeline.models import (
    ConfigFindings,
    DependencyFindings,
    EnvVarFinding,
    NativeDependency,
    ResearchResult,
    RuntimeFindings,
    ServiceFinding,
    ServiceFindings,
)
from wunderunner.pipeline.research.synthesis import synthesize_research


def test_synthesize_research_produces_markdown():
    """synthesize_research converts ResearchResult to markdown."""
    result = ResearchResult(
        runtime=RuntimeFindings(
            language="python", version="3.11", framework="fastapi"
        ),
        dependencies=DependencyFindings(
            package_manager="uv",
            native_deps=[NativeDependency(name="libpq-dev", reason="psycopg2")],
            start_command="uvicorn app:app",
        ),
        config=ConfigFindings(
            env_vars=[
                EnvVarFinding(name="DATABASE_URL", secret=True, service="postgres")
            ],
            config_files=[".env.example"],
        ),
        services=ServiceFindings(
            services=[ServiceFinding(type="postgres", version="15")],
        ),
    )

    markdown = synthesize_research(result)

    assert "# Project Research" in markdown
    assert "python" in markdown
    assert "3.11" in markdown
    assert "fastapi" in markdown
    assert "uv" in markdown
    assert "libpq-dev" in markdown
    assert "DATABASE_URL" in markdown
    assert "postgres" in markdown


def test_synthesize_research_handles_empty_sections():
    """synthesize_research handles missing optional data."""
    result = ResearchResult(
        runtime=RuntimeFindings(language="node"),
        dependencies=DependencyFindings(package_manager="npm"),
        config=ConfigFindings(),
        services=ServiceFindings(),
    )

    markdown = synthesize_research(result)

    assert "# Project Research" in markdown
    assert "node" in markdown
    assert "npm" in markdown
