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
