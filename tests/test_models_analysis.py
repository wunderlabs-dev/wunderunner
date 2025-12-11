"""Tests for analysis models."""

from wunderunner.models.analysis import (
    Analysis,
    BuildStrategy,
    CodeStyle,
    DetectedService,
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


def test_detected_service_creation():
    """DetectedService captures agent's service detection."""
    detected = DetectedService(
        type="postgres",
        env_vars=["DATABASE_HOST", "DATABASE_USER", "DATABASE_PASS"],
        confidence=0.95,
    )
    assert detected.type == "postgres"
    assert detected.confidence == 0.95


def test_detected_service_confidence_bounds():
    """DetectedService confidence must be 0-1."""
    detected = DetectedService(
        type="redis",
        env_vars=["REDIS_URL"],
        confidence=0.5,
    )
    assert 0 <= detected.confidence <= 1
