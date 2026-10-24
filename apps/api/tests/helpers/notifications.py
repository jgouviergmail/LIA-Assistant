"""A notification dispatcher over scripted channels, with the real verdict (audit AC-003).

Five consumers wrote « delivered » without reading what ``dispatch`` returned, and
their tests could not have caught it: every double answered ``None``. This double
runs the REAL ``NotificationDispatcher.dispatch`` — its channel order, its archive
commit, its durable predicate — over channels each test scripts, so a consumer is
proven against what a dispatch actually answers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from src.infrastructure.proactive.notification import NotificationDispatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.users.models import User


@dataclass(frozen=True)
class SentNotification:
    """What one dispatch carried, as the SSE channel received it."""

    user_id: UUID
    content: str
    title: str
    task_type: str
    target_id: str


@dataclass
class ScriptedChannels:
    """What each channel answers, and what the dispatches carried.

    Attributes:
        archived: Whether the conversation archive accepts the message.
        fcm_success: Push deliveries the FCM channel reports.
        sse: Whether the SSE publish succeeds.
        channel_sent: Messages the external channels (Telegram…) report sent.
        archive_error: Raised by the archive step instead of answering.
        sent: Every dispatch that reached the SSE step, in order.
    """

    archived: bool = True
    fcm_success: int = 0
    sse: bool = True
    channel_sent: int = 0
    archive_error: BaseException | None = None
    sent: list[SentNotification] = field(default_factory=list)


def sse_only() -> ScriptedChannels:
    """Channels where only the SSE publish succeeds: not a durable delivery."""
    return ScriptedChannels(archived=False, fcm_success=0, sse=True, channel_sent=0)


class ScriptedDispatcher(NotificationDispatcher):
    """The real dispatcher whose four channels answer what a test scripted."""

    def __init__(self, channels: ScriptedChannels, **flags: bool) -> None:
        super().__init__(**flags)
        self.channels = channels

    async def _archive_message(
        self, user: User, content: str, metadata: Mapping[str, object], db: AsyncSession
    ) -> dict[str, object]:
        if self.channels.archive_error is not None:
            raise self.channels.archive_error
        return {"archived": self.channels.archived, "conversation_id": None, "message_id": None}

    async def _send_fcm(
        self,
        user: User,
        title: str,
        body: str,
        task_type: str,
        target_id: str,
        db: AsyncSession,
        run_id: str | None = None,
    ) -> dict[str, int]:
        return {"success": self.channels.fcm_success, "failed": 0}

    async def _publish_sse(
        self,
        user_id: UUID,
        content: str,
        title: str,
        task_type: str,
        target_id: str,
        metadata: Mapping[str, object],
    ) -> None:
        self.channels.sent.append(SentNotification(user_id, content, title, task_type, target_id))
        if not self.channels.sse:
            raise ConnectionError("SSE unavailable")

    async def _send_channels(
        self, user_id: UUID, title: str, body: str, task_type: str, target_id: str
    ) -> int:
        return self.channels.channel_sent


def scripted_dispatcher(channels: ScriptedChannels) -> Callable[..., ScriptedDispatcher]:
    """What a test installs in place of the class: the consumer builds its own.

    Args:
        channels: The answers every dispatcher the consumer builds will give.

    Returns:
        A callable taking the dispatcher's own flags, like the real constructor.
    """

    def build(**flags: bool) -> ScriptedDispatcher:
        return ScriptedDispatcher(channels, **flags)

    return build
