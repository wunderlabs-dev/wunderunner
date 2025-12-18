"""Tests for PKCE utilities."""

import base64
import hashlib
import re

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
