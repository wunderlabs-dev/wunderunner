"""Tests for service templates."""

import pytest

from wunderunner.templates.services import ENV_MAPPINGS, SERVICE_TEMPLATES, get_env_value


class TestServiceTemplates:
    """Test SERVICE_TEMPLATES dictionary."""

    def test_all_services_exist(self):
        """All expected services are defined."""
        assert "postgres" in SERVICE_TEMPLATES
        assert "redis" in SERVICE_TEMPLATES
        assert "mysql" in SERVICE_TEMPLATES
        assert "mongodb" in SERVICE_TEMPLATES

    def test_postgres_template_structure(self):
        """Postgres template has required fields."""
        postgres = SERVICE_TEMPLATES["postgres"]
        assert "image" in postgres
        assert "postgres" in postgres["image"]
        assert "environment" in postgres
        assert "POSTGRES_USER" in postgres["environment"]
        assert "POSTGRES_PASSWORD" in postgres["environment"]
        assert "POSTGRES_DB" in postgres["environment"]
        assert "ports" in postgres

    def test_redis_template_structure(self):
        """Redis template has required fields."""
        redis = SERVICE_TEMPLATES["redis"]
        assert "image" in redis
        assert "redis" in redis["image"]
        assert "ports" in redis
        assert "6379:6379" in redis["ports"]

    def test_mysql_template_structure(self):
        """MySQL template has required fields."""
        mysql = SERVICE_TEMPLATES["mysql"]
        assert "image" in mysql
        assert "mysql" in mysql["image"]
        assert "environment" in mysql
        assert "MYSQL_ROOT_PASSWORD" in mysql["environment"]
        assert "MYSQL_DATABASE" in mysql["environment"]
        assert "ports" in mysql

    def test_mongodb_template_structure(self):
        """MongoDB template has required fields."""
        mongo = SERVICE_TEMPLATES["mongodb"]
        assert "image" in mongo
        assert "mongo" in mongo["image"]
        assert "ports" in mongo


class TestEnvMappings:
    """Test ENV_MAPPINGS dictionary."""

    def test_all_services_have_mappings(self):
        """All service types have env var mappings."""
        assert "postgres" in ENV_MAPPINGS
        assert "redis" in ENV_MAPPINGS
        assert "mysql" in ENV_MAPPINGS
        assert "mongodb" in ENV_MAPPINGS

    def test_postgres_mappings(self):
        """Postgres has expected env var mappings."""
        pg = ENV_MAPPINGS["postgres"]
        assert "_HOST" in pg
        assert "_USER" in pg
        assert "_PASSWORD" in pg or "_PASS" in pg
        assert "_DB" in pg or "_DATABASE" in pg
        assert "_PORT" in pg
        assert "_URL" in pg

    def test_redis_mappings(self):
        """Redis has expected env var mappings."""
        redis = ENV_MAPPINGS["redis"]
        assert "_HOST" in redis
        assert "_PORT" in redis
        assert "_URL" in redis

    def test_mysql_mappings(self):
        """MySQL has expected env var mappings."""
        mysql = ENV_MAPPINGS["mysql"]
        assert "_HOST" in mysql
        assert "_USER" in mysql
        assert "_PASSWORD" in mysql or "_PASS" in mysql
        assert "_URL" in mysql

    def test_mongodb_mappings(self):
        """MongoDB has expected env var mappings."""
        mongo = ENV_MAPPINGS["mongodb"]
        assert "_HOST" in mongo
        assert "_PORT" in mongo
        assert "_URL" in mongo or "_URI" in mongo


class TestGetEnvValue:
    """Test get_env_value function."""

    def test_postgres_host(self):
        """Postgres host returns 'postgres'."""
        assert get_env_value("postgres", "DATABASE_HOST") == "postgres"
        assert get_env_value("postgres", "PG_HOST") == "postgres"

    def test_postgres_user(self):
        """Postgres user returns 'postgres'."""
        assert get_env_value("postgres", "DATABASE_USER") == "postgres"
        assert get_env_value("postgres", "PGUSER") == "postgres"

    def test_postgres_password(self):
        """Postgres password returns expected value."""
        assert get_env_value("postgres", "DATABASE_PASSWORD") == "postgres"
        assert get_env_value("postgres", "DB_PASS") == "postgres"

    def test_postgres_port(self):
        """Postgres port returns '5432'."""
        assert get_env_value("postgres", "DATABASE_PORT") == "5432"

    def test_postgres_url(self):
        """Postgres URL returns full connection string."""
        url = get_env_value("postgres", "DATABASE_URL")
        assert "postgres://" in url
        assert "@postgres:" in url
        assert ":5432" in url

    def test_redis_host(self):
        """Redis host returns 'redis'."""
        assert get_env_value("redis", "REDIS_HOST") == "redis"

    def test_redis_url(self):
        """Redis URL returns full connection string."""
        assert get_env_value("redis", "REDIS_URL") == "redis://redis:6379"

    def test_mysql_url(self):
        """MySQL URL returns full connection string."""
        url = get_env_value("mysql", "DATABASE_URL")
        assert "mysql://" in url

    def test_mongodb_url(self):
        """MongoDB URL returns full connection string."""
        url = get_env_value("mongodb", "MONGO_URL")
        assert "mongodb://" in url

    def test_mongodb_uri(self):
        """MongoDB URI also works."""
        uri = get_env_value("mongodb", "MONGODB_URI")
        assert "mongodb://" in uri

    def test_unknown_suffix_returns_service_name(self):
        """Unknown suffix returns service type as default."""
        assert get_env_value("postgres", "RANDOM_VAR") == "postgres"
        assert get_env_value("redis", "UNKNOWN") == "redis"

    def test_case_insensitive_matching(self):
        """Suffix matching is case-insensitive."""
        assert get_env_value("postgres", "database_host") == "postgres"
        assert get_env_value("redis", "redis_port") == "6379"

    def test_unknown_service_returns_service_name(self):
        """Unknown service type returns the service name."""
        assert get_env_value("unknown_service", "SOME_VAR") == "unknown_service"
