"""Announce a settled voice relay through the person's existing SSE channel."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n_live import get_live_phrases
from src.domains.users.models import User
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.proactive.notification import NotificationDispatcher

logger = structlog.get_logger(__name__)


async def notify_relay(db: AsyncSession, user: User, session: VoiceSession, relay: str) -> None:
    """Publish the relay outcome after releasing the caller's transaction."""
    await db.commit()
    phrases = get_live_phrases(session.language)
    try:
        await NotificationDispatcher(
            fcm_enabled=False, channel_enabled=False, archive_enabled=False, sse_enabled=True
        ).dispatch(
            user=user,
            content=phrases[f"relay_{relay}"],
            task_type=session.origin_kind,
            target_id=session.origin_id,
            metadata={
                "event": "live_relay",
                "relay": relay,
                "session_id": session.origin_id,
                "conversation_id": str(session.conversation_id),
            },
            db=db,
            title=phrases["summary_title"],
            commit_before_notification=False,
            push_enabled=False,
        )
    except Exception as exc:  # noqa: BLE001 — a notice failing never undoes the turn
        logger.warning(
            "voice_direct_relay_notice_failed",
            origin_id=session.origin_id,
            error_type=type(exc).__name__,
        )
