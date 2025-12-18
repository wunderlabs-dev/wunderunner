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


class ValidationError(WunderunnerError):
    """Failed to validate generated artifacts."""


class AuthError(WunderunnerError):
    """Base exception for authentication errors."""


class TokenExpiredError(AuthError):
    """Token expired and refresh failed."""


class TokenRefreshError(AuthError):
    """Failed to refresh OAuth token."""


class OAuthCallbackError(AuthError):
    """OAuth callback server failed or timed out."""


class NoAuthError(AuthError):
    """No authentication configured for provider."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"No {provider} credentials configured. "
            f"Run `wxr auth login` or set {provider.upper()}_API_KEY environment variable."
        )
