"""Tests for auth exceptions."""

import pytest

from wunderunner.exceptions import (
    AuthError,
    NoAuthError,
    OAuthCallbackError,
    TokenExpiredError,
    TokenRefreshError,
    WunderunnerError,
)


class TestAuthExceptions:
    """Test auth exception hierarchy."""

    def test_auth_error_inherits_from_wunderunner_error(self):
        """AuthError is a WunderunnerError."""
        error = AuthError("test")
        assert isinstance(error, WunderunnerError)

    def test_token_expired_error_inherits_from_auth_error(self):
        """TokenExpiredError is an AuthError."""
        error = TokenExpiredError("expired")
        assert isinstance(error, AuthError)

    def test_token_refresh_error_inherits_from_auth_error(self):
        """TokenRefreshError is an AuthError."""
        error = TokenRefreshError("refresh failed")
        assert isinstance(error, AuthError)

    def test_oauth_callback_error_inherits_from_auth_error(self):
        """OAuthCallbackError is an AuthError."""
        error = OAuthCallbackError("callback timeout")
        assert isinstance(error, AuthError)

    def test_no_auth_error_inherits_from_auth_error(self):
        """NoAuthError is an AuthError."""
        error = NoAuthError("anthropic")
        assert isinstance(error, AuthError)

    def test_no_auth_error_includes_provider_in_message(self):
        """NoAuthError message includes provider name."""
        error = NoAuthError("anthropic")
        assert "anthropic" in str(error).lower()

    def test_no_auth_error_suggests_login_command(self):
        """NoAuthError message suggests wxr auth login."""
        error = NoAuthError("anthropic")
        assert "wxr auth login" in str(error)
