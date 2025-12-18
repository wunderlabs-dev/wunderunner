# OAuth Authentication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add OAuth authentication for Anthropic Claude Pro/Max subscriptions with API key fallback; OpenAI remains API key only.

**Architecture:** PKCE OAuth flow with localhost callback server. Tokens stored in `~/.local/share/wunderunner/auth.json`. Custom httpx client injects Bearer tokens into Pydantic AI providers. Priority: OAuth > env var API key > error.

**Tech Stack:** httpx (async HTTP), aiofiles (async file I/O), webbrowser (open browser), aiohttp (callback server), Rich (CLI prompts/tables)

---

## Task 1: Auth Exceptions

**Files:**
- Modify: `src/wunderunner/exceptions.py`
- Create: `tests/test_auth_exceptions.py`

**Step 1: Write the failing test**

Create `tests/test_auth_exceptions.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_exceptions.py -v`
Expected: FAIL with ImportError (exceptions not defined)

**Step 3: Write minimal implementation**

Add to `src/wunderunner/exceptions.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_exceptions.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/exceptions.py tests/test_auth_exceptions.py
git commit -m "feat(auth): add auth exception hierarchy"
```

---

## Task 2: Auth Models (Token Storage Schema)

**Files:**
- Create: `src/wunderunner/auth/__init__.py`
- Create: `src/wunderunner/auth/models.py`
- Create: `tests/test_auth_models.py`

**Step 1: Write the failing test**

Create `tests/test_auth_models.py`:

```python
"""Tests for auth models."""

import time

import pytest

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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_models.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

Create `src/wunderunner/auth/__init__.py`:

```python
"""Authentication module for wunderunner."""

from wunderunner.auth.models import AuthStore, Provider, TokenSet

__all__ = ["AuthStore", "Provider", "TokenSet"]
```

Create `src/wunderunner/auth/models.py`:

```python
"""Authentication data models."""

import time
from enum import Enum

from pydantic import BaseModel


class Provider(str, Enum):
    """Supported authentication providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class TokenSet(BaseModel):
    """OAuth token set for a provider."""

    access_token: str
    refresh_token: str
    expires_at: int
    token_type: str = "Bearer"

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired or expiring soon.

        Args:
            buffer_seconds: Consider expired if within this many seconds of expiry.

        Returns:
            True if token is expired or expiring within buffer.
        """
        return time.time() >= (self.expires_at - buffer_seconds)


class AuthStore(BaseModel):
    """Storage model for all provider tokens."""

    anthropic: TokenSet | None = None
    openai: TokenSet | None = None

    def get_tokens(self, provider: Provider) -> TokenSet | None:
        """Get tokens for a provider."""
        if provider == Provider.ANTHROPIC:
            return self.anthropic
        elif provider == Provider.OPENAI:
            return self.openai
        return None

    def set_tokens(self, provider: Provider, tokens: TokenSet) -> None:
        """Set tokens for a provider."""
        if provider == Provider.ANTHROPIC:
            self.anthropic = tokens
        elif provider == Provider.OPENAI:
            self.openai = tokens

    def clear_tokens(self, provider: Provider) -> None:
        """Clear tokens for a provider."""
        if provider == Provider.ANTHROPIC:
            self.anthropic = None
        elif provider == Provider.OPENAI:
            self.openai = None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_models.py -v`
Expected: PASS (14 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/auth/ tests/test_auth_models.py
git commit -m "feat(auth): add token storage models"
```

---

## Task 3: Auth Storage (File Persistence)

**Files:**
- Create: `src/wunderunner/auth/storage.py`
- Create: `tests/test_auth_storage.py`

**Step 1: Write the failing test**

Create `tests/test_auth_storage.py`:

```python
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
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.home", return_value=Path("/home/user")):
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_storage.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `src/wunderunner/auth/storage.py`:

```python
"""Token storage for OAuth credentials."""

import logging
import os
from pathlib import Path

import aiofiles
from pydantic import ValidationError

from wunderunner.auth.models import AuthStore, Provider, TokenSet

logger = logging.getLogger(__name__)

AUTH_FILE = "auth.json"


def _get_auth_path() -> Path:
    """Get the path to the auth storage file.

    Uses XDG_DATA_HOME if set, otherwise ~/.local/share/wunderunner/auth.json
    """
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        base = Path(xdg_data)
    else:
        base = Path.home() / ".local" / "share"
    return base / "wunderunner" / AUTH_FILE


async def load_store() -> AuthStore:
    """Load auth store from disk. Returns empty store if not found."""
    auth_path = _get_auth_path()

    if not auth_path.exists():
        return AuthStore()

    try:
        async with aiofiles.open(auth_path) as f:
            content = await f.read()
        return AuthStore.model_validate_json(content)
    except (ValidationError, OSError, ValueError) as e:
        logger.warning("Failed to load auth store from %s: %s", auth_path, e)
        return AuthStore()


async def save_store(store: AuthStore) -> None:
    """Save auth store to disk with secure permissions."""
    auth_path = _get_auth_path()
    auth_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Write to temp file first for atomic operation
    temp_path = auth_path.with_suffix(".tmp")
    async with aiofiles.open(temp_path, "w") as f:
        await f.write(store.model_dump_json(indent=2))

    # Set restrictive permissions before rename
    temp_path.chmod(0o600)
    temp_path.rename(auth_path)


