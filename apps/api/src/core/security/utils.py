"""
Security utilities for authentication and authorization.
Includes JWT token handling, password hashing, and OAuth flows.
Provides AuthProvider interface for future service-to-service auth.

Security features (PROD only):
- JTI (JWT ID): Single-use tokens for email verification and password reset.
  Prevents token reuse attacks. Tokens are blacklisted in Redis after first use.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import bcrypt
import structlog
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from src.core.config import settings
from src.core.constants import (
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
    JTI_BLACKLIST_REDIS_PREFIX,
    JTI_BLACKLIST_TTL_SECONDS,
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
)

logger = structlog.get_logger(__name__)

# Fernet cipher for encrypting sensitive data (connector tokens, etc.)
cipher_suite = Fernet(settings.fernet_key.encode())


class AuthProvider(ABC):
    """
    Abstract base class for authentication providers.

    This interface allows for future implementation of:
    - Service-to-service authentication (mTLS, service tokens)
    - Different OAuth providers
    - Custom authentication mechanisms

    Example implementations:
    - JWTAuthProvider (current, for users)
    - ServiceTokenAuthProvider (future, for microservices)
    - mTLSAuthProvider (future, for service mesh)
    """

    @abstractmethod
    def authenticate(self, credentials: Any) -> dict[str, Any] | None:
        """Authenticate and return user/service information."""
        pass

    @abstractmethod
    def verify(self, token: str) -> dict[str, Any] | None:
        """Verify token and return decoded payload."""
        pass


# Password utilities
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: The plain text password to hash

    Returns:
        The bcrypt hashed password

    Raises:
        ValueError: If password is empty or whitespace only
    """
    if not password or not password.strip():
        raise ValueError("Password cannot be empty")

    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# JWT token verification (used for email verification and password reset)
def verify_token(token: str) -> dict[str, Any] | None:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string to verify

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        return payload
    except JWTError:
        return None


async def verify_single_use_token(
    token: str,
    expected_type: str,
) -> tuple[dict[str, Any], str | None]:
    """
    Verify a single-use token (email verification or password reset).

    Combines token verification + JTI reuse check (PROD only).
    DRY helper to eliminate duplication in verify_email and reset_password.

    Args:
        token: JWT token string
        expected_type: Expected token type ("email_verification" or "password_reset")

    Returns:
        Tuple of (payload, jti) where jti may be None in dev

    Raises:
        AuthenticationError: If token is invalid, expired, or already used (PROD)
    """
    from src.core.exceptions import raise_token_already_used, raise_token_invalid

    payload = verify_token(token)

    if not payload or payload.get("type") != expected_type:
        raise_token_invalid(f"{expected_type.replace('_', ' ')} token")

    # JTI single-use check (PROD only)
    jti = payload.get("jti")
    if jti and await is_token_used(jti):
        logger.warning(f"{expected_type}_token_reused", jti=jti)
        raise_token_already_used(expected_type)

    return payload, jti


