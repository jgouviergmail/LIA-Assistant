"""The person's own gate on habit LEARNING — read where the learning happens.

« Apprendre mes habitudes » is one switch in the settings panel, and its copy
promises that everything habits does obeys it: the rhythm, the request ledger
and the proposals (ADR-214, ADR-375). The nightly job filters on
``users.habits_enabled``; the readers that run OUTSIDE that job — the ledger
write after a chat turn, the proposals inbox and its badge, the chat card —
read the switch here, through ONE function.

It is deliberately a DATABASE read rather than a value threaded through the
typed run context: the ledger write is a fire-and-forget background task, and
one indexed read costs nothing measurable, while threading a new preference
through the chokepoint signatures would touch frozen files for a fact the
database already owns.

Failure mode is CLOSED: when the gate cannot be read, nothing is learned and
nothing is proposed — the privacy-preserving side of « unsure ».
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import select

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LearningGate:
    """What the person allows.

    Attributes:
        allowed: The account preference (``users.habits_enabled``) — False
            when the person switched learning off, or when the read failed.
    """

    allowed: bool


CLOSED = LearningGate(allowed=False)


async def read_learning_gate(user_id: str | UUID) -> LearningGate:
    """Read the person's learning preference.

    Args:
        user_id: Owner (string or UUID form).

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
        return LearningGate(allowed=bool(allowed))
    except Exception as exc:  # noqa: BLE001 — closed on doubt, never raised at a turn
        logger.warning(
            "habits_learning_gate_unreadable",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return CLOSED
