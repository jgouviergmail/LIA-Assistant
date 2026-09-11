"""The person's own gate on habit LEARNING — read where the learning happens.

« Apprendre mes habitudes » is one switch in the settings panel, and its copy
promises that both halves of ADR-214 obey it: the rhythm AND the recurring
requests. Until 2026-09-11 only the rhythm did (the nightly job filters on
``users.habits_enabled``): the recurrence ledger kept recording every
actionable turn and the chat kept suggesting « je remarque que tu me demandes
ce genre de chose tous les jours » to someone who had switched learning off
(measured, sim C5). A habit the person BLOCKED was suggested again every
cooldown period for the same reason: nothing on the chat side ever read the
tombstone.

This module is the one reader of that gate for the chat-side detector. It is
deliberately a DATABASE read rather than a value threaded through the typed
run context: the ledger write is a fire-and-forget background task and the
suggestion evaluates a lock at most once per turn, so one indexed read costs
nothing measurable, while threading a new positional preference through the
six chokepoint signatures would touch four frozen files for a fact the
database already owns.

Failure mode is CLOSED: when the gate cannot be read, nothing is learned and
nothing is suggested — the privacy-preserving side of « unsure ».
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import select

from src.domains.habits.models import HabitKind, UserHabit

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LearningGate:
    """What the person allows for one recurrence signature.

    Attributes:
        allowed: The account preference (``users.habits_enabled``) — False
            when the person switched learning off, or when the read failed.
        recurring_status: Status of the ``recurring_request`` row for the
            signature (``active`` | ``paused`` | ``blocked``), or None when
            no row exists yet.
    """

    allowed: bool
    recurring_status: str | None = None

    @property
    def suggestion_allowed(self) -> bool:
        """Whether the chat may suggest automating this signature.

        A PAUSED row is the person's snooze and a BLOCKED row their refusal:
        neither may be suggested again, whatever the ledger says.
        """
        return self.allowed and self.recurring_status not in ("paused", "blocked")


CLOSED = LearningGate(allowed=False)


async def read_learning_gate(user_id: str | UUID, signature: str | None = None) -> LearningGate:
    """Read the person's learning preference and, optionally, one tombstone.

    Args:
        user_id: Owner (string or UUID form).
        signature: Recurrence signature whose row status is wanted, or None
            when only the account preference matters (the ledger write).

    Returns:
        The gate; :data:`CLOSED` when the account is unknown or the read
        failed (logged at warning — production ships INFO and above).
    """
    try:
        from src.domains.users.models import User
        from src.infrastructure.database import get_db_context

        uid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
        async with get_db_context() as db:
            allowed = await db.scalar(select(User.habits_enabled).where(User.id == uid))
            if not allowed:
                return CLOSED
            if signature is None:
                return LearningGate(allowed=True)
            status = await db.scalar(
                select(UserHabit.status).where(
                    UserHabit.user_id == uid,
                    UserHabit.kind == HabitKind.RECURRING_REQUEST.value,
                    UserHabit.key == signature,
                )
            )
            return LearningGate(allowed=True, recurring_status=status)
    except Exception as exc:  # noqa: BLE001 — closed on doubt, never raised at a turn
        logger.warning(
            "habits_learning_gate_unreadable",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return CLOSED
