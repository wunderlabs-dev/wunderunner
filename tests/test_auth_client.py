"""Tests for auth client factory."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.auth.client import get_anthropic_client
from wunderunner.auth.models import Provider, TokenSet
from wunderunner.auth.providers.anthropic import AnthropicOAuth


class TestGetAnthropicClient:
    """Test get_anthropic_client function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_tokens(self):
        """Returns None when no OAuth tokens exist."""
        with patch("wunderunner.auth.client.load_store", new_callable=AsyncMock) as mock_load:
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore()

            client = await get_anthropic_client()
            assert client is None

    @pytest.mark.asyncio
    async def test_returns_client_with_valid_tokens(self):
        """Returns configured httpx client when tokens are valid."""
        tokens = TokenSet(
            access_token="valid_access_token",
            refresh_token="refresh",
            expires_at=int(time.time()) + 3600,  # Valid for 1 hour
            token_type="Bearer",
        )

        with patch("wunderunner.auth.client.load_store", new_callable=AsyncMock) as mock_load:
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore(anthropic=tokens)

            client = await get_anthropic_client()

            assert client is not None
            # Check headers are set
            assert "authorization" in [k.lower() for k in client.headers.keys()]

    @pytest.mark.asyncio
    async def test_client_has_bearer_token(self):
        """Client has Bearer authorization header."""
        tokens = TokenSet(
            access_token="my_access_token",
            refresh_token="refresh",
            expires_at=int(time.time()) + 3600,
            token_type="Bearer",
        )

        with patch("wunderunner.auth.client.load_store", new_callable=AsyncMock) as mock_load:
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore(anthropic=tokens)

            client = await get_anthropic_client()

            auth_header = client.headers.get("authorization")
            assert auth_header == "Bearer my_access_token"

    @pytest.mark.asyncio
    async def test_client_has_beta_header(self):
        """Client has Anthropic beta header for OAuth."""
        tokens = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=int(time.time()) + 3600,
            token_type="Bearer",
        )

        with patch("wunderunner.auth.client.load_store", new_callable=AsyncMock) as mock_load:
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore(anthropic=tokens)

            client = await get_anthropic_client()

            beta_header = client.headers.get("anthropic-beta")
            assert beta_header == AnthropicOAuth.BETA_HEADER

    @pytest.mark.asyncio
    async def test_refreshes_expired_tokens(self):
        """Refreshes tokens when expired."""
        expired_tokens = TokenSet(
            access_token="expired_access",
            refresh_token="valid_refresh",
            expires_at=int(time.time()) - 100,  # Expired
            token_type="Bearer",
        )
        new_tokens = TokenSet(
            access_token="new_access",
            refresh_token="new_refresh",
            expires_at=int(time.time()) + 3600,
            token_type="Bearer",
        )

        with (
            patch("wunderunner.auth.client.load_store", new_callable=AsyncMock) as mock_load,
            patch("wunderunner.auth.client.save_tokens", new_callable=AsyncMock) as mock_save,
            patch("wunderunner.auth.client.refresh_access_token", new_callable=AsyncMock) as mock_refresh,
        ):
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore(anthropic=expired_tokens)
            mock_refresh.return_value = new_tokens

            client = await get_anthropic_client()

            mock_refresh.assert_called_once_with(expired_tokens.refresh_token)
            mock_save.assert_called_once()
            auth_header = client.headers.get("authorization")
            assert auth_header == "Bearer new_access"

    @pytest.mark.asyncio
    async def test_returns_none_on_refresh_failure(self):
        """Returns None when token refresh fails."""
        expired_tokens = TokenSet(
            access_token="expired",
            refresh_token="invalid_refresh",
            expires_at=int(time.time()) - 100,
            token_type="Bearer",
        )

        with (
            patch("wunderunner.auth.client.load_store", new_callable=AsyncMock) as mock_load,
            patch("wunderunner.auth.client.refresh_access_token", new_callable=AsyncMock) as mock_refresh,
        ):
            from wunderunner.auth.models import AuthStore
            from wunderunner.exceptions import TokenRefreshError
            mock_load.return_value = AuthStore(anthropic=expired_tokens)
            mock_refresh.side_effect = TokenRefreshError("Refresh failed")

            client = await get_anthropic_client()
            assert client is None
