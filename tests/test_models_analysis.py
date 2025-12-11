"""Tests for analysis models."""

from wunderunner.models.analysis import (
    Analysis,
    BuildStrategy,
    CodeStyle,
    ProjectStructure,
    ServiceConfig,
)


def test_service_config_creation():
    """ServiceConfig can be created with type and env_vars."""
    config = ServiceConfig(
        type="postgres",
        env_vars=["DATABASE_HOST", "DATABASE_USER", "DATABASE_PASS"],
    )
    assert config.type == "postgres"
    assert config.env_vars == ["DATABASE_HOST", "DATABASE_USER", "DATABASE_PASS"]


def test_analysis_with_services():
    """Analysis model includes services field."""
    analysis = Analysis(
        project_structure=ProjectStructure(runtime="node"),
        build_strategy=BuildStrategy(),
        code_style=CodeStyle(),
        services=[
            ServiceConfig(type="postgres", env_vars=["DATABASE_URL"]),
            ServiceConfig(type="redis", env_vars=["REDIS_URL"]),
        ],
    )
    assert len(analysis.services) == 2
    assert analysis.services[0].type == "postgres"
    assert analysis.services[1].type == "redis"


def test_analysis_services_defaults_to_empty():
    """Analysis.services defaults to empty list."""
    analysis = Analysis(
        project_structure=ProjectStructure(runtime="node"),
        build_strategy=BuildStrategy(),
        code_style=CodeStyle(),
    )
    assert analysis.services == []
