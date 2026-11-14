"""The person's message enters the state carrying the instant it was written (lot 17).

Every later turn reads it with that instant (``message_view.with_written_at``):
a message that loses it on the way — rebuilt for its attachments, replaced by a
reformulation — reads as if said just now.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from src.domains.agents.services.orchestration.person_message import person_message
from src.domains.agents.services.orchestration.service import OrchestrationService
from src.infrastructure.llm.message_view import WRITTEN_AT_KEY, written_at

pytestmark = pytest.mark.unit


def test_the_persons_message_carries_the_instant_it_was_written() -> None:
    before = datetime.now(UTC)

    message = person_message("Hello")

    assert isinstance(message, HumanMessage) and message.content == "Hello"
    moment = written_at(message)
    assert moment is not None and before <= moment <= datetime.now(UTC)


async def test_an_answer_to_a_question_enters_the_state_with_its_instant() -> None:
    resume: dict[str, Any] = {"decision": "APPROVE", "_user_message": "yes"}

    command = await OrchestrationService()._build_hitl_resume_command(
        None, resume, {"configurable": {}}, "run-1"
    )

    (message,) = command.update["messages"]
    assert message.content == "yes" and written_at(message) is not None


async def test_attachments_rebuild_the_message_without_losing_its_instant() -> None:
    from src.domains.agents.api import attachments_injection

    stamped = person_message("Look at this")
    state: dict[str, Any] = {"messages": [stamped], "metadata": {}}

    attachments_injection._annotate_last_human(state, "[1 image attached]")

    (message,) = state["messages"]
    assert message.content == "Look at this\n\n[1 image attached]"
    assert message.id == stamped.id
    assert message.additional_kwargs[WRITTEN_AT_KEY] == stamped.additional_kwargs[WRITTEN_AT_KEY]
