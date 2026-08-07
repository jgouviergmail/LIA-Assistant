"""Preferences a demonstrator account starts with.

The instance-level half of this decision lives in
``infrastructure/provisioning/demo_defaults.py``, which opens
``DEBUG_PANEL_USER_ACCESS_ENABLED`` because "showing the reasoning IS the
demonstration". This module is the per-ACCOUNT half: the gate being open is
useless while every visitor's own switch is off.

The per-user flag is documented on the model as an opt-in defaulting to
``False`` — right for a private instance, where the panel exposes a run's
internals, and wrong for one whose entire purpose is to be looked at. Measured
2026-08-07: a visitor saw the panel render and stay empty, with no error
anywhere, because the emission is gated on ``user_access AND
user.debug_panel_enabled``.

It stays a PREFERENCE, deliberately: a visitor can switch it off, and an
operator can close the instance-level gate for everybody. This only decides
where a brand-new account starts.

Created: 2026-08-07 (live-demonstrator programme, owner arbitration)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.users.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: Where a demonstrator account starts, and nothing else. Adding an entry is a
#: decision about what a visitor sees on their first screen — the same
#: doctrine as ``DEMO_SETTING_DEFAULTS`` for the instance.
DEMO_ACCOUNT_PREFERENCES: dict[str, Any] = {
    # Showing the reasoning IS the demonstration: routing, plan, tokens spent.
    "debug_panel_enabled": True,
}


async def apply_demo_account_preferences(db: AsyncSession, user_id: UUID) -> bool:
    """Start this account with the demonstrator's preferences.

    No-op outside demo mode: a private instance must never have a visitor's
    internals panel switched on behind their back.

    Loads the row rather than issuing an UPDATE. The two sign-up paths have
    different transaction topologies — email/password commits before
    provisioning, the OAuth callback commits once at the very end — so a
    statement aimed at a still-pending row would update nothing and report
    nothing. Reading it works on both, and leaves the write to the caller's
    commit like every other step of the cascade.

    Never raises. A visitor without a debug panel is disappointed; a visitor
    who cannot sign up sees nothing at all.

    Args:
        db: Session whose transaction the caller owns (no commit here).
        user_id: The freshly created account.

    Returns:
        True when the preferences were applied.
    """
    if not settings.demo_mode_enabled:
        return False

    try:
        user = await db.get(User, user_id)
        if user is None:
            logger.warning("demo_account_preferences_user_absent", user_id=str(user_id))
            return False
        for name, value in DEMO_ACCOUNT_PREFERENCES.items():
            setattr(user, name, value)
    except Exception as exc:  # noqa: BLE001 — never break a sign-up
        logger.error(
            "demo_account_preferences_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return False

    logger.info(
        "demo_account_preferences_applied",
        user_id=str(user_id),
        preferences=sorted(DEMO_ACCOUNT_PREFERENCES),
    )
    return True
