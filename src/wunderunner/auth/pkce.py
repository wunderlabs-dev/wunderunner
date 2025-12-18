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