async def save_tokens(provider: Provider, tokens: TokenSet) -> None:
    """Save tokens for a specific provider, preserving others."""
    store = await load_store()
    store.set_tokens(provider, tokens)
    await save_store(store)


async def clear_tokens(provider: Provider) -> None:
    """Clear tokens for a specific provider, preserving others."""
    store = await load_store()
    store.clear_tokens(provider)
    await save_store(store)
```

Update `src/wunderunner/auth/__init__.py`:

```python
"""Authentication module for wunderunner."""

from wunderunner.auth.models import AuthStore, Provider, TokenSet
from wunderunner.auth.storage import clear_tokens, load_store, save_store, save_tokens

__all__ = [
    "AuthStore",
    "Provider",
    "TokenSet",
    "clear_tokens",
    "load_store",
    "save_store",
    "save_tokens",
]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_storage.py -v`
Expected: PASS (12 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/auth/ tests/test_auth_storage.py
git commit -m "feat(auth): add token storage persistence"
```

---

## Task 4: Anthropic OAuth Provider Constants

**Files:**
- Create: `src/wunderunner/auth/providers/__init__.py`
- Create: `src/wunderunner/auth/providers/anthropic.py`
- Create: `tests/test_auth_provider_anthropic.py`

**Step 1: Write the failing test**

Create `tests/test_auth_provider_anthropic.py`:

```python
"""Tests for Anthropic OAuth provider."""

import pytest

from wunderunner.auth.providers.anthropic import AnthropicOAuth


class TestAnthropicOAuthConstants:
    """Test AnthropicOAuth constants."""

    def test_client_id(self):
        """CLIENT_ID is the correct Anthropic OAuth client."""
        assert AnthropicOAuth.CLIENT_ID == "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

    def test_auth_url(self):
        """AUTH_URL points to Anthropic console."""
        assert "console.anthropic.com" in AnthropicOAuth.AUTH_URL
        assert "oauth/authorize" in AnthropicOAuth.AUTH_URL

    def test_token_url(self):
        """TOKEN_URL points to Anthropic token endpoint."""
        assert "console.anthropic.com" in AnthropicOAuth.TOKEN_URL
        assert "oauth/token" in AnthropicOAuth.TOKEN_URL

    def test_redirect_uri(self):
        """REDIRECT_URI is the Anthropic callback."""
        assert "console.anthropic.com" in AnthropicOAuth.REDIRECT_URI
        assert "callback" in AnthropicOAuth.REDIRECT_URI

    def test_scopes(self):
        """SCOPES includes required permissions."""
        assert "user:inference" in AnthropicOAuth.SCOPES

    def test_beta_header(self):
        """BETA_HEADER is the OAuth beta flag."""
        assert "oauth" in AnthropicOAuth.BETA_HEADER
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_provider_anthropic.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `src/wunderunner/auth/providers/__init__.py`:

```python
"""OAuth provider implementations."""

from wunderunner.auth.providers.anthropic import AnthropicOAuth

__all__ = ["AnthropicOAuth"]
```

Create `src/wunderunner/auth/providers/anthropic.py`:

```python
"""Anthropic OAuth provider configuration."""


class AnthropicOAuth:
    """Anthropic OAuth configuration constants."""

    CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    AUTH_URL = "https://console.anthropic.com/oauth/authorize"
    TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
    REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
    SCOPES = "org:create_api_key user:profile user:inference"
    BETA_HEADER = "oauth-2025-04-20"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_provider_anthropic.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/auth/providers/ tests/test_auth_provider_anthropic.py
git commit -m "feat(auth): add Anthropic OAuth provider constants"
```

---

## Task 5: PKCE Utilities

**Files:**
- Create: `src/wunderunner/auth/pkce.py`
- Create: `tests/test_auth_pkce.py`

**Step 1: Write the failing test**

Create `tests/test_auth_pkce.py`:

```python
"""Tests for PKCE utilities."""

import base64
import hashlib
import re

import pytest

from wunderunner.auth.pkce import generate_pkce, generate_state


class TestGeneratePkce:
    """Test generate_pkce function."""

    def test_returns_verifier_and_challenge(self):
        """generate_pkce returns verifier and challenge tuple."""
        verifier, challenge = generate_pkce()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_length(self):
        """Verifier is between 43-128 characters (RFC 7636)."""
        verifier, _ = generate_pkce()
        assert 43 <= len(verifier) <= 128

    def test_verifier_uses_valid_characters(self):
        """Verifier uses only URL-safe base64 characters."""
        verifier, _ = generate_pkce()
        # RFC 7636: ALPHA / DIGIT / "-" / "." / "_" / "~"
        assert re.match(r"^[A-Za-z0-9\-._~]+$", verifier)

    def test_challenge_is_sha256_of_verifier(self):
        """Challenge is base64url(SHA256(verifier))."""
        verifier, challenge = generate_pkce()
        # Compute expected challenge
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_generates_unique_values(self):
        """Each call generates unique verifier/challenge."""
        v1, c1 = generate_pkce()
        v2, c2 = generate_pkce()
        assert v1 != v2
        assert c1 != c2


