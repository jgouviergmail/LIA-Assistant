"""Voice-only exchanges reach the memory and the interests once, at the end,
under the person's switch, on the session's run id (ADR-299 R4, ADR-301 — one
learning for both carriers)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.infrastructure.scheduler.voice_session_closing import (
    schedule_voice_learning,
    voice_turn_messages,
)

pytestmark = pytest.mark.unit

MODULE = "src.infrastructure.scheduler.voice_session_closing"
ROWS = [("user", "a"), ("assistant", "b")]


def _tracking(tracking: object) -> None:
    tracking.return_value.__aenter__ = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    tracking.return_value.__aexit__ = AsyncMock(return_value=False)  # type: ignore[attr-defined]


def test_rows_become_messages_in_order_and_blanks_are_dropped() -> None:
    messages = voice_turn_messages([("user", "hello"), ("assistant", "hi"), ("user", "  ")])
    assert [type(m) for m in messages] == [HumanMessage, AIMessage]


async def test_nothing_runs_on_no_rows() -> None:
    with patch(f"{MODULE}.TrackingContext") as tracking:
        await schedule_voice_learning(
            user_id=uuid.uuid4(),
            memory_enabled=True,
            conversation_id=uuid.uuid4(),
            run_id="live_session_x",
            rows=[],
            language="fr",
            run_inline=True,
        )
    tracking.assert_not_called()


async def test_memory_is_skipped_when_the_person_switched_it_off() -> None:
    with (
        patch(f"{MODULE}.extract_memories_background", AsyncMock()) as memories,
        patch(f"{MODULE}.extract_interests_background", AsyncMock()) as interests,
        patch(f"{MODULE}.TrackingContext") as tracking,
    ):
        _tracking(tracking)
        await schedule_voice_learning(
            user_id=uuid.uuid4(),
            memory_enabled=False,
            conversation_id=uuid.uuid4(),
            run_id="live_session_x",
            rows=ROWS,
            language="fr",
            run_inline=True,
        )
    memories.assert_not_awaited()
    interests.assert_awaited_once()


async def test_both_run_under_the_session_run_id() -> None:
    with (
        patch(f"{MODULE}.extract_memories_background", AsyncMock(return_value=1)) as memories,
        patch(f"{MODULE}.extract_interests_background", AsyncMock(return_value=0)) as interests,
        patch(f"{MODULE}.TrackingContext") as tracking,
    ):
        _tracking(tracking)
        await schedule_voice_learning(
            user_id=uuid.uuid4(),
            memory_enabled=True,
            conversation_id=uuid.uuid4(),
            run_id="live_session_x",
            rows=ROWS,
            language="fr",
            run_inline=True,
        )
    assert memories.call_args.kwargs["parent_run_id"] == "live_session_x"
    assert interests.call_args.kwargs["parent_run_id"] == "live_session_x"
    assert tracking.call_args.args[0] == "live_session_x"


async def test_a_failing_extractor_never_raises() -> None:
    with (
        patch(f"{MODULE}.extract_memories_background", AsyncMock(side_effect=RuntimeError("x"))),
        patch(f"{MODULE}.TrackingContext") as tracking,
    ):
        _tracking(tracking)
        await schedule_voice_learning(
            user_id=uuid.uuid4(),
            memory_enabled=True,
            conversation_id=uuid.uuid4(),
            run_id="r",
            rows=ROWS,
            language="fr",
            run_inline=True,
        )
