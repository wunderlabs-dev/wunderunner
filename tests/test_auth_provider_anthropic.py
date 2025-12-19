"""Tests for Anthropic OAuth provider."""


from wunderunner.auth.providers.anthropic import AnthropicOAuth


class TestAnthropicOAuthConstants:
    """Test AnthropicOAuth constants."""

    def test_client_id(self):
        """CLIENT_ID is the correct Anthropic OAuth client."""
        assert AnthropicOAuth.CLIENT_ID == "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

    def test_auth_url(self):
        """AUTH_URL points to Claude.ai for Max users."""
        assert "claude.ai" in AnthropicOAuth.AUTH_URL
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
