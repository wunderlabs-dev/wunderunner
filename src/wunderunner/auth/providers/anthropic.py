"""Anthropic OAuth provider configuration and flow."""

import time
from urllib.parse import urlencode

import httpx

from wunderunner.auth.models import TokenSet
from wunderunner.exceptions import TokenRefreshError


class AnthropicOAuth:
    """Anthropic OAuth configuration constants."""

    CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    # Use claude.ai for Max users (console.anthropic.com is for API console)
    AUTH_URL = "https://claude.ai/oauth/authorize"
    TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
    REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
    SCOPES = "org:create_api_key user:profile user:inference"
    BETA_HEADER = "oauth-2025-04-20"


def build_auth_url(
    code_challenge: str,
    code_verifier: str,
) -> str:
    """Build the OAuth authorization URL.

    Args:
        code_challenge: PKCE code challenge (S256).
        code_verifier: PKCE code verifier (used as state per OpenCode).

    Returns:
        Full authorization URL to open in browser.
    """
    params = {
        "code": "true",  # Required by Anthropic OAuth
        "client_id": AnthropicOAuth.CLIENT_ID,
        "response_type": "code",
        "redirect_uri": AnthropicOAuth.REDIRECT_URI,
        "scope": AnthropicOAuth.SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": code_verifier,  # OpenCode uses verifier as state
    }
    return f"{AnthropicOAuth.AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    code_verifier: str,
) -> TokenSet:
    """Exchange authorization code for access tokens.

    Args:
        code: Authorization code from OAuth callback (may include state after #).
        code_verifier: PKCE code verifier.

    Returns:
        TokenSet with access and refresh tokens.
    """
    # Code format from Anthropic: "code#state"
    parts = code.split("#")
    auth_code = parts[0]
    state = parts[1] if len(parts) > 1 else code_verifier

    async with httpx.AsyncClient() as client:
        response = await client.post(
            AnthropicOAuth.TOKEN_URL,
            headers={"Content-Type": "application/json"},
            json={
                "code": auth_code,
                "state": state,
                "grant_type": "authorization_code",
                "client_id": AnthropicOAuth.CLIENT_ID,
                "redirect_uri": AnthropicOAuth.REDIRECT_URI,
                "code_verifier": code_verifier,
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
