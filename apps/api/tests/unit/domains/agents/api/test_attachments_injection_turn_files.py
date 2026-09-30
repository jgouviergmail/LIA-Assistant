"""The turn's files reach a skill command through the request, never past it (ADR-327 lot 2).

The attachment injection records what it read into the list the request bound;
a scheduler may run several people's turns one after another in one task, so a
list outside a bound request records nothing, and the reset forgets it.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from src.core.context import (
    SkillTurnFile,
    bind_skill_context,
    reset_skill_context,
    skill_turn_files,
)
from src.domains.agents.api.attachments_injection import inject_attachments_into_state

pytestmark = pytest.mark.unit

_ATTACHMENT = SimpleNamespace(
    id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
    content_type="document",
    original_filename="form.pdf",
    mime_type="application/pdf",
    file_path="u/stored.pdf",
    file_size=1234,
    extracted_text=None,
)


class _Service:
    def __init__(self, db: Any) -> None:
        pass

    async def get_batch(self, ids: Any, user_id: Any) -> list[Any]:
        return [_ATTACHMENT]


async def _inject() -> None:
    state: dict[str, Any] = {"messages": [HumanMessage(content="fill it")], "metadata": {}}
    with patch("src.domains.attachments.service.AttachmentService", _Service):
        await inject_attachments_into_state(
            state=state,
            attachment_ids=[_ATTACHMENT.id],
            user_id=uuid.uuid4(),
            user_language="en",
            run_id="r",
            db=None,
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