class TestGenerateState:
    """Test generate_state function."""

    def test_returns_string(self):
        """generate_state returns a string."""
        state = generate_state()
        assert isinstance(state, str)

    def test_reasonable_length(self):
        """State is a reasonable length for security."""
        state = generate_state()
        assert len(state) >= 16

    def test_generates_unique_values(self):
        """Each call generates unique state."""
        s1 = generate_state()
        s2 = generate_state()
        assert s1 != s2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_pkce.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `src/wunderunner/auth/pkce.py`:

```python
"""PKCE (Proof Key for Code Exchange) utilities for OAuth 2.0."""

import base64
import hashlib
import secrets


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge.

    Returns:
        Tuple of (code_verifier, code_challenge).
        Challenge is base64url(SHA256(verifier)) per RFC 7636.
    """
    # Generate 32 bytes of randomness -> 43 chars in base64url
    verifier_bytes = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")

    # SHA256 hash of verifier, base64url encoded
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    return verifier, challenge


def generate_state() -> str:
    """Generate a random state parameter for CSRF protection.

    Returns:
        URL-safe random string.
    """
    return secrets.token_urlsafe(16)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_pkce.py -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/auth/pkce.py tests/test_auth_pkce.py
git commit -m "feat(auth): add PKCE utilities"
```

---

## Task 6: OAuth Callback Server

**Files:**
- Create: `src/wunderunner/auth/server.py`
- Create: `src/wunderunner/auth/pages/success.html`
- Create: `tests/test_auth_server.py`

**Step 1: Write the failing test**

Create `tests/test_auth_server.py`:

