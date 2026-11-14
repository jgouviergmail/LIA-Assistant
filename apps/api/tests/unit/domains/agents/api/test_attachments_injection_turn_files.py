"""The turn's files reach a skill command through the request, never past it (ADR-327 lot 2).

The attachment injection records what it read into the list the request bound;
a scheduler may run several people's turns one after another in one task, so a
list outside a bound request records nothing, and the reset forgets it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import (
    SkillTurnFile,
    bind_skill_context,
    reset_skill_context,
    skill_turn_files,
)
from src.core.conversation_target import ConversationRef
from src.domains.agents.api import attachments_injection
from src.domains.agents.api.attachments_injection import inject_attachments_into_state
from src.domains.agents.models import create_initial_state
from src.domains.attachments.models import Attachment
from tests.fixtures.conversation_cases import conversation_target

pytestmark = pytest.mark.unit

_OWNER = uuid.uuid4()
_ATTACHMENT = Attachment(
    id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
    user_id=_OWNER,
    content_type="document",
    original_filename="form.pdf",
    mime_type="application/pdf",
    file_path="u/stored.pdf",
    file_size=1234,
    extracted_text=None,
)


class _Service:
    """Only the file projection is doubled; the ownership/SQL boundary has real tests."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def accept_for_conversation(
        self, ids: list[uuid.UUID], user_id: uuid.UUID, target: ConversationRef
    ) -> list[Attachment]:
        assert user_id == target.owner_id == _OWNER
        assert ids == [_ATTACHMENT.id]
        return [_ATTACHMENT]


async def _inject() -> None:
    state = create_initial_state(_OWNER, "session", "r", user_language="en")
    state["messages"] = [HumanMessage(content="fill it")]

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as db:
            yield db

    with (
        patch.object(attachments_injection, "AttachmentService", _Service),
        patch.object(attachments_injection, "get_db_context", database),
    ):
        await inject_attachments_into_state(
            state=state,
            attachment_ids=[_ATTACHMENT.id],
            user_id=_OWNER,
            user_language="en",
            run_id="r",
            target=conversation_target(_OWNER, uuid.uuid4()),
        )


async def test_the_injected_files_are_the_turns_files() -> None:
    tokens = bind_skill_context(set(), frozenset())
    try:
        await _inject()
        assert skill_turn_files() == (
            SkillTurnFile(
                attachment_id=str(_ATTACHMENT.id),
                filename="form.pdf",
                file_path="u/stored.pdf",
                size=1234,
            ),
        )
    finally:
        reset_skill_context(tokens)
    assert skill_turn_files() == ()


async def test_outside_a_request_nothing_is_recorded() -> None:
    await _inject()
    assert skill_turn_files() == ()
