"""Tests for auth models."""

import time

from wunderunner.auth.models import AuthStore, Provider, TokenSet


class TestProvider:
    """Test Provider enum."""

    def test_anthropic_provider(self):
        """Provider has anthropic value."""
        assert Provider.ANTHROPIC.value == "anthropic"

    def test_openai_provider(self):
        """Provider has openai value."""
        assert Provider.OPENAI.value == "openai"


class TestTokenSet:
    """Test TokenSet model."""

    def test_create_token_set(self):
        """TokenSet stores token data."""
        ts = TokenSet(
            access_token="access123",
            refresh_token="refresh456",
            expires_at=1234567890,
            token_type="Bearer",
        )
        assert ts.access_token == "access123"
        assert ts.refresh_token == "refresh456"
        assert ts.expires_at == 1234567890
        assert ts.token_type == "Bearer"

    def test_is_expired_when_past(self):
        """is_expired returns True when token is past expiry."""
        ts = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=int(time.time()) - 100,  # 100 seconds ago
            token_type="Bearer",
        )
        assert ts.is_expired() is True

    def test_is_expired_when_future(self):
        """is_expired returns False when token is valid."""
        ts = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=int(time.time()) + 3600,  # 1 hour from now
            token_type="Bearer",
        )
        assert ts.is_expired() is False

    def test_is_expired_with_buffer(self):
        """is_expired respects buffer_seconds."""
        ts = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=int(time.time()) + 60,  # 60 seconds from now
            token_type="Bearer",
        )
        # With 300s buffer (default), should be considered expired
        assert ts.is_expired(buffer_seconds=300) is True
        # With 30s buffer, should not be expired
        assert ts.is_expired(buffer_seconds=30) is False


class TestAuthStore:
    """Test AuthStore model."""

    def test_empty_auth_store(self):
        """AuthStore starts empty."""
        store = AuthStore()
        assert store.anthropic is None
        assert store.openai is None

    def test_auth_store_with_tokens(self):
        """AuthStore holds provider tokens."""
        ts = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=1234567890,
            token_type="Bearer",
        )
        store = AuthStore(anthropic=ts)
        assert store.anthropic is not None
        assert store.anthropic.access_token == "access"

    def test_get_tokens_existing(self):
        """get_tokens returns tokens for provider."""
        ts = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=1234567890,
            token_type="Bearer",
        )
        store = AuthStore(anthropic=ts)
        assert store.get_tokens(Provider.ANTHROPIC) == ts

    def test_get_tokens_missing(self):
        """get_tokens returns None for missing provider."""
        store = AuthStore()
        assert store.get_tokens(Provider.ANTHROPIC) is None

    def test_set_tokens(self):
        """set_tokens stores tokens for provider."""
        ts = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=1234567890,
            token_type="Bearer",
        )
        store = AuthStore()
        store.set_tokens(Provider.ANTHROPIC, ts)
        assert store.anthropic == ts

    def test_clear_tokens(self):
        """clear_tokens removes tokens for provider."""
        ts = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=1234567890,
            token_type="Bearer",
        )
        store = AuthStore(anthropic=ts)
        store.clear_tokens(Provider.ANTHROPIC)
        assert store.anthropic is None
