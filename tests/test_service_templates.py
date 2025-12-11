"""Tests for service templates."""


def test_service_templates_exist():
    """SERVICE_TEMPLATES dict exists with expected services."""
    from wunderunner.templates.services import SERVICE_TEMPLATES

    assert "postgres" in SERVICE_TEMPLATES
    assert "redis" in SERVICE_TEMPLATES
    assert "mysql" in SERVICE_TEMPLATES
    assert "mongodb" in SERVICE_TEMPLATES


def test_postgres_template():
    """Postgres template has required fields."""
    from wunderunner.templates.services import SERVICE_TEMPLATES

    postgres = SERVICE_TEMPLATES["postgres"]
    assert "image" in postgres
    assert "postgres" in postgres["image"]
    assert "environment" in postgres
    assert "POSTGRES_USER" in postgres["environment"]
    assert "POSTGRES_PASSWORD" in postgres["environment"]


def test_env_mappings_exist():
    """ENV_MAPPINGS dict exists for wiring app to services."""
    from wunderunner.templates.services import ENV_MAPPINGS

    assert "postgres" in ENV_MAPPINGS
    assert "redis" in ENV_MAPPINGS


def test_get_env_value_for_service():
    """get_env_value returns correct value for env var pattern."""
    from wunderunner.templates.services import get_env_value

    # Exact matches
    assert get_env_value("postgres", "DATABASE_HOST") == "postgres"
    assert get_env_value("postgres", "DATABASE_USER") == "postgres"
    assert get_env_value("postgres", "DATABASE_PORT") == "5432"

    # URL patterns
    assert "postgres://" in get_env_value("postgres", "DATABASE_URL")

    # Redis
    assert get_env_value("redis", "REDIS_URL") == "redis://redis:6379"
    assert get_env_value("redis", "REDIS_HOST") == "redis"
