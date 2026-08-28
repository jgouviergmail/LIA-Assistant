"""Shared superuser gate for admin-only agent tools.

Single implementation of the check the DevOps tool pioneered (extracted for
the diagnostics tools — factorisation, not duplication). Fail-secure: any
failure (missing user, invalid id, DB error) resolves to False.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def user_is_superuser(user_id: str) -> bool:
    """Check whether the user has superuser privileges (one indexed read).

    Args:
        user_id: User UUID string (any failure to parse resolves to False).

    Returns:
        True only for an existing user with ``is_superuser`` set.
    """
    try:
        from src.domains.users.models import User

        async with get_db_context() as db:
            user = await db.get(User, UUID(str(user_id)))
            if user is None:
                return False
            return bool(user.is_superuser)
    except Exception as exc:
        logger.warning("admin_gate_check_failed", user_id=str(user_id), error=str(exc))
        return False
