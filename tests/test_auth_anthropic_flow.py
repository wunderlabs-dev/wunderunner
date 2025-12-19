"""Tests for Anthropic OAuth flow."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wunderunner.auth.models import TokenSet
from wunderunner.auth.providers.anthropic import (
    AnthropicOAuth,
    build_auth_url,
    exchange_code_for_tokens,
    refresh_access_token,
)


class TestBuildAuthUrl:
    """Test build_auth_url function."""

    def test_includes_client_id(self):
        """Auth URL includes client ID."""
        url = build_auth_url(
            code_challenge="challenge",
            code_verifier="verifier123",
        )
        assert f"client_id={AnthropicOAuth.CLIENT_ID}" in url

    def test_includes_code_challenge(self):
        """Auth URL includes PKCE code challenge."""
        url = build_auth_url(
            code_challenge="test_challenge",
            code_verifier="verifier123",
        )
        assert "code_challenge=test_challenge" in url
        assert "code_challenge_method=S256" in url

    def test_includes_state_as_verifier(self):
        """Auth URL uses code_verifier as state (per OpenCode)."""
        url = build_auth_url(
            code_challenge="challenge",
            code_verifier="my_verifier_value",
        )
        assert "state=my_verifier_value" in url

    def test_includes_redirect_uri(self):
        """Auth URL includes Anthropic's redirect URI."""
        url = build_auth_url(
            code_challenge="challenge",
            code_verifier="verifier",
        )
        assert "redirect_uri=" in url
        assert "console.anthropic.com" in url

    def test_response_type_is_code(self):
        """Auth URL requests authorization code."""
        url = build_auth_url(
            code_challenge="challenge",
            code_verifier="verifier",
        )
        assert "response_type=code" in url

    def test_includes_code_true_param(self):
        """Auth URL includes code=true parameter."""
        url = build_auth_url(
            code_challenge="challenge",
            code_verifier="verifier",
        )
        assert "code=true" in url


class TestExchangeCodeForTokens:
    """Test exchange_code_for_tokens function."""

    @pytest.mark.asyncio
    async def test_returns_token_set(self):
        """exchange_code_for_tokens returns TokenSet."""
        mock_response = {
            "access_token": "access123",
            "refresh_token": "refresh456",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_instance.post.return_value = mock_response_obj

            tokens = await exchange_code_for_tokens(
                code="auth_code",
                code_verifier="verifier",
            )

            assert isinstance(tokens, TokenSet)
            assert tokens.access_token == "access123"
            assert tokens.refresh_token == "refresh456"

    @pytest.mark.asyncio
    async def test_calculates_expires_at(self):
        """exchange_code_for_tokens calculates absolute expiry time."""
        mock_response = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_instance.post.return_value = mock_response_obj

            before = int(time.time())
            tokens = await exchange_code_for_tokens(
                code="code",
                code_verifier="verifier",
            )
            after = int(time.time())

            # expires_at should be now + expires_in
            assert before + 3600 <= tokens.expires_at <= after + 3600

    @pytest.mark.asyncio
    async def test_handles_code_with_state_hash(self):
        """exchange_code_for_tokens parses code#state format."""
        mock_response = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_instance.post.return_value = mock_response_obj

            # Anthropic returns code in format: code#state
            tokens = await exchange_code_for_tokens(
                code="auth_code_123#state_from_anthropic",
                code_verifier="verifier",
            )

            assert isinstance(tokens, TokenSet)
            # Verify the POST was called with parsed code
            call_args = mock_instance.post.call_args
            json_data = call_args.kwargs["json"]
            assert json_data["code"] == "auth_code_123"
            assert json_data["state"] == "state_from_anthropic"


class TestRefreshAccessToken:
    """Test refresh_access_token function."""

    @pytest.mark.asyncio
    async def test_returns_new_token_set(self):
        """refresh_access_token returns new TokenSet."""
        mock_response = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 7200,
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_instance.post.return_value = mock_response_obj

            tokens = await refresh_access_token(refresh_token="old_refresh")

            assert isinstance(tokens, TokenSet)
            assert tokens.access_token == "new_access"
            assert tokens.refresh_token == "new_refresh"
