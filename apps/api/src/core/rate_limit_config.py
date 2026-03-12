"""
Rate limiting configuration utilities for SlowAPI integration.

This module provides centralized configuration helpers for HTTP rate limiting,
ensuring consistent application of limits across all FastAPI endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.constants import (
    RATE_LIMIT_AUTH_LOGIN_PER_MINUTE,
    RATE_LIMIT_AUTH_REGISTER_PER_MINUTE,
    RATE_LIMIT_SSE_MAX_PER_MINUTE,
)

if TYPE_CHECKING:
    from src.core.config import Settings


def build_default_limit(settings: Settings) -> str:
    """
    Build the default rate limit string for SlowAPI.

    Args:
        settings: Application settings instance

    Returns:
        Rate limit string in SlowAPI format (e.g., "60/minute")

    Example:
        >>> settings = Settings(rate_limit_per_minute=60)
        >>> build_default_limit(settings)
        '60/minute'
    """
    return f"{settings.rate_limit_per_minute}/minute"


def rate_limiting_enabled(settings: Settings) -> bool:
    """
    Check if HTTP rate limiting is enabled globally.

    Args:
        settings: Application settings instance

    Returns:
        True if rate limiting should be enforced, False otherwise

    Example:
        >>> settings = Settings(rate_limit_enabled=True)
        >>> rate_limiting_enabled(settings)
        True
    """
    return settings.rate_limit_enabled


def resolve_endpoint_limit(endpoint_type: str, settings: Settings) -> str:
    """
    Resolve rate limit for specific endpoint types.

    Different endpoints may require different rate limiting strategies:
    - SSE/streaming endpoints: more permissive to allow long-running connections
    - Authentication endpoints: stricter to prevent brute force attacks
    - Standard API endpoints: default limits

    Args:
        endpoint_type: Type of endpoint ('sse', 'auth_login', 'auth_register', 'default')
        settings: Application settings instance

    Returns:
        Rate limit string in SlowAPI format

    Raises:
        ValueError: If endpoint_type is not recognized

    Example:
        >>> settings = Settings(rate_limit_per_minute=60)
        >>> resolve_endpoint_limit('auth_login', settings)
        '10/minute'
        >>> resolve_endpoint_limit('sse', settings)
        '30/minute'
    """
    # Map endpoint types to their rate limits
    endpoint_limits = {
        "sse": min(settings.rate_limit_per_minute * 2, RATE_LIMIT_SSE_MAX_PER_MINUTE),
        "auth_login": RATE_LIMIT_AUTH_LOGIN_PER_MINUTE,
        "auth_register": RATE_LIMIT_AUTH_REGISTER_PER_MINUTE,
        "default": settings.rate_limit_per_minute,
    }

    if endpoint_type not in endpoint_limits:
        raise ValueError(
            f"Unknown endpoint_type: {endpoint_type}. "
            f"Valid types: {', '.join(endpoint_limits.keys())}"
        )

    limit = endpoint_limits[endpoint_type]
    return f"{limit}/minute"


def get_rate_limit_message(endpoint_type: str = "default") -> dict[str, str]:
    """
    Generate a structured rate limit error message.

    Args:
        endpoint_type: Type of endpoint for context-specific messaging

    Returns:
        Dictionary with error details for HTTP 429 responses

    Example:
        >>> get_rate_limit_message('auth_login')
        {'error': 'rate_limit_exceeded', 'message': 'Too many login attempts...'}
    """
    messages = {
        "auth_login": {
            "error": "rate_limit_exceeded",
            "message": "Too many login attempts. Please try again later.",
        },
        "auth_register": {
            "error": "rate_limit_exceeded",
            "message": "Too many registration attempts. Please try again later.",
        },
        "sse": {
            "error": "rate_limit_exceeded",
            "message": "Too many streaming requests. Please try again later.",
        },
        "default": {
            "error": "rate_limit_exceeded",
            "message": "Rate limit exceeded. Please try again later.",
        },
    }

    return messages.get(endpoint_type, messages["default"])
