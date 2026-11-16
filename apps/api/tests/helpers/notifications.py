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

from src.core.field_names import FIELD_CONVERSATION_ID, FIELD_RUN_ID
from src.infrastructure.proactive.notification import NotificationDispatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.conversation_target import ConversationOrigin
    from src.domains.users.models import User


@dataclass(frozen=True)
class SentNotification:
    """What one dispatch carried, as the SSE channel received it.

    ``run_id`` is the run the archived message names — what the chat meter
    joins the spend on — or None when the dispatch named none; ``discussion``
    the annex the live event names, or None for Main.
    """

    user_id: UUID
    content: str
    title: str
    task_type: str
    target_id: str
    run_id: str | None = None
    discussion: str | None = None


@dataclass
class ScriptedChannels:
    """What each channel answers, and what the dispatches carried.

    Attributes:
        archived: Whether the conversation archive accepts the message.
        fcm_success: Push deliveries the FCM channel reports.
        sse: Whether the SSE publish succeeds.
        channel_sent: Messages the external channels (Telegram…) report sent.
        archive_error: Raised by the archive step instead of answering.
        annex: The annex an origin resolves to (None: Main, or retired).
        sent: Every dispatch that reached the SSE step, in order.
        origins: The origin every archive was asked to publish on.
        push_links: The annex every push was asked to open.
    """

    archived: bool = True
    fcm_success: int = 0
    sse: bool = True
    channel_sent: int = 0
    archive_error: BaseException | None = None
    annex: UUID | None = None
    sent: list[SentNotification] = field(default_factory=list)
    origins: list[ConversationOrigin | None] = field(default_factory=list)
    push_links: list[UUID | None] = field(default_factory=list)


def sse_only() -> ScriptedChannels:
    """Channels where only the SSE publish succeeds: not a durable delivery."""
    return ScriptedChannels(archived=False, fcm_success=0, sse=True, channel_sent=0)


class ScriptedDispatcher(NotificationDispatcher):
    """The real dispatcher whose four channels answer what a test scripted."""

    def __init__(self, channels: ScriptedChannels, **flags: bool) -> None:
        super().__init__(**flags)
        self.channels = channels

    async def _archive_message(
        self,
        user: User,
        content: str,
        metadata: Mapping[str, object],
        db: AsyncSession,
        conversation_id: UUID | None = None,
        origin: ConversationOrigin | None = None,
    ) -> dict[str, object]:
        self.channels.origins.append(origin)
        if self.channels.archive_error is not None:
            raise self.channels.archive_error
        return {"archived": self.channels.archived, "conversation_id": None, "message_id": None}

    async def _annex_of(
        self, db: AsyncSession, owner_id: UUID, origin: ConversationOrigin | None
    ) -> UUID | None:
        return self.channels.annex if origin is not None else None

    async def _send_fcm(
        self,
        user: User,
        title: str,
        body: str,
        task_type: str,
        target_id: str,
        db: AsyncSession,
        run_id: str | None = None,
        discussion: UUID | None = None,
    ) -> dict[str, int]:
        self.channels.push_links.append(discussion)
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
        run_id = metadata.get(FIELD_RUN_ID)
        discussion = metadata.get(FIELD_CONVERSATION_ID)
        self.channels.sent.append(
            SentNotification(
                user_id,
                content,
                title,
                task_type,
                target_id,
                run_id if isinstance(run_id, str) else None,
                discussion if isinstance(discussion, str) else None,
            )
        )
        if not self.channels.sse:
            raise ConnectionError("SSE unavailable")

    async def _send_channels(
        self, user_id: UUID, title: str, body: str, task_type: str, target_id: str, language: str
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
