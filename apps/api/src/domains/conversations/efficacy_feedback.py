"""Injected port avoids importing agent/psyche domains from conversations."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class EfficacyFeedbackHooks(Protocol):
    async def apply(
        self, db: AsyncSession, user_id: UUID, message_id: UUID, verdict: str
    ) -> None: ...


_hooks: EfficacyFeedbackHooks | None = None


def register_efficacy_feedback_hooks(hooks: EfficacyFeedbackHooks) -> None:
    global _hooks
    _hooks = hooks


async def apply_efficacy_feedback(
    db: AsyncSession, user_id: UUID, message_id: UUID, verdict: str
) -> None:
    if _hooks is None:
        return
    try:
        async with db.begin_nested():
            await _hooks.apply(db, user_id, message_id, verdict)
    except Exception as exc:
        from src.infrastructure.observability.logging import get_logger

        get_logger(__name__).warning("efficacy_feedback_unavailable", error_type=type(exc).__name__)
