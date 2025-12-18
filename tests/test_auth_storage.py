"""Tests for auth storage."""

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from wunderunner.auth.models import AuthStore, Provider, TokenSet
from wunderunner.auth.storage import (
    AUTH_FILE,
    _get_auth_path,
    clear_tokens,
    load_store,
    save_store,
    save_tokens,
)


class TestGetAuthPath:
    """Test _get_auth_path helper."""

    def test_returns_xdg_path(self):
        """_get_auth_path returns XDG data home path."""
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/custom/data"}, clear=False):
            path = _get_auth_path()
            assert path == Path("/custom/data/wunderunner") / AUTH_FILE

    def test_uses_default_when_no_xdg(self):
        """_get_auth_path uses ~/.local/share when XDG_DATA_HOME not set."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("pathlib.Path.home", return_value=Path("/home/user")),
        ):
            path = _get_auth_path()
            assert path == Path("/home/user/.local/share/wunderunner") / AUTH_FILE


class TestLoadStore:
    """Test load_store function."""

    @pytest.mark.asyncio
    async def test_missing_file_returns_empty_store(self, tmp_path):
        """load_store returns empty AuthStore if file doesn't exist."""
        with patch("wunderunner.auth.storage._get_auth_path", return_value=tmp_path / AUTH_FILE):
            store = await load_store()
            assert isinstance(store, AuthStore)
            assert store.anthropic is None
            assert store.openai is None

    @pytest.mark.asyncio
    async def test_loads_existing_store(self, tmp_path):
        """load_store loads store from existing file."""
        auth_file = tmp_path / AUTH_FILE
        auth_file.parent.mkdir(parents=True, exist_ok=True)

        store = AuthStore(
            anthropic=TokenSet(
                access_token="access",
                refresh_token="refresh",
                expires_at=1234567890,
                token_type="Bearer",
            )
        )
        auth_file.write_text(store.model_dump_json())

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            loaded = await load_store()
            assert loaded.anthropic is not None
            assert loaded.anthropic.access_token == "access"

    @pytest.mark.asyncio
    async def test_corrupt_file_returns_empty_store(self, tmp_path):
        """load_store returns empty store if file is corrupt."""
        auth_file = tmp_path / AUTH_FILE
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text("invalid json {{{")

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            store = await load_store()
            assert isinstance(store, AuthStore)
            assert store.anthropic is None


class TestSaveStore:
    """Test save_store function."""

    @pytest.mark.asyncio
    async def test_creates_directory_if_missing(self, tmp_path):
        """save_store creates parent directory if it doesn't exist."""
        auth_file = tmp_path / "subdir" / AUTH_FILE

        store = AuthStore()

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            await save_store(store)
            assert auth_file.exists()

    @pytest.mark.asyncio
    async def test_sets_file_permissions(self, tmp_path):
        """save_store sets restrictive file permissions."""
        auth_file = tmp_path / AUTH_FILE

        store = AuthStore()

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            await save_store(store)
            mode = auth_file.stat().st_mode
            # Check for 0600 permissions (owner read/write only)
            assert stat.S_IMODE(mode) == 0o600

    @pytest.mark.asyncio
    async def test_saves_store_as_json(self, tmp_path):
        """save_store writes JSON representation."""
        auth_file = tmp_path / AUTH_FILE

        store = AuthStore(
            anthropic=TokenSet(
                access_token="test_access",
                refresh_token="test_refresh",
                expires_at=9999999999,
                token_type="Bearer",
            )
        )

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            await save_store(store)
            content = json.loads(auth_file.read_text())
            assert content["anthropic"]["access_token"] == "test_access"


class TestSaveTokens:
    """Test save_tokens function."""

    @pytest.mark.asyncio
    async def test_saves_tokens_for_provider(self, tmp_path):
        """save_tokens adds tokens for provider."""
        auth_file = tmp_path / AUTH_FILE

        tokens = TokenSet(
            access_token="new_access",
            refresh_token="new_refresh",
            expires_at=9999999999,
            token_type="Bearer",
        )

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            await save_tokens(Provider.ANTHROPIC, tokens)
            store = await load_store()
            assert store.anthropic is not None
            assert store.anthropic.access_token == "new_access"

    @pytest.mark.asyncio
    async def test_preserves_other_providers(self, tmp_path):
        """save_tokens preserves tokens for other providers."""
        auth_file = tmp_path / AUTH_FILE
        auth_file.parent.mkdir(parents=True, exist_ok=True)

        # Pre-existing OpenAI tokens
        existing = AuthStore(
            openai=TokenSet(
                access_token="openai_access",
                refresh_token="openai_refresh",
                expires_at=8888888888,
                token_type="Bearer",
            )
        )
        auth_file.write_text(existing.model_dump_json())

        # Add Anthropic tokens
        tokens = TokenSet(
            access_token="anthropic_access",
            refresh_token="anthropic_refresh",
            expires_at=9999999999,
            token_type="Bearer",
        )

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            await save_tokens(Provider.ANTHROPIC, tokens)
            store = await load_store()
            assert store.anthropic is not None
            assert store.openai is not None
            assert store.openai.access_token == "openai_access"


class TestClearTokens:
    """Test clear_tokens function."""

    @pytest.mark.asyncio
    async def test_clears_tokens_for_provider(self, tmp_path):
        """clear_tokens removes tokens for provider."""
        auth_file = tmp_path / AUTH_FILE
        auth_file.parent.mkdir(parents=True, exist_ok=True)

        existing = AuthStore(
            anthropic=TokenSet(
                access_token="access",
                refresh_token="refresh",
                expires_at=9999999999,
                token_type="Bearer",
            )
        )
        auth_file.write_text(existing.model_dump_json())

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            await clear_tokens(Provider.ANTHROPIC)
            store = await load_store()
            assert store.anthropic is None

    @pytest.mark.asyncio
    async def test_preserves_other_providers(self, tmp_path):
        """clear_tokens preserves tokens for other providers."""
        auth_file = tmp_path / AUTH_FILE
        auth_file.parent.mkdir(parents=True, exist_ok=True)

        existing = AuthStore(
            anthropic=TokenSet(
                access_token="anthropic",
                refresh_token="refresh",
                expires_at=9999999999,
                token_type="Bearer",
            ),
            openai=TokenSet(
                access_token="openai",
                refresh_token="refresh",
                expires_at=8888888888,
                token_type="Bearer",
            ),
        )
        auth_file.write_text(existing.model_dump_json())

        with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
            await clear_tokens(Provider.ANTHROPIC)
            store = await load_store()
            assert store.anthropic is None
            assert store.openai is not None
