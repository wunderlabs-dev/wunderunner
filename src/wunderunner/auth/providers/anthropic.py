"""Anthropic OAuth provider configuration."""


class AnthropicOAuth:
    """Anthropic OAuth configuration constants."""

    CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    AUTH_URL = "https://console.anthropic.com/oauth/authorize"
    TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
    REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
    SCOPES = "org:create_api_key user:profile user:inference"
    BETA_HEADER = "oauth-2025-04-20"
