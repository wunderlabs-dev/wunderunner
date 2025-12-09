"""Exception hierarchy for wunderunner."""


class WunderunnerError(Exception):
    """Base exception for all wunderunner errors."""


class AnalyzeError(WunderunnerError):
    """Failed to analyze project."""


class DockerfileError(WunderunnerError):
    """Failed to generate Dockerfile."""


class ServicesError(WunderunnerError):
    """Failed to generate or manage services."""


class BuildError(WunderunnerError):
    """Failed to build Docker image."""


class StartError(WunderunnerError):
    """Failed to start services."""


class HealthcheckError(WunderunnerError):
    """Services failed healthcheck."""
