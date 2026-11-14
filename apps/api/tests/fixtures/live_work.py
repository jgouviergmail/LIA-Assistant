"""Detached admission doubles for provider unit tests; native tests exercise SQL ownership."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.core.conversation_execution import ExecutionKind, ReservedWork, RunAdmission
from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.reservation_work import reservation_work_scope
from src.domains.live.service import LiveService
from src.domains.users.models import User


def _work(user_id: UUID, target_id: UUID, revision: int, session_id: str) -> ReservedWork:
    """Provide a complete server-owned identity, never a loose dictionary or cast."""
    target = ConversationRef(user_id, target_id, ConversationKind.MAIN, revision, uuid4())
    admission = RunAdmission(
        uuid4(),
        target,
        ExecutionKind.LIVE,
        f"live_session_{session_id}",
        session_id,
        uuid4(),
        uuid4(),
        1,
        False,
    )
    return ReservedWork(admission, uuid4(), uuid4(), uuid4(), "request")


@pytest.fixture
def detached_live_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate provider policy tests from SQL; test_bound_archive uses the real service and DB."""
    primary_id = uuid4()

    async def prepare_owner(owner: UUID) -> None:
        """Provider unit tests contain no legacy SQL reservation."""

    monkeypatch.setattr("src.domains.live.session_start.prepare_live_retirement", prepare_owner)

    async def provider_ready() -> None:
        """Native tests cover the SQL fence; this suite exercises provider decisions."""

    monkeypatch.setattr("src.domains.live.service.require_live_work", provider_ready)

    @asynccontextmanager
    async def session_scope(
        service: LiveService, user: User, session_id: str, *, language: str, closing: bool = False
    ) -> AsyncIterator[ReservedWork]:
        record = await service._owned_record(user, session_id, language=language)
        target_id = record.lia_conversation_id or primary_id
        work = _work(user.id, target_id, record.lia_conversation_revision or 0, session_id)
        with reservation_work_scope(work):
            yield work

    @asynccontextmanager
    async def opening_scope(
        service: LiveService,
        user: User,
        selection: ConversationSelection,
        *,
        session_id: str,
        run_id: str,
        language: str,
    ) -> AsyncIterator[ReservedWork]:
        target_id = selection.conversation_id or primary_id
        work = _work(user.id, target_id, selection.conversation_revision or 0, session_id)
        with reservation_work_scope(work):
            yield work

    monkeypatch.setattr("src.domains.live.service.session_work", session_scope)
    monkeypatch.setattr("src.domains.live.session_start.opening_work", opening_scope)
    monkeypatch.setattr(
        "src.domains.conversations.reservation_repository.ConversationReservationRepository.take_standby_recaps",
        AsyncMock(return_value=[]),
    )