def create_verification_token(
    email: str, expires_hours: int = EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
) -> str:
    """
    Create an email verification token.

    Args:
        email: User email address
        expires_hours: Token expiration in hours (default: 24 hours)

    Returns:
        Encoded JWT verification token

    Security (PROD only):
        Includes JTI (JWT ID) for single-use enforcement via Redis blacklist.
    """
    expire = datetime.now(UTC) + timedelta(hours=expires_hours)
    to_encode: dict[str, Any] = {
        "sub": email,
        "type": "email_verification",
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    # JTI for single-use tokens (PROD only)
    if settings.is_production:
        to_encode["jti"] = str(uuid4())

    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def create_password_reset_token(
    email: str, expires_hours: int = PASSWORD_RESET_TOKEN_EXPIRE_HOURS
) -> str:
    """
    Create a password reset token.

    Args:
        email: User email address
        expires_hours: Token expiration in hours (default: 1 hour for security)

    Returns:
        Encoded JWT password reset token

    Security (PROD only):
        Includes JTI (JWT ID) for single-use enforcement via Redis blacklist.
    """
    expire = datetime.now(UTC) + timedelta(hours=expires_hours)
    to_encode: dict[str, Any] = {
        "sub": email,
        "type": "password_reset",
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    # JTI for single-use tokens (PROD only)
    if settings.is_production:
        to_encode["jti"] = str(uuid4())

    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )


# Encryption utilities for sensitive data (connector tokens, API keys)
def encrypt_data(data: str) -> str:
    """
    Encrypt sensitive data using Fernet symmetric encryption.
    Used for storing OAuth tokens, API keys, etc.

    Args:
        data: Plain text data to encrypt

    Returns:
        Encrypted data as base64 string
    """
    return cipher_suite.encrypt(data.encode()).decode()


def decrypt_data(encrypted_data: str) -> str:
    """
    Decrypt sensitive data using Fernet symmetric encryption.

    Args:
        encrypted_data: Encrypted data as base64 string

    Returns:
        Decrypted plain text data

    Raises:
        ValueError: If the encrypted data is invalid or cannot be decrypted
    """
    try:
        return cipher_suite.decrypt(encrypted_data.encode()).decode()
    except Exception as exc:
        raise ValueError(f"Failed to decrypt data: {exc!s}") from exc


# CSRF protection for OAuth flows
def generate_state_token() -> str:
    """
    Generate a random state token for OAuth CSRF protection.

    Returns:
        Random state token string
    """
    import secrets

    return secrets.token_urlsafe(32)


def verify_state_token(state: str, stored_state: str) -> bool:
    """
    Verify OAuth state token against stored value.

    Args:
        state: State token from OAuth callback
        stored_state: State token stored before redirect

    Returns:
        True if tokens match, False otherwise
    """
    return state == stored_state


# PKCE (Proof Key for Code Exchange) for OAuth flows
def generate_code_verifier() -> str:
    """
    Generate a code verifier for PKCE flow.

    Per RFC 7636, the code verifier should be a cryptographically random string
    using the characters [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"
    with a minimum length of 43 characters and a maximum length of 128 characters.

    Returns:
        Random code verifier string (43-128 characters)
    """
    import secrets

    # Generate 43 characters (minimum required by RFC 7636)
    return secrets.token_urlsafe(43)


def generate_code_challenge(code_verifier: str) -> str:
    """
    Generate a code challenge from a code verifier for PKCE flow.

    Uses S256 (SHA-256) method as recommended by RFC 7636.

    Args:
        code_verifier: The code verifier string

    Returns:
        Base64-URL-encoded SHA-256 hash of the verifier
    """
    import base64
    import hashlib

    # SHA-256 hash the code verifier
    digest = hashlib.sha256(code_verifier.encode()).digest()

    # Base64-URL encode (without padding)
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")

    return code_challenge


# =============================================================================
# JTI (JWT ID) Blacklist for Single-Use Tokens (PROD only)
# =============================================================================
# Used for email verification and password reset tokens to prevent reuse.
# Blacklist stored in Redis with TTL matching token expiration.
# Constants defined in src.core.constants (JTI_BLACKLIST_*)
# =============================================================================


async def is_token_used(jti: str) -> bool:
    """
    Check if a token JTI has already been used (PROD only).

    Args:
        jti: JWT ID from token payload

    Returns:
        True if token was already used, False otherwise

    Note:
        Returns False in development (JTI checking disabled).
    """
    if not settings.is_production:
        return False

    from src.infrastructure.cache.redis import get_redis_session

    redis = await get_redis_session()
    key = f"{JTI_BLACKLIST_REDIS_PREFIX}{jti}"
    result = await redis.exists(key)
    return result > 0


async def mark_token_used(jti: str, token_type: str = "unknown") -> None:
    """
    Mark a token JTI as used (blacklist it) - PROD only.

    Args:
        jti: JWT ID from token payload
        token_type: Type of token for logging (email_verification, password_reset)

    Note:
        No-op in development (JTI checking disabled).
    """
    if not settings.is_production:
        return

    from src.infrastructure.cache.redis import get_redis_session

    redis = await get_redis_session()
    key = f"{JTI_BLACKLIST_REDIS_PREFIX}{jti}"
    await redis.setex(key, JTI_BLACKLIST_TTL_SECONDS, "1")

    logger.info(
        "token_jti_blacklisted",
        jti=jti,
        token_type=token_type,
        ttl_hours=JTI_BLACKLIST_TTL_SECONDS / 3600,
    )
