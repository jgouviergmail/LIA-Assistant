"""The two habit-proposal handlers heartbeat owns: its own preferences (ADR-375).

``extend_notification_window`` moves the notification hours to the window the
proposal showed; ``review_notifications`` switches the proactive notifications
off. Both write through ``update_heartbeat_preferences`` — the door the
settings panel and the confirmed assistant commands share — with the state the
person was SHOWN as the expected one: hours changed since, or notifications
already off, refuse rather than overwrite (``settings_changed``).

``heartbeat`` imports habits, so habits cannot import this module: it is
installed into ``habits.proposal_actions`` at import and again by the boot.
"""

from __future__ import annotations

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.habits.models import HabitProposal, ProposalKind
from src.domains.habits.proposal_actions import (
    ProposalActionRefused,
    ProposalActionResult,
    ProposalRefusal,
    install_proposal_action,
)
from src.domains.habits.proposal_facts import ExtendWindowFacts, ReviewNotificationsFacts
from src.domains.heartbeat.preference_commands import update_heartbeat_preferences
from src.domains.heartbeat.schemas import HeartbeatSettingsUpdate
from src.domains.users.models import User


async def _write(
    db: AsyncSession,
    user: User,
    update: HeartbeatSettingsUpdate,
    expected: dict[str, JsonValue],
) -> ProposalActionResult:
    """Apply a preference change conditioned on the state the person was shown."""
    try:
        await update_heartbeat_preferences(db, user.id, update, expected=expected)
    except ResourceConflictError:
        raise ProposalActionRefused(ProposalRefusal.SETTINGS_CHANGED) from None
    return ProposalActionResult()


async def extend_notification_window(
    db: AsyncSession, user: User, proposal: HabitProposal
) -> ProposalActionResult:
    """Move the notification hours to the window the proposal showed.

    Args:
        db: The decision's session.
        user: The person accepting.
        proposal: The claimed proposal.

    Returns:
        An empty result.

    Raises:
        ProposalActionRefused: When the hours changed since the proposal.
    """
    facts = ExtendWindowFacts.model_validate(proposal.payload)
    return await _write(
        db,
        user,
        HeartbeatSettingsUpdate(
            heartbeat_notify_start_hour=facts.new_start,
            heartbeat_notify_end_hour=facts.new_end,
        ),
        {"heartbeat_notify_start_hour": facts.start, "heartbeat_notify_end_hour": facts.end},
    )


async def review_notifications(
    db: AsyncSession, user: User, proposal: HabitProposal
) -> ProposalActionResult:
    """Switch the proactive notifications off — nobody reacted to them.

    Args:
        db: The decision's session.
        user: The person accepting.
        proposal: The claimed proposal.

    Returns:
        An empty result.

    Raises:
        ProposalActionRefused: When they were already switched off.
    """
    ReviewNotificationsFacts.model_validate(proposal.payload)
    return await _write(
        db, user, HeartbeatSettingsUpdate(heartbeat_enabled=False), {"heartbeat_enabled": True}
    )


def install() -> None:
    """Register the two handlers heartbeat owns."""
    install_proposal_action(ProposalKind.EXTEND_NOTIFICATION_WINDOW, extend_notification_window)
    install_proposal_action(ProposalKind.REVIEW_NOTIFICATIONS, review_notifications)


install()