```python
"""Tests for OAuth callback server."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from wunderunner.auth.server import CallbackServer, get_success_page


class TestGetSuccessPage:
    """Test success page loading."""

    def test_returns_html(self):
        """get_success_page returns HTML content."""
        html = get_success_page()
        assert "<html" in html.lower()
        assert "</html>" in html.lower()

    def test_includes_success_message(self):
        """Success page includes authentication success message."""
        html = get_success_page()
        assert "authenticated" in html.lower() or "success" in html.lower()


class TestCallbackServer:
    """Test CallbackServer class."""

    @pytest.mark.asyncio
    async def test_server_binds_to_localhost(self):
        """Server binds to localhost."""
        server = CallbackServer(port=0)  # Random available port
        await server.start()
        try:
            assert server.host == "127.0.0.1"
            assert server.port > 0
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_callback_url_format(self):
        """callback_url returns correct format."""
        server = CallbackServer(port=0)
        await server.start()
        try:
            url = server.callback_url
            assert url.startswith("http://127.0.0.1:")
            assert "/callback" in url
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wait_for_callback_returns_code(self):
        """wait_for_callback returns authorization code."""
        server = CallbackServer(port=0)
        await server.start()

        async def simulate_callback():
            await asyncio.sleep(0.1)
            # Simulate browser callback
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"{server.callback_url}?code=test_auth_code&state=test_state"
                async with session.get(url) as resp:
                    assert resp.status == 200

        try:
            callback_task = asyncio.create_task(simulate_callback())
            code = await asyncio.wait_for(
                server.wait_for_callback(expected_state="test_state"),
                timeout=5.0,
            )
            await callback_task
            assert code == "test_auth_code"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wait_for_callback_validates_state(self):
        """wait_for_callback raises on state mismatch."""
        server = CallbackServer(port=0)
        await server.start()

        async def simulate_callback():
            await asyncio.sleep(0.1)
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"{server.callback_url}?code=test_code&state=wrong_state"
                async with session.get(url) as resp:
                    pass  # Server returns error page

        try:
            callback_task = asyncio.create_task(simulate_callback())
            with pytest.raises(Exception):  # OAuthCallbackError or timeout
                await asyncio.wait_for(
                    server.wait_for_callback(expected_state="correct_state"),
                    timeout=2.0,
                )
            await callback_task
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wait_for_callback_timeout(self):
        """wait_for_callback raises on timeout."""
        server = CallbackServer(port=0)
        await server.start()

        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    server.wait_for_callback(expected_state="test"),
                    timeout=0.1,
                )
        finally:
            await server.stop()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_server.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `src/wunderunner/auth/pages/success.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>wunderunner - Authenticated</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            background-color: #0d1117;
            color: #00ff00;
            font-family: 'Courier New', Courier, monospace;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            text-align: center;
            padding: 2rem;
            border: 1px solid #30363d;
            border-radius: 8px;
            background-color: #161b22;
            max-width: 500px;
        }
        .logo {
            color: #58a6ff;
            font-size: 0.7rem;
            line-height: 1.2;
            margin-bottom: 1.5rem;
            white-space: pre;
        }
        .success {
            color: #3fb950;
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }
        .message {
            color: #8b949e;
            font-size: 1rem;
        }
        .checkmark {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <pre class="logo">
██╗    ██╗██╗  ██╗██████╗
██║    ██║╚██╗██╔╝██╔══██╗
██║ █╗ ██║ ╚███╔╝ ██████╔╝
██║███╗██║ ██╔██╗ ██╔══██╗
╚███╔███╔╝██╔╝ ██╗██║  ██║
 ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝
        </pre>
        <div class="checkmark">✓</div>
        <div class="success">Successfully authenticated</div>
        <div class="message">You can close this tab and return to the terminal.</div>
    </div>
    <script>
        // Auto-close after 3 seconds
        setTimeout(() => window.close(), 3000);
    </script>
</body>
</html>
```

Create `src/wunderunner/auth/server.py`:

```python
"""OAuth callback server for handling browser redirects."""

import asyncio
import logging
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from aiohttp import web

from wunderunner.exceptions import OAuthCallbackError

logger = logging.getLogger(__name__)


def get_success_page() -> str:
    """Load the success HTML page."""
    return files("wunderunner.auth.pages").joinpath("success.html").read_text()


def _get_error_page(message: str) -> str:
    """Generate error HTML page."""
    return f"""<!DOCTYPE html>
<html>
<head><title>Authentication Error</title></head>
<body style="background:#0d1117;color:#f85149;font-family:monospace;padding:2rem;">
<h1>Authentication Error</h1>
<p>{message}</p>
</body>
</html>"""


class CallbackServer:
    """Temporary HTTP server to receive OAuth callbacks."""

    def __init__(self, port: int = 0):
        """Initialize callback server.

        Args:
            port: Port to bind to. 0 = random available port.
        """
        self.host = "127.0.0.1"
        self._requested_port = port
        self.port = 0
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._code_future: asyncio.Future[str] | None = None
        self._expected_state: str | None = None

    @property
    def callback_url(self) -> str:
        """Get the callback URL for this server."""
        return f"http://{self.host}:{self.port}/callback"

    async def start(self) -> None:
        """Start the callback server."""
        self._app = web.Application()
        self._app.router.add_get("/callback", self._handle_callback)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.host, self._requested_port)
        await self._site.start()

        # Get actual port if we requested 0
        assert self._site._server is not None
        sockets = self._site._server.sockets
        if sockets:
            self.port = sockets[0].getsockname()[1]

        logger.debug("Callback server started on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the callback server."""
        if self._runner:
            await self._runner.cleanup()
        self._app = None
        self._runner = None
        self._site = None

    async def wait_for_callback(self, expected_state: str) -> str:
        """Wait for OAuth callback and return authorization code.

        Args:
            expected_state: Expected state parameter for CSRF validation.

        Returns:
            Authorization code from callback.

        Raises:
            OAuthCallbackError: If state doesn't match or callback fails.
        """
        self._expected_state = expected_state
        self._code_future = asyncio.get_event_loop().create_future()

        try:
            return await self._code_future
        finally:
            self._code_future = None
            self._expected_state = None

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback request."""
        query = parse_qs(request.query_string)

        # Check for error response
        if "error" in query:
            error = query.get("error", ["unknown"])[0]
            description = query.get("error_description", [""])[0]
            message = f"OAuth error: {error} - {description}"
            logger.error(message)
            if self._code_future and not self._code_future.done():
                self._code_future.set_exception(OAuthCallbackError(message))
            return web.Response(
                text=_get_error_page(message),
                content_type="text/html",
            )

        # Validate state
        state = query.get("state", [None])[0]
        if state != self._expected_state:
            message = "State mismatch - possible CSRF attack"
            logger.error(message)
            if self._code_future and not self._code_future.done():
                self._code_future.set_exception(OAuthCallbackError(message))
            return web.Response(
                text=_get_error_page(message),
                content_type="text/html",
            )

        # Extract code
        code = query.get("code", [None])[0]
        if not code:
            message = "No authorization code in callback"
            logger.error(message)
            if self._code_future and not self._code_future.done():
                self._code_future.set_exception(OAuthCallbackError(message))
            return web.Response(
                text=_get_error_page(message),
                content_type="text/html",
            )

        # Success
        logger.debug("Received authorization code")
        if self._code_future and not self._code_future.done():
            self._code_future.set_result(code)

        return web.Response(
            text=get_success_page(),
            content_type="text/html",
        )
```

Create empty `src/wunderunner/auth/pages/__init__.py`:

```python
"""Auth pages package."""
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_server.py -v`
Expected: PASS (6 tests)

**Step 5: Check if aiohttp is installed**

Run: `uv pip show aiohttp || uv add aiohttp`

**Step 6: Commit**

```bash
git add src/wunderunner/auth/ tests/test_auth_server.py
git commit -m "feat(auth): add OAuth callback server with success page"
```

---

## Task 7: Anthropic OAuth Flow (Token Exchange)

**Files:**
- Modify: `src/wunderunner/auth/providers/anthropic.py`
- Create: `tests/test_auth_anthropic_flow.py`

**Step 1: Write the failing test**

Create `tests/test_auth_anthropic_flow.py`:

```python
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
            state="state123",
            redirect_uri="http://localhost/callback",
        )
        assert f"client_id={AnthropicOAuth.CLIENT_ID}" in url

    def test_includes_code_challenge(self):
        """Auth URL includes PKCE code challenge."""
        url = build_auth_url(
            code_challenge="test_challenge",
            state="state123",
            redirect_uri="http://localhost/callback",
        )
        assert "code_challenge=test_challenge" in url
        assert "code_challenge_method=S256" in url

    def test_includes_state(self):
        """Auth URL includes state parameter."""
        url = build_auth_url(
            code_challenge="challenge",
            state="my_state_value",
            redirect_uri="http://localhost/callback",
        )
        assert "state=my_state_value" in url

    def test_includes_redirect_uri(self):
        """Auth URL includes redirect URI."""
        url = build_auth_url(
            code_challenge="challenge",
            state="state",
            redirect_uri="http://localhost:8080/callback",
        )
        assert "redirect_uri=" in url

    def test_response_type_is_code(self):
        """Auth URL requests authorization code."""
        url = build_auth_url(
            code_challenge="challenge",
            state="state",
            redirect_uri="http://localhost/callback",
        )
        assert "response_type=code" in url


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
                redirect_uri="http://localhost/callback",
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
                redirect_uri="http://localhost/callback",
            )
            after = int(time.time())

            # expires_at should be now + expires_in
            assert before + 3600 <= tokens.expires_at <= after + 3600


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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_anthropic_flow.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Update `src/wunderunner/auth/providers/anthropic.py`:

```python
"""Anthropic OAuth provider configuration and flow."""

import time
from urllib.parse import urlencode

import httpx

from wunderunner.auth.models import TokenSet
from wunderunner.exceptions import TokenRefreshError


class AnthropicOAuth:
    """Anthropic OAuth configuration constants."""

    CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    AUTH_URL = "https://console.anthropic.com/oauth/authorize"
    TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
    REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
    SCOPES = "org:create_api_key user:profile user:inference"
    BETA_HEADER = "oauth-2025-04-20"


def build_auth_url(
    code_challenge: str,
    state: str,
    redirect_uri: str,
) -> str:
    """Build the OAuth authorization URL.

    Args:
        code_challenge: PKCE code challenge (S256).
        state: Random state for CSRF protection.
        redirect_uri: Where to redirect after auth.

    Returns:
        Full authorization URL to open in browser.
    """
    params = {
        "response_type": "code",
        "client_id": AnthropicOAuth.CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": AnthropicOAuth.SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{AnthropicOAuth.AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> TokenSet:
    """Exchange authorization code for access tokens.

    Args:
        code: Authorization code from OAuth callback.
        code_verifier: PKCE code verifier.
        redirect_uri: Must match the one used in auth request.

    Returns:
        TokenSet with access and refresh tokens.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            AnthropicOAuth.TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": AnthropicOAuth.CLIENT_ID,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        data = response.json()

    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=int(time.time()) + data["expires_in"],
        token_type=data.get("token_type", "Bearer"),
    )


