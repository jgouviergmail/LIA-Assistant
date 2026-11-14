"""Every post-response extraction is handed the turn's zone (ADR-381 amendment).

The four background extractions stamp the exchange and write their present in the
person's zone; the zone they read is the one the turn ran in (``user_timezone`` of
the state), never a default chosen on the way.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from langchain_core.messages import HumanMessage

from src.domains.agents.nodes.post_response_extractions import (
    _schedule_post_response_extractions,
)
from tests.helpers.runtime_context import installed_runtime_context, make_runtime_context

pytestmark = pytest.mark.unit

_MODULE = "src.domains.agents.nodes.post_response_extractions"


def _recorder(received: dict[str, object], name: str) -> Callable[..., Coroutine[Any, Any, int]]:
    def call(*_args: object, **kwargs: object) -> Coroutine[Any, Any, int]:
        received[name] = kwargs.get("user_timezone", "NOT PASSED")

        async def done() -> int:
            return 0

        return done()

    return call


def test_the_four_extractions_receive_the_turns_zone() -> None:
    received: dict[str, object] = {}

    def fire_and_forget(coro: Coroutine[Any, Any, object], **_kwargs: object) -> None:
        coro.close()

    context = make_runtime_context(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        thread_id="thread-1",
        conversation_id="thread-1",
        is_automated_source=False,
        memory_enabled=True,
        journals_enabled=True,
        psyche_enabled=False,
    )
    state = {
        "messages": [HumanMessage(content="je dois rappeler le plombier demain matin")],
        "user_timezone": "Pacific/Auckland",
    }
    with (
        installed_runtime_context(context),
        patch(f"{_MODULE}.safe_fire_and_forget", side_effect=fire_and_forget),
        patch(
            f"{_MODULE}.settings",
            SimpleNamespace(
                open_loops_enabled=True,
                habits_enabled=False,
                journals_enabled=True,
                psyche_enabled=False,
            ),
        ),
        patch(f"{_MODULE}.extract_memories_background", _recorder(received, "memory")),
        patch(f"{_MODULE}.extract_interests_background", _recorder(received, "interests")),
        patch(f"{_MODULE}.extract_open_loops_background", _recorder(received, "open_loops")),
        patch(
            "src.domains.journals.extraction_service.extract_journal_entry_background",
            _recorder(received, "journal"),
        ),
    ):
        _schedule_post_response_extractions(
            state,
            {"configurable": {"thread_id": "thread-1"}},
            "run-1",
            user_msg_is_trivial=False,
            personality_instruction=None,
            user_message_embedding=None,
            user_language="fr",
            final_content="Noté !",
            previous_journal_injected_ids=[],
            psyche_appraisal=None,
        )

    assert received == {
        "memory": "Pacific/Auckland",
        "interests": "Pacific/Auckland",
        "open_loops": "Pacific/Auckland",
        "journal": "Pacific/Auckland",
    }
