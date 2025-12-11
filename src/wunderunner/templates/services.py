"""Service container templates and env var mappings."""

SERVICE_TEMPLATES: dict[str, dict] = {
    "postgres": {
        "image": "postgres:16-alpine",
        "environment": {
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "postgres",
            "POSTGRES_DB": "app",
        },
        "ports": ["5432:5432"],
    },
    "redis": {
        "image": "redis:7-alpine",
        "ports": ["6379:6379"],
    },
    "mysql": {
        "image": "mysql:8",
        "environment": {
            "MYSQL_ROOT_PASSWORD": "root",
            "MYSQL_DATABASE": "app",
            "MYSQL_USER": "app",
            "MYSQL_PASSWORD": "app",
        },
        "ports": ["3306:3306"],
    },
    "mongodb": {
        "image": "mongo:7",
        "ports": ["27017:27017"],
    },
}

# Patterns for mapping app env vars to service values
# Keys are suffixes/patterns, values are the actual values
ENV_MAPPINGS: dict[str, dict[str, str]] = {
    "postgres": {
        "_HOST": "postgres",
        "_USER": "postgres",
        "_PASS": "postgres",
        "_PASSWORD": "postgres",
        "_DB": "app",
        "_DATABASE": "app",
        "_PORT": "5432",
        "_URL": "postgres://postgres:postgres@postgres:5432/app",
    },
    "mysql": {
        "_HOST": "mysql",
        "_USER": "app",
        "_PASS": "app",
        "_PASSWORD": "app",
        "_DB": "app",
        "_DATABASE": "app",
        "_PORT": "3306",
        "_URL": "mysql://app:app@mysql:3306/app",
    },
    "redis": {
        "_HOST": "redis",
        "_PORT": "6379",
        "_URL": "redis://redis:6379",
    },
    "mongodb": {
        "_HOST": "mongodb",
        "_PORT": "27017",
        "_URL": "mongodb://mongodb:27017/app",
        "_URI": "mongodb://mongodb:27017/app",
    },
}


def get_env_value(service_type: str, env_var_name: str) -> str:
    """Get the value for an env var based on service type.

    Args:
        service_type: The service type (postgres, redis, etc.)
        env_var_name: The env var name (DATABASE_HOST, REDIS_URL, etc.)

    Returns:
        The value to use for this env var when connecting to the service.
    """
    mappings = ENV_MAPPINGS.get(service_type, {})

    # Check each suffix pattern
    for suffix, value in mappings.items():
        if env_var_name.upper().endswith(suffix):
            return value

    # Default to service name (works for HOST-like vars)
    return service_type
