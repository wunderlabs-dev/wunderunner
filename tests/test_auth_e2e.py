"""End-to-end tests for auth flow."""

import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.auth.models import AuthStore, Provider, TokenSet
from wunderunner.auth.storage import AUTH_FILE, load_store, save_tokens


class TestAuthE2E:
    """End-to-end auth tests."""

    @pytest.mark.asyncio
    async def test_full_token_lifecycle(self, tmp_path):
        """Test save → load → refresh cycle."""
        auth_file = tmp_path / AUTH_FILE

        tokens = TokenSet(
            access_token="initial_access",
            refresh_token="initial_refresh",
            expires_at=int(time.time()) + 3600,
            token_type="Bearer",
        )

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            # Save
            await save_tokens(Provider.ANTHROPIC, tokens)

            # Load
            store = await load_store()
            assert store.anthropic is not None
            assert store.anthropic.access_token == "initial_access"

            # Update
            new_tokens = TokenSet(
                access_token="updated_access",
                refresh_token="updated_refresh",
                expires_at=int(time.time()) + 7200,
                token_type="Bearer",
            )
            await save_tokens(Provider.ANTHROPIC, new_tokens)

            # Verify update
            store = await load_store()
            assert store.anthropic.access_token == "updated_access"

    @pytest.mark.asyncio
    async def test_oauth_client_with_stored_tokens(self, tmp_path):
        """Test getting OAuth client with stored tokens."""
        auth_file = tmp_path / AUTH_FILE

        tokens = TokenSet(
            access_token="stored_access_token",
            refresh_token="stored_refresh",
            expires_at=int(time.time()) + 3600,
            token_type="Bearer",
        )

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            await save_tokens(Provider.ANTHROPIC, tokens)

            # Get client using the same patched path
            from wunderunner.auth.client import get_anthropic_client
            client = await get_anthropic_client()

            assert client is not None
            assert client.headers.get("authorization") == "Bearer stored_access_token"
