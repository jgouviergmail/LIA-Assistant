"""Nightly wipe of visitor accounts on a demonstrator instance.

Everything resets each night so the next day starts from zero: no data
accumulates, no account survives, nothing is left to leak. It is what makes
an open demonstrator sustainable.

Two design points worth stating, because both are easy to get wrong:

- **The row goes, not just its data.** ``AccountDeletionService`` purges every
  personal table but KEEPS the users row with its email (billing contact,
  ADR-067). On a demonstrator that would lock the address forever, so the same
  visitor could never come back tomorrow — precisely the journey advertised.
  The sweep therefore calls the audited path first, then removes the row.
- **The purge is not a hand-rolled cascade.** Re-implementing the deletion
  would drift from the production path the moment a table is added. The sweep
  orchestrates; the deletion service still owns what "delete an account"
  means.

It lives in the scheduler layer rather than in ``domains/users`` on purpose:
it orchestrates TWO domains (the account lifecycle and the settings store
that authorizes the sweep). Hosting it inside either one would make that
domain import the other and close a runtime import cycle (F009) — the same
lesson as the spend ceiling in lot 1.

Created: 2026-08-06 (live-demonstrator programme, lot 2)
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.users.models import User
from src.infrastructure.database import get_db_context

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PurgeReport:
    """What the sweep actually did — a silent no-op must stay visible."""

    purged: int = 0
    failed: int = 0
    skipped_reason: str | None = None


async def delete_user_row(db: AsyncSession, user_id: UUID) -> None:
    """Remove the users row itself, freeing the email address.

    Called AFTER the audited purge emptied every personal table. Foreign keys
    pointing at users are either CASCADE (already emptied) or SET NULL (admin
    records, which document an action rather than a person).

    Args:
        db: Async session; the caller owns the commit.
        user_id: Account to remove.
    """
    await db.execute(delete(User).where(User.id == user_id))


async def _sweep_one(db: AsyncSession, user: User, operator_id: UUID | None) -> None:
    """Deactivate, purge through the audited path, then drop the row."""
    from src.domains.users.account_deletion_service import AccountDeletionService

    # The production path refuses an active account (409). Deactivating here
    # also ends the visitor's session — the announced nightly reset.
    user.is_active = False
    await db.commit()

    await AccountDeletionService(db).delete_account(
        user_id=user.id,
        admin_user_id=operator_id,
        reason="demo_nightly_purge",
    )
    await delete_user_row(db, user.id)
    await db.commit()


async def purge_demo_accounts() -> PurgeReport:
    """Wipe every visitor account. No-op unless the instance is a demonstrator.

    Superusers are excluded IN THE QUERY, not by a later filter: an operator
    locked out of their own demonstrator has no way back in.

    A failing account is logged and skipped — two survivors beat a whole night
    skipped.

    Returns:
        What was purged, what failed, and why nothing happened if so.
    """
    if not settings.demo_mode_enabled:
        # A private instance must never lose its users to a schedule that was
        # left enabled by mistake.
        logger.debug("demo_account_purge_skipped", reason="demo_mode_disabled")
        return PurgeReport(skipped_reason="demo_mode_disabled")

    # SECOND, INDEPENDENT condition, and the one that actually protects:
    # a marker stored IN THE DATABASE this job would empty. An environment
    # variable describes a process; it can be set by a script, a shell, a
    # test harness pointed at the wrong database. The marker travels with the
    # data, so a database that is not a demonstrator's cannot be swept
    # whatever the process believes about itself.
    if not await _instance_is_a_demonstrator():
        logger.warning(
            "demo_account_purge_refused",
            reason="instance_marker_absent",
            detail=(
                "DEMO_MODE_ENABLED is set but this database carries no "
                "demonstrator marker — refusing to delete accounts."
            ),
        )
        return PurgeReport(skipped_reason="instance_marker_absent")

    purged = 0
    failed = 0
    async with get_db_context() as db:
        result = await db.execute(select(User).where(User.is_superuser.is_(False)))
        visitors = list(result.scalars().all())

        operator_id = await _operator_id(db)
        for user in visitors:
            try:
                await _sweep_one(db, user, operator_id)
                purged += 1
            except Exception as exc:  # noqa: BLE001 — one bad row, not the night
                failed += 1
                logger.error(
                    "demo_account_purge_failed",
                    user_id=str(user.id),
                    error_type=type(exc).__name__,
                )
                await db.rollback()

    logger.info("demo_account_purge_complete", purged=purged, failed=failed)
    return PurgeReport(purged=purged, failed=failed)


async def _instance_is_a_demonstrator() -> bool:
    """Whether the DATABASE itself is marked as a demonstrator's.

    Read straight from the store, never from a cache: this authorizes
    deleting every visitor account.

    Returns:
        True only when the marker was explicitly set on this database.
    """
    from src.domains.system_settings.models import SystemSettingKey
    from src.domains.system_settings.registry import read_setting

    marked: bool = await read_setting(SystemSettingKey.DEMO_INSTANCE_MARKER)
    return marked


async def _operator_id(db: AsyncSession) -> UUID | None:
    """The superuser credited in the audit trail, when there is one.

    None on an instance with no administrator — which is the NOMINAL case for
    a demonstrator: nobody creates an admin on a throwaway instance. The
    previous nil-UUID fallback was a `users.id` that does not exist, so the
    admin audit insert raised a foreign key violation and took the whole
    deletion down with it: measured 2026-08-06, a visitor account, its
    connector and eleven messages survived the purge the terms promise.
    """
    result = await db.execute(select(User.id).where(User.is_superuser.is_(True)).limit(1))
    return result.scalar_one_or_none()
