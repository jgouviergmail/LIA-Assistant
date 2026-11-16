"""The opted-in health context a model surface reads — one door.

Three surfaces give a model the person's recent health history as context: the
memory extractor, the journal extractor and the journal consolidation. Each
carried its own copy of the same gate — the instance switch, the person's
opt-in, their time zone, an empty answer on failure — and two of the copies
logged an error's text, which a log line never carries (ADR-317). They read it
here; each keeps only how its prompt frames the block.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import HEALTH_METRICS_USER_TOGGLE_ATTR
from src.core.time_utils import resolve_user_timezone
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.users.repository import UserRepository
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

#: What a surface hands a prompt when there is nothing to say.
NO_HEALTH_CONTEXT: Final = ""


async def opted_in_health_context(user_id: UUID, *, surface: str) -> str:
    """The person's health context for a prompt, or nothing.

    Nothing when the instance switch is off, the person has not opted into the
    assistant reading their health history, they have no history, or the read
    failed — the prompts mark the block optional. Reads on a short session of
    its own, closed before the caller's model call.

    Args:
        user_id: The account whose history is read.
        surface: Which surface asks (a bounded word, for the log line).

    Returns:
        The context block, or ``""``.
    """
    if not settings.health_metrics_enabled:
        return NO_HEALTH_CONTEXT
    try:
        async with get_db_context() as db:
            user = await UserRepository(db).get_by_id(user_id)
            if user is None or not getattr(user, HEALTH_METRICS_USER_TOGGLE_ATTR, False):
                return NO_HEALTH_CONTEXT
            return await HealthMetricsService(db).build_health_context_for_prompt(
                user_id, zone=resolve_user_timezone(user)
            )
    except Exception as exc:  # noqa: BLE001 — context is optional: a failure leaves it out
        logger.warning(
            "health_prompt_context_failed",
            surface=surface,
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return NO_HEALTH_CONTEXT


__all__ = ["NO_HEALTH_CONTEXT", "opted_in_health_context"]
