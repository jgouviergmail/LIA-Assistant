"""
Unit tests for security utilities (passwords, encryption, OAuth).

JWT tests removed - authentication now uses BFF Pattern with session-based auth.
"""

import pytest

from src.core.security import (
    # JWT functions removed (BFF Pattern migration v0.3.0)
    decrypt_data,
    encrypt_data,
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
    get_password_hash,
    verify_password,
    verify_state_token,
)


@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password(self):
        """Test password hashing."""
        password = "SecurePass123!!"
        hashed = get_password_hash(password)

        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_verify_password_success(self):
        """Test password verification with correct password."""
        password = "SecurePass123!!"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_failure(self):
        """Test password verification with wrong password."""
        password = "SecurePass123!!"
        wrong_password = "WrongPassword456!"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_hash_different_passwords_produce_different_hashes(self):
        """Test that hashing the same password twice produces different hashes."""
        password = "SecurePass123!!"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2  # bcrypt uses random salt

    def test_empty_password_raises_error(self):
        """Test that empty password raises an error."""
        with pytest.raises(ValueError, match="Password cannot be empty"):
            get_password_hash("")


# ============================================================================
# REMOVED JWT TOKEN TESTS (BFF Pattern Migration)
# ============================================================================
# The following test classes were removed as part of BFF Pattern migration:
#
# - TestJWTTokens: Tests for create_access_token(), create_refresh_token()
# - TestTokenPayloads: Tests for JWT payload structure validation
#
# JWT authentication has been replaced with session-based authentication:
# - Session storage: Redis-backed sessions (see infrastructure/cache/session_store.py)
# - HTTP-only cookies: Secure cookie-based auth (see core/session_dependencies.py)
# - Session tests: See tests/integration/test_session_auth.py
#
# Token tests for email verification and password reset remain below.
# ============================================================================


@pytest.mark.unit
@pytest.mark.security
class TestEncryption:
    """Test data encryption and decryption."""

    def test_encrypt_data(self):
        """Test data encryption."""
        plaintext = "sensitive-api-key-12345"
        encrypted = encrypt_data(plaintext)

        assert encrypted != plaintext
        assert len(encrypted) > 0
        assert isinstance(encrypted, str)

    def test_decrypt_data(self):
        """Test data decryption."""
        plaintext = "sensitive-api-key-12345"
        encrypted = encrypt_data(plaintext)
        decrypted = decrypt_data(encrypted)

        assert decrypted == plaintext

    def test_encrypt_decrypt_roundtrip(self):
        """Test encryption and decryption roundtrip."""
        data_items = [
            "oauth-token-abcdef123456",
            "api-key-xyz789",
            "secret-value-with-special-chars!@#$%",
            "unicode-data-éàç",
        ]

        for plaintext in data_items:
            encrypted = encrypt_data(plaintext)
            decrypted = decrypt_data(encrypted)
            assert decrypted == plaintext

    def test_encrypt_same_data_produces_different_ciphertexts(self):
        """Test that encrypting same data twice produces different ciphertexts."""
        plaintext = "sensitive-api-key-12345"
        encrypted1 = encrypt_data(plaintext)
        encrypted2 = encrypt_data(plaintext)

        # Fernet uses random IV, so ciphertexts should differ
        assert encrypted1 != encrypted2

        # But both should decrypt to same plaintext
        assert decrypt_data(encrypted1) == plaintext
        assert decrypt_data(encrypted2) == plaintext

    def test_decrypt_invalid_data_raises_error(self):
        """Test that decrypting invalid data raises an error."""
        with pytest.raises((ValueError, TypeError)):
            decrypt_data("invalid-encrypted-data")


@pytest.mark.unit
class TestOAuthSecurity:
    """Test OAuth security utilities."""

    def test_generate_state_token(self):
        """Test state token generation."""
        state1 = generate_state_token()
        state2 = generate_state_token()

        assert isinstance(state1, str)
        assert isinstance(state2, str)
        assert len(state1) > 0
        assert len(state2) > 0
        assert state1 != state2  # Should be unique

    def test_verify_state_token_success(self):
        """Test state token verification with matching tokens."""
        state = generate_state_token()
        assert verify_state_token(state, state) is True

    def test_verify_state_token_failure(self):
        """Test state token verification with mismatched tokens."""
        state1 = generate_state_token()
        state2 = generate_state_token()
        assert verify_state_token(state1, state2) is False

    def test_state_token_length(self):
        """Test state token has reasonable length."""
        state = generate_state_token()
        # URL-safe base64 encoding, 32 bytes = ~43 chars
        assert len(state) >= 40

    def test_generate_code_verifier(self):
        """Test PKCE code verifier generation."""
        verifier1 = generate_code_verifier()
        verifier2 = generate_code_verifier()

        # Verify it's a string
        assert isinstance(verifier1, str)
        assert isinstance(verifier2, str)

        # Verify minimum length (RFC 7636 requires min 43 chars)
        assert len(verifier1) >= 43
        assert len(verifier2) >= 43

        # Verify uniqueness
        assert verifier1 != verifier2

        # Verify it only contains URL-safe characters
        import re

        assert re.match(r"^[A-Za-z0-9_-]+$", verifier1)

    def test_generate_code_challenge(self):
        """Test PKCE code challenge generation."""
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)

        # Verify it's a string
        assert isinstance(challenge, str)

        # Verify it's not the same as verifier
        assert challenge != verifier

        # Verify it's a base64-url-encoded string (no padding)
        import re

        assert re.match(r"^[A-Za-z0-9_-]+$", challenge)
        assert "=" not in challenge  # No padding

    def test_code_challenge_deterministic(self):
        """Test that same verifier always produces same challenge."""
        verifier = generate_code_verifier()
        challenge1 = generate_code_challenge(verifier)
        challenge2 = generate_code_challenge(verifier)

        assert challenge1 == challenge2

    def test_code_challenge_different_verifiers(self):
        """Test that different verifiers produce different challenges."""
        verifier1 = generate_code_verifier()
        verifier2 = generate_code_verifier()
        challenge1 = generate_code_challenge(verifier1)
        challenge2 = generate_code_challenge(verifier2)

        assert challenge1 != challenge2

    def test_code_challenge_sha256_format(self):
        """Test that code challenge is SHA-256 hash (32 bytes = 43 chars base64)."""
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)

        # SHA-256 produces 32 bytes, base64 encoding without padding = 43 chars
        assert len(challenge) == 43


# ============================================================================
# REMOVED: TestTokenPayloads class (JWT testing)
# ============================================================================
# This test class validated JWT token payload structure for access and refresh tokens.
# Removed as part of BFF Pattern migration - see comment block above.
# ============================================================================