async def refresh_access_token(refresh_token: str) -> TokenSet:
    """Refresh an expired access token.

    Args:
        refresh_token: Valid refresh token.

    Returns:
        New TokenSet with fresh access token.

    Raises:
        TokenRefreshError: If refresh fails.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                AnthropicOAuth.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": AnthropicOAuth.CLIENT_ID,
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            data = response.json()

        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=int(time.time()) + data["expires_in"],
            token_type=data.get("token_type", "Bearer"),
        )
    except httpx.HTTPStatusError as e:
        raise TokenRefreshError(f"Failed to refresh token: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_anthropic_flow.py -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/auth/providers/anthropic.py tests/test_auth_anthropic_flow.py
git commit -m "feat(auth): add Anthropic OAuth token exchange"
```

---

## Task 8: Auth Client Factory (httpx with OAuth)

**Files:**
- Create: `src/wunderunner/auth/client.py`
- Create: `tests/test_auth_client.py`

**Step 1: Write the failing test**

Create `tests/test_auth_client.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth_client.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `src/wunderunner/auth/client.py`:

```python
"""HTTP client factory with OAuth authentication."""

import logging

import httpx

from wunderunner.auth.models import Provider
from wunderunner.auth.providers.anthropic import AnthropicOAuth, refresh_access_token
from wunderunner.auth.storage import load_store, save_tokens
from wunderunner.exceptions import TokenRefreshError

logger = logging.getLogger(__name__)


async def get_anthropic_client() -> httpx.AsyncClient | None:
    """Get an httpx client configured for Anthropic OAuth.

    Priority: OAuth tokens (refresh if needed) → None (fall back to API key).

    Returns:
        Configured httpx.AsyncClient if OAuth tokens exist and are valid,
        None otherwise (caller should fall back to API key).
    """
    store = await load_store()
    tokens = store.get_tokens(Provider.ANTHROPIC)

    if tokens is None:
        return None

    # Refresh if expired or expiring soon
    if tokens.is_expired():
        logger.debug("Anthropic tokens expired, attempting refresh")
        try:
            tokens = await refresh_access_token(tokens.refresh_token)
            await save_tokens(Provider.ANTHROPIC, tokens)
            logger.debug("Anthropic tokens refreshed successfully")
        except TokenRefreshError as e:
            logger.warning("Failed to refresh Anthropic tokens: %s", e)
            return None

    # Build client with OAuth headers
    return httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {tokens.access_token}",
            "anthropic-beta": AnthropicOAuth.BETA_HEADER,
        }
    )
```

Update `src/wunderunner/auth/__init__.py`:

```python
"""Authentication module for wunderunner."""

from wunderunner.auth.client import get_anthropic_client
from wunderunner.auth.models import AuthStore, Provider, TokenSet
from wunderunner.auth.storage import clear_tokens, load_store, save_store, save_tokens

__all__ = [
    "AuthStore",
    "Provider",
    "TokenSet",
    "clear_tokens",
    "get_anthropic_client",
    "load_store",
    "save_store",
    "save_tokens",
]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth_client.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/auth/ tests/test_auth_client.py
git commit -m "feat(auth): add httpx client factory with OAuth"
```

---

## Task 9: CLI Auth Commands

**Files:**
- Create: `src/wunderunner/cli/auth.py`
- Modify: `src/wunderunner/cli/main.py`
- Create: `tests/test_cli_auth.py`

**Step 1: Write the failing test**

Create `tests/test_cli_auth.py`:

```python
"""Tests for CLI auth commands."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from wunderunner.cli.main import app


