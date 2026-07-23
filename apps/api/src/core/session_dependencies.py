"""
Session-based authentication dependencies for BFF pattern.
Replaces JWT bearer token authentication with HTTP-only cookies.

Architecture (GDPR/OWASP Compliant - 2024):
    1. Cookie contains session_id (opaque token, no PII)
    2. Redis stores minimal session: {user_id, remember_me, created_at}
    3. PostgreSQL is single source of truth for User data
    4. Each authenticated request fetches User from DB

Performance:
    - Redis session check: ~0.1-0.5ms
    - PostgreSQL user fetch: ~0.3-0.5ms (optimized query, PRIMARY KEY index)
    - Total overhead: ~0.5-1ms per request

Security:
    - No PII in Redis (OWASP Session Management compliance)
    - No PII in cookies (HTTP-only, SameSite=Lax)
    - Immediate session revocation (DELETE from Redis)
    - No desynchronization (PostgreSQL = source of truth)
"""

from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import (
    raise_admin_required,
    raise_session_invalid,
    raise_step_up_required,
    raise_user_inactive,
    raise_user_not_authenticated,
    raise_user_not_verified,
)
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

logger = structlog.get_logger(__name__)


async def get_session_store() -> SessionStore:
    """
    Dependency to get SessionStore instance.

    Returns:
        SessionStore instance with Redis connection
    """
    redis = await get_redis_session()
    return SessionStore(redis)


