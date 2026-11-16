"""A notification archived under a run names its bill's discussion (2026-11-14).

A call's or a meeting's spend is billed before any discussion is known; the
dispatcher writes its return where the act began. The bill joins that
discussion in the same transaction, so the bubble shows the cost there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_publication import OriginPublication
from src.domains.conversations import run_bills
from src.domains.conversations import service as conversation_service
from src.infrastructure.proactive.notification import NotificationDispatcher

pytestmark = pytest.mark.unit


@dataclass
class _Archived:
    """The discussion each archive landed in, and every bill named."""

    discussion: UUID = field(default_factory=uuid4)
    bills: list[tuple[UUID, str, UUID]] = field(default_factory=list)


def _install(monkeypatch: pytest.MonkeyPatch, archived: _Archived) -> None:
    class _Service:
        async def get_or_create_conversation(
            self, user_id: UUID, db: AsyncSession, *, language: str | None
        ) -> SimpleNamespace:
            del user_id, db, language
            return SimpleNamespace(id=uuid4())

        async def archive_message(
            self,
            conversation_id: OriginPublication,
            role: str,
            content: str,
            metadata: dict[str, object],
            db: AsyncSession,
        ) -> SimpleNamespace:
            del conversation_id, role, content, metadata, db
            return SimpleNamespace(id=uuid4(), conversation_id=archived.discussion)

    async def _attach(
        db: AsyncSession,
        *,
        owner_id: UUID,
        run_id: str,
        conversation_id: UUID,
        revision: int | None = None,
    ) -> bool:
        del db
        assert revision is None  # the words were just written, in this transaction
        archived.bills.append((owner_id, run_id, conversation_id))
        return True

    monkeypatch.setattr(conversation_service, "ConversationService", _Service)
    monkeypatch.setattr(run_bills, "attach_run_bill", _attach)


def _archive_only() -> NotificationDispatcher:
    """A dispatcher that archives and sends nothing."""
    return NotificationDispatcher(fcm_enabled=False, sse_enabled=False, channel_enabled=False)


async def test_a_return_archived_under_a_run_names_the_bill_where_it_was_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archived = _Archived()
    _install(monkeypatch, archived)
    owner = SimpleNamespace(id=uuid4(), language="fr")

    result = await _archive_only().dispatch(
        user=owner,
        content="I called the garage.",
        task_type="phone_call",
        target_id=str(uuid4()),
        metadata={},
        db=AsyncSession(),  # never reached: the archive and the bill are fakes
        run_id="phone_call_abc",
        commit_before_notification=False,
    )

    assert result.conversation_id == archived.discussion
    assert archived.bills == [(owner.id, "phone_call_abc", archived.discussion)]


async def test_a_message_with_no_run_names_no_bill(monkeypatch: pytest.MonkeyPatch) -> None:
    archived = _Archived()
    _install(monkeypatch, archived)

    result = await _archive_only().dispatch(
        user=SimpleNamespace(id=uuid4(), language="fr"),
        content="A reminder.",
        task_type="reminder",
        target_id=str(uuid4()),
        metadata={},
        db=AsyncSession(),
        commit_before_notification=False,
    )

    assert result.archived
    assert archived.bills == []