runner = CliRunner()


class TestAuthStatus:
    """Test wxr auth status command."""

    def test_shows_no_auth_when_empty(self):
        """Status shows no authentication when store is empty."""
        with patch("wunderunner.cli.auth.load_store", new_callable=AsyncMock) as mock_load:
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore()

            with patch("wunderunner.cli.auth.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = None
                mock_settings.return_value.openai_api_key = None

                result = runner.invoke(app, ["auth", "status"])

                assert result.exit_code == 0
                assert "not configured" in result.stdout.lower() or "none" in result.stdout.lower()

    def test_shows_oauth_when_tokens_exist(self):
        """Status shows OAuth when tokens are configured."""
        import time
        from wunderunner.auth.models import AuthStore, TokenSet

        tokens = TokenSet(
            access_token="access",
            refresh_token="refresh",
            expires_at=int(time.time()) + 3600,
            token_type="Bearer",
        )

        with patch("wunderunner.cli.auth.load_store", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = AuthStore(anthropic=tokens)

            with patch("wunderunner.cli.auth.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = None
                mock_settings.return_value.openai_api_key = None

                result = runner.invoke(app, ["auth", "status"])

                assert result.exit_code == 0
                assert "oauth" in result.stdout.lower()

    def test_shows_api_key_when_env_set(self):
        """Status shows API key when environment variable is set."""
        with patch("wunderunner.cli.auth.load_store", new_callable=AsyncMock) as mock_load:
            from wunderunner.auth.models import AuthStore
            mock_load.return_value = AuthStore()

            with patch("wunderunner.cli.auth.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = "sk-ant-xxx"
                mock_settings.return_value.openai_api_key = None

                result = runner.invoke(app, ["auth", "status"])

                assert result.exit_code == 0
                assert "api key" in result.stdout.lower() or "env" in result.stdout.lower()


class TestAuthLogout:
    """Test wxr auth logout command."""

    def test_logout_clears_tokens(self):
        """Logout clears tokens for selected provider."""
        with (
            patch("wunderunner.cli.auth.clear_tokens", new_callable=AsyncMock) as mock_clear,
            patch("wunderunner.cli.auth.Prompt.ask", return_value="1"),  # Select Anthropic
        ):
            result = runner.invoke(app, ["auth", "logout"])

            assert result.exit_code == 0
            mock_clear.assert_called_once()


class TestAuthLogin:
    """Test wxr auth login command."""

    def test_login_command_exists(self):
        """Login command is registered."""
        result = runner.invoke(app, ["auth", "login", "--help"])
        assert result.exit_code == 0
        assert "login" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_auth.py -v`
Expected: FAIL (no auth command registered)

**Step 3: Write minimal implementation**

Create `src/wunderunner/cli/auth.py`:

```python
"""CLI commands for authentication."""

import asyncio
import webbrowser
from datetime import datetime

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from wunderunner.auth.models import Provider
from wunderunner.auth.pkce import generate_pkce, generate_state
from wunderunner.auth.providers.anthropic import (
    AnthropicOAuth,
    build_auth_url,
    exchange_code_for_tokens,
)
from wunderunner.auth.server import CallbackServer
from wunderunner.auth.storage import clear_tokens, load_store, save_tokens
from wunderunner.exceptions import OAuthCallbackError
from wunderunner.settings import get_settings

auth_app = typer.Typer(name="auth", help="Manage authentication.")
console = Console()

OAUTH_TIMEOUT = 120  # seconds


@auth_app.command()
def status() -> None:
    """Show authentication status for all providers."""
    asyncio.run(_status_async())


async def _status_async() -> None:
    """Async implementation of status command."""
    store = await load_store()
    settings = get_settings()

    table = Table(title="Authentication Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Method", style="green")
    table.add_column("Status", style="yellow")

    # Anthropic
    anthropic_tokens = store.get_tokens(Provider.ANTHROPIC)
    if anthropic_tokens:
        if anthropic_tokens.is_expired():
            status_text = "Expired (run `wxr auth login`)"
        else:
            expires = datetime.fromtimestamp(anthropic_tokens.expires_at)
            status_text = f"Valid until {expires.strftime('%H:%M')}"
        table.add_row("Anthropic", "OAuth", status_text)
    elif settings.anthropic_api_key:
        table.add_row("Anthropic", "API Key (env)", "Configured")
    else:
        table.add_row("Anthropic", "-", "Not configured")

    # OpenAI
    if settings.openai_api_key:
        table.add_row("OpenAI", "API Key (env)", "Configured")
    else:
        table.add_row("OpenAI", "-", "Not configured")

    console.print(table)


@auth_app.command()
def login() -> None:
    """Authenticate with a provider."""
    console.print("\n[bold]Select provider:[/bold]")
    console.print("  [cyan]1[/cyan] Anthropic (OAuth - Claude Pro/Max subscription)")
    console.print("  [cyan]2[/cyan] Enter API key manually")

    choice = Prompt.ask("Choice", choices=["1", "2"], default="1")

    if choice == "1":
        asyncio.run(_login_anthropic_oauth())
    elif choice == "2":
        _login_api_key()


async def _login_anthropic_oauth() -> None:
    """Run Anthropic OAuth flow."""
    console.print("\n[dim]Starting OAuth flow...[/dim]")

    # Generate PKCE and state
    code_verifier, code_challenge = generate_pkce()
    state = generate_state()

    # Start callback server
    server = CallbackServer(port=0)
    await server.start()

    try:
        # Build auth URL (using Anthropic's redirect, not localhost)
        # The console will show the code which user pastes
        auth_url = build_auth_url(
            code_challenge=code_challenge,
            state=state,
            redirect_uri=AnthropicOAuth.REDIRECT_URI,
        )

        console.print(f"\n[dim]Opening browser for authentication...[/dim]")
        console.print(f"[dim]If browser doesn't open, visit:[/dim]")
        console.print(f"[link={auth_url}]{auth_url[:80]}...[/link]\n")

        webbrowser.open(auth_url)

        # For Anthropic, the redirect goes to their console which shows the code
        # User needs to paste the code
        console.print("[bold]After authenticating, paste the authorization code:[/bold]")
        code = Prompt.ask("Authorization code")

        if not code:
            console.print("[red]No code provided. Aborting.[/red]")
            return

        # Exchange code for tokens
        console.print("[dim]Exchanging code for tokens...[/dim]")
        tokens = await exchange_code_for_tokens(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=AnthropicOAuth.REDIRECT_URI,
        )

        # Save tokens
        await save_tokens(Provider.ANTHROPIC, tokens)
        console.print("\n[green bold]Successfully authenticated with Anthropic![/green bold]")

    except OAuthCallbackError as e:
        console.print(f"\n[red]Authentication failed: {e}[/red]")
    except Exception as e:
        console.print(f"\n[red]Error during authentication: {e}[/red]")
    finally:
        await server.stop()


def _login_api_key() -> None:
    """Manual API key entry."""
    console.print("\n[bold]Select provider for API key:[/bold]")
    console.print("  [cyan]1[/cyan] Anthropic")
    console.print("  [cyan]2[/cyan] OpenAI")

    choice = Prompt.ask("Choice", choices=["1", "2"])

    if choice == "1":
        console.print("\nSet the ANTHROPIC_API_KEY environment variable:")
        console.print("  [dim]export ANTHROPIC_API_KEY='sk-ant-...'[/dim]")
    else:
        console.print("\nSet the OPENAI_API_KEY environment variable:")
        console.print("  [dim]export OPENAI_API_KEY='sk-...'[/dim]")


@auth_app.command()
def logout() -> None:
    """Remove stored authentication."""
    console.print("\n[bold]Select provider to logout:[/bold]")
    console.print("  [cyan]1[/cyan] Anthropic")
    console.print("  [cyan]2[/cyan] All providers")

    choice = Prompt.ask("Choice", choices=["1", "2"], default="1")

    if choice == "1":
        asyncio.run(clear_tokens(Provider.ANTHROPIC))
        console.print("[green]Logged out of Anthropic[/green]")
    else:
        asyncio.run(clear_tokens(Provider.ANTHROPIC))
        console.print("[green]Logged out of all providers[/green]")
```

Update `src/wunderunner/cli/main.py` - add import and register auth_app:

After the existing imports, add:

```python
from wunderunner.cli.auth import auth_app
```

After the `app = typer.Typer(...)` line, add:

```python
app.add_typer(auth_app)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_auth.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/cli/ tests/test_cli_auth.py
git commit -m "feat(auth): add CLI auth commands (login/logout/status)"
```

---

## Task 10: Integrate OAuth with Settings

**Files:**
- Modify: `src/wunderunner/settings.py`
- Modify: `tests/test_settings.py`

**Step 1: Write the failing test**

Add to `tests/test_settings.py`:

```python
class TestCreateModelWithOAuth:
    """Test _create_model with OAuth integration."""

    @pytest.mark.asyncio
    async def test_uses_oauth_client_when_available(self):
        """_create_model uses OAuth client when tokens exist."""
        import time
        from unittest.mock import AsyncMock
        import httpx

        # Create a mock OAuth client
        mock_client = httpx.AsyncClient(
            headers={
                "Authorization": "Bearer oauth_token",
                "anthropic-beta": "oauth-2025-04-20",
            }
        )

        with (
            patch("wunderunner.settings.get_anthropic_client", new_callable=AsyncMock) as mock_get_client,
            patch("wunderunner.settings.get_settings") as mock_settings,
        ):
            mock_get_client.return_value = mock_client
            mock_settings.return_value.anthropic_api_key = None

            from wunderunner.settings import create_model_async
            model = await create_model_async("anthropic:claude-3-5-sonnet-20241022")

            mock_get_client.assert_called_once()
            # Model should be created (we can't easily verify the client was used)
            assert model is not None

    @pytest.mark.asyncio
    async def test_falls_back_to_api_key(self):
        """_create_model falls back to API key when no OAuth."""
        from unittest.mock import AsyncMock

        with (
            patch("wunderunner.settings.get_anthropic_client", new_callable=AsyncMock) as mock_get_client,
            patch("wunderunner.settings.get_settings") as mock_settings,
        ):
            mock_get_client.return_value = None  # No OAuth
            mock_settings.return_value.anthropic_api_key = "sk-ant-test"

            from wunderunner.settings import create_model_async
            model = await create_model_async("anthropic:claude-3-5-sonnet-20241022")

            assert model is not None

    @pytest.mark.asyncio
    async def test_raises_no_auth_error(self):
        """_create_model raises NoAuthError when no auth configured."""
        from unittest.mock import AsyncMock
        from wunderunner.exceptions import NoAuthError

        with (
            patch("wunderunner.settings.get_anthropic_client", new_callable=AsyncMock) as mock_get_client,
            patch("wunderunner.settings.get_settings") as mock_settings,
        ):
            mock_get_client.return_value = None
            mock_settings.return_value.anthropic_api_key = None

            from wunderunner.settings import create_model_async

            with pytest.raises(NoAuthError):
                await create_model_async("anthropic:claude-3-5-sonnet-20241022")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py::TestCreateModelWithOAuth -v`
Expected: FAIL with ImportError (create_model_async doesn't exist)

**Step 3: Write minimal implementation**

Update `src/wunderunner/settings.py` - add async model creation:

Add import at top:

```python
from wunderunner.auth.client import get_anthropic_client
from wunderunner.auth.models import Provider
from wunderunner.auth.providers.anthropic import AnthropicOAuth
from wunderunner.exceptions import NoAuthError
```

Add new async function:

```python
async def create_model_async(model_str: str):
    """Create a model instance with OAuth or API key authentication.

    Priority: OAuth tokens → API key → NoAuthError

    Args:
        model_str: Model string in format "provider:model_name"

    Returns:
        Configured model instance.

    Raises:
        NoAuthError: If no authentication is configured for the provider.
    """
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.anthropic import AnthropicProvider
    from pydantic_ai.providers.openai import OpenAIProvider

    settings = get_settings()
    provider, model_name = model_str.split(":", 1)

    if provider == Provider.ANTHROPIC.value:
        # Try OAuth first
        oauth_client = await get_anthropic_client()
        if oauth_client:
            return AnthropicModel(
                model_name,
                provider=AnthropicProvider(http_client=oauth_client),
            )
        # Fall back to API key
        if settings.anthropic_api_key:
            return AnthropicModel(
                model_name,
                provider=AnthropicProvider(api_key=settings.anthropic_api_key),
            )
        raise NoAuthError(Provider.ANTHROPIC.value)

    elif provider == Provider.OPENAI.value:
        # OpenAI: API key only
        if settings.openai_api_key:
            return OpenAIModel(
                model_name,
                provider=OpenAIProvider(api_key=settings.openai_api_key),
            )
        raise NoAuthError(Provider.OPENAI.value)

    else:
        raise ValueError(f"Unknown provider: {provider}")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py::TestCreateModelWithOAuth -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/wunderunner/settings.py tests/test_settings.py
git commit -m "feat(auth): integrate OAuth into model creation"
```

---

## Task 11: Update Existing Code to Use Async Model Creation

**Files:**
- Audit all files that call `_create_model` or `get_fallback_model`
- Update to use `create_model_async`

**Step 1: Find all usages**

Run: `grep -r "_create_model\|get_fallback_model" src/`

**Step 2: Update each usage**

For each file that uses these functions:
1. Change the function to async if not already
2. Replace `_create_model(...)` with `await create_model_async(...)`
3. Replace `get_fallback_model(...)` with `await create_model_async(...)`

**Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update codebase to use async OAuth model creation"
```

---

## Task 12: End-to-End Test

**Files:**
- Create: `tests/test_auth_e2e.py`

**Step 1: Write integration test**

Create `tests/test_auth_e2e.py`:

```python
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

        with patch("wunderunner.auth.client._get_auth_path", return_value=auth_file):
            with patch("wunderunner.auth.storage._get_auth_path", return_value=auth_file):
                from wunderunner.auth.client import get_anthropic_client
                client = await get_anthropic_client()

                assert client is not None
                assert client.headers.get("authorization") == "Bearer stored_access_token"
```

**Step 2: Run test**

Run: `uv run pytest tests/test_auth_e2e.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_auth_e2e.py
git commit -m "test: add auth end-to-end tests"
```

---

## Task 13: Final Cleanup and Documentation

**Step 1: Run linter**

Run: `make lint`
Fix any issues.

**Step 2: Run formatter**

Run: `make format`

**Step 3: Run full test suite**

Run: `make test`
Expected: All tests pass

**Step 4: Update __init__.py exports**

Ensure `src/wunderunner/auth/__init__.py` exports all public API.

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup for OAuth auth feature"
```

---

## Summary

**Total tasks:** 13
**New files:** 15
**Modified files:** 4
**New tests:** ~80

**Key components:**
1. Auth exceptions (Task 1)
2. Token models (Task 2)
3. File storage (Task 3)
4. Anthropic provider constants (Task 4)
5. PKCE utilities (Task 5)
6. Callback server + success page (Task 6)
7. Token exchange flow (Task 7)
8. HTTP client factory (Task 8)
9. CLI commands (Task 9)
10. Settings integration (Task 10)
11. Codebase updates (Task 11)
12. E2E tests (Task 12)
13. Cleanup (Task 13)
