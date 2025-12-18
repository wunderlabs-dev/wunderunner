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
