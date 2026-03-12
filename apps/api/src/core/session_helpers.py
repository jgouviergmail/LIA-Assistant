"""
Helper functions for session management in BFF Pattern.

Provides utilities for creating authenticated sessions with HTTP-only cookies.
"""

from typing import Any, Literal, cast

import structlog
from fastapi import Response

from src.core.config import settings
from src.core.field_names import FIELD_SESSION_ID, FIELD_USER_ID
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore, UserSession

logger = structlog.get_logger(__name__)


async def create_authenticated_session_with_cookie(
    response: Response,
    user_id: str,
    remember_me: bool = False,
    event_name: str = "session_created",
    extra_context: dict[str, Any] | None = None,
    old_session_id: str | None = None,
) -> UserSession:
    """
    Create authenticated session and set HTTP-only cookie.

    This is the standard flow for register/login/OAuth after user authentication.
    Centralizes session creation logic to eliminate code duplication across auth endpoints.

    Handles:
    1. Session creation in Redis with appropriate TTL
    2. Cookie setting with security flags (HttpOnly, Secure, SameSite)
    3. TTL synchronization between Redis session and browser cookie
    4. Structured logging with contextual information

    Args:
        response: FastAPI Response object to set cookie on
        user_id: User ID to create session for
        remember_me: If True, uses extended TTL (30 days), else short TTL (7 days)
        event_name: Log event name for structured logging (e.g., "user_registered_bff")
        extra_context: Additional context fields for logging (e.g., {"email": "user@example.com"})
        old_session_id: Previous session ID to invalidate (PROD only, for session rotation)

    Returns:
        UserSession: Created session object with minimal data (user_id, session_id)

    Security notes:
    - HTTP-only cookie prevents XSS attacks (JavaScript cannot access)
    - Secure flag enforces HTTPS in production
    - SameSite=Lax prevents CSRF attacks
    - Session stored server-side in Redis, only session ID in cookie
    - GDPR compliant: minimal data storage (no PII in Redis)

    Performance:
    - Session creation: ~0.1-0.5ms (Redis SETEX + SADD for index)
    - Cookie setting: negligible (HTTP header)
    - Total overhead: <1ms

    Usage:
        # Register/Login
        await create_authenticated_session_with_cookie(
            response=response,
            user_id=str(user.id),
            remember_me=data.remember_me,
            event_name="user_registered_bff",
            extra_context={"email": user.email},
        )

        # OAuth callback
        await create_authenticated_session_with_cookie(
            response=response,
            user_id=str(user.id),
            remember_me=False,
            event_name="oauth_callback_success_bff",
            extra_context={"email": user.email, "redirect_to": redirect_url},
        )

        # Login with session rotation (PROD only)
        await create_authenticated_session_with_cookie(
            response=response,
            user_id=str(user.id),
            remember_me=data.remember_me,
            event_name="user_logged_in_bff",
            extra_context={"email": user.email},
            old_session_id=existing_session_id,  # Invalidates old session
        )

    Best practices:
    - Follows DRY principle (single source of truth)
    - Uses structlog context binding pattern (2025 best practice)
    - Extensible via extra_context without signature changes (Open/Closed principle)
    """
    # Create session in Redis with user session index
    redis = await get_redis_session()
    session_store = SessionStore(redis)

    # Session rotation (PROD only): Invalidate old session before creating new one
    # Prevents session fixation attacks where attacker pre-sets a session ID
    if old_session_id and settings.is_production:
        await session_store.delete_session(old_session_id)
        logger.info(
            "session_rotated",
            old_session_id=old_session_id,
            user_id=user_id,
            reason="login_security",
        )

    session = await session_store.create_session(
        user_id=user_id,
        remember_me=remember_me,
    )

    # Calculate cookie TTL (must match Redis TTL for consistency)
    session_ttl = (
        settings.session_cookie_max_age_remember if remember_me else settings.session_cookie_max_age
    )

    # Set HTTP-only session cookie with security flags
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.session_id,
        max_age=session_ttl,
        secure=settings.session_cookie_secure,
        httponly=settings.session_cookie_httponly,
        samesite=cast(Literal["lax", "strict", "none"], settings.session_cookie_samesite),
        domain=settings.session_cookie_domain,
    )

    # Build structured logging context
    context: dict[str, Any] = {
        FIELD_USER_ID: user_id,
        FIELD_SESSION_ID: session.session_id,
        "remember_me": remember_me,
        "session_ttl_days": session_ttl / 86400,
    }

    # Merge with extra context if provided (extra_context takes precedence for custom fields)
    if extra_context:
        context.update(extra_context)

    # Log session creation with structured context
    logger.info(event_name, **context)

    return session


def clear_session_cookie(response: Response) -> None:
    """
    Clear the session cookie from the response.

    Used by logout endpoints to invalidate client-side session.
    Centralizes cookie deletion logic to eliminate code duplication.

    Args:
        response: FastAPI Response object to clear cookie from

    Security notes:
    - Must match cookie creation parameters (domain, samesite) for proper deletion
    - Browser will only delete cookie if parameters match exactly

    Usage:
        # In logout endpoint
        clear_session_cookie(response)

        # Combined with session deletion
        await session_store.delete_session(session_id)
        clear_session_cookie(response)
    """
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain,
        samesite=cast(Literal["lax", "strict", "none"], settings.session_cookie_samesite),
    )