async def get_current_session(
    lia_session: Annotated[str | None, Cookie()] = None,
    session_store: SessionStore = Depends(get_session_store),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current user from session cookie (GDPR/OWASP compliant).

    BFF Pattern with minimal sessions:
    1. Validates session_id in Redis (minimal: user_id + remember_me)
    2. Fetches User from PostgreSQL (single source of truth)
    3. Returns User object (not UserSession - architectural change)

    Performance:
        - Redis GET: ~0.1-0.5ms (session validation)
        - PostgreSQL SELECT: ~0.3-0.5ms (optimized query, no JOINs)
        - Total: ~0.5-1ms per authenticated request

    Args:
        lia_session: Session ID from HTTP-only cookie
        session_store: SessionStore dependency
        db: Database session dependency (NEW)

    Returns:
        User object (ORM model) - CHANGED from UserSession

    Raises:
        HTTPException: 401 if not authenticated or user not found/inactive

    Breaking Change:
        Previously returned UserSession, now returns User.
        Callers must update: session.user_id → user.id, session.email → user.email
    """
    if not lia_session:
        logger.debug("authentication_required_no_cookie")
        raise_user_not_authenticated()

    # Type narrowing: lia_session is str (not None) after check
    assert lia_session is not None

    # Step 1: Validate minimal session in Redis
    session = await session_store.get_session(lia_session)

    if not session:
        raise_session_invalid()

    # Type narrowing: session is UserSession (not None) after check
    assert session is not None

    # D2 device overview: coarse last-seen refresh (>=15 min grain, keepttl).
    # Best-effort — activity tracking must never fail a request.
    with suppress(Exception):
        await session_store.touch_last_seen(session.session_id)

    # Step 2: Fetch User from PostgreSQL (single source of truth)
    user_repo = UserRepository(db)
    user = await user_repo.get_user_minimal_for_session(UUID(session.user_id))

    if not user:
        # Orphan session (user deleted or deactivated) - cleanup
        await session_store.delete_session(session.session_id)
        logger.warning(
            "orphan_session_deleted",
            session_id=session.session_id,
            user_id=session.user_id,
        )
        raise_session_invalid()

    # Type narrowing: user is User (not None) after check
    assert user is not None

    logger.debug(
        "session_authenticated_user_fetched",
        session_id=session.session_id,
        user_id=str(user.id),
        email=user.email,
        is_verified=user.is_verified,
        is_superuser=user.is_superuser,
    )

    return user


async def get_current_active_session(
    user: User = Depends(get_current_session),
) -> User:
    """
    Get current active user (CHANGED: returns User, not UserSession).

    Requires user to be active (not disabled/deleted).

    Note:
        With optimized query (get_user_minimal_for_session), inactive users
        are already filtered at DB level. This check is defensive/redundant.

    Args:
        user: Current user from get_current_session (CHANGED from session)

    Returns:
        User object (CHANGED from UserSession)

    Raises:
        HTTPException: 403 if user is inactive (defensive check)

    Breaking Change:
        Parameter renamed: session → user
        Return type changed: UserSession → User
    """
    # Defensive check (already filtered in get_user_minimal_for_session)
    if not user.is_active:
        raise_user_inactive(user.id)

    # Reject deleted accounts (data purged, row kept for billing only)
    if user.is_deleted:
        raise_user_inactive(user.id)

    return user


async def get_current_verified_session(
    user: User = Depends(get_current_active_session),
) -> User:
    """
    Get current verified user (CHANGED: returns User, not UserSession).

    Requires user to have verified their email.

    Args:
        user: Current user from get_current_active_session (CHANGED from session)

    Returns:
        User object (CHANGED from UserSession)

    Raises:
        HTTPException: 403 if user is not verified

    Breaking Change:
        Parameter renamed: session → user
        Return type changed: UserSession → User
    """
    if not user.is_verified:
        raise_user_not_verified(user.id)

    return user


async def get_current_superuser_session(
    user: User = Depends(get_current_active_session),
) -> User:
    """
    Get current superuser (CHANGED: returns User, not UserSession).

    Requires user to be a superuser (admin).

    Args:
        user: Current user from get_current_active_session (CHANGED from session)

    Returns:
        User object (CHANGED from UserSession)

    Raises:
        HTTPException: 403 if user is not a superuser

    Breaking Change:
        Parameter renamed: session → user
        Return type changed: UserSession → User
    """
    if not user.is_superuser:
        raise_admin_required(user.id)

    return user


async def require_recent_step_up(
    lia_session: Annotated[str | None, Cookie()] = None,
    user: User = Depends(get_current_active_session),
    session_store: SessionStore = Depends(get_session_store),
) -> User:
    """Require a fresh step-up re-authentication on the current session.

    Sensitive actions (credential revocation, MFA management, exports)
    depend on this instead of ``get_current_active_session``. The challenge
    is a typed **403** (``detail.error = "step_up_required"``) — NEVER a
    plain 401, which the frontend hard-redirects to the login page.

    Args:
        lia_session: Session ID from the HTTP-only cookie.
        user: The authenticated active user (chains the standard checks).
        session_store: SessionStore dependency.

    Returns:
        The authenticated user, when the session carries a step-up newer
        than ``settings.step_up_window_seconds``.

    Raises:
        HTTPException: 403 with the step-up contract otherwise.
    """
    assert lia_session is not None  # get_current_active_session already required it

    session = await session_store.get_session(lia_session)
    if session is None or session.step_up_at is None:
        raise_step_up_required()

    age_seconds = (datetime.now(UTC) - session.step_up_at).total_seconds()
    if age_seconds > settings.step_up_window_seconds:
        logger.debug(
            "step_up_expired",
            session_id=lia_session,
            age_seconds=int(age_seconds),
        )
        raise_step_up_required()

    return user


async def get_optional_session(
    lia_session: Annotated[str | None, Cookie()] = None,
    session_store: SessionStore = Depends(get_session_store),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Get current user if authenticated, None otherwise (CHANGED: returns User).

    Useful for endpoints that work for both authenticated and anonymous users.

    Args:
        lia_session: Session ID from HTTP-only cookie
        session_store: SessionStore dependency
        db: Database session dependency (NEW)

    Returns:
        User object or None if not authenticated (CHANGED from UserSession)

    Breaking Change:
        Return type changed: UserSession | None → User | None
    """
    if not lia_session:
        return None

    session = await session_store.get_session(lia_session)
    if not session:
        return None

    # Fetch User from PostgreSQL
    user_repo = UserRepository(db)
    user = await user_repo.get_user_minimal_for_session(UUID(session.user_id))

    if user:
        logger.debug(
            "optional_user_found",
            session_id=session.session_id,
            user_id=str(user.id),
            email=user.email,
        )
    else:
        # Cleanup orphan session
        await session_store.delete_session(session.session_id)
        logger.debug(
            "optional_session_orphan_cleaned",
            session_id=session.session_id,
            user_id=session.user_id,
        )

    return user
