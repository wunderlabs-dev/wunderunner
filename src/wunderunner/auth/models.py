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
