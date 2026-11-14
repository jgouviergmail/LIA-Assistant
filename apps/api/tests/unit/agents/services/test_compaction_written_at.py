"""A compaction summary keeps WHEN each message was written (lot 17).

The summary replaces the messages it covers: if its model never read their
moments, « the dentist tomorrow », said days ago, would come back undated in
every later turn — the defect the stamps remove, reintroduced by compaction.
Its prompt already turns a relative date into an absolute one « whenever the
conversation states the reference date »: each stamp is that reference.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.domains.agents.nodes.compaction_node import compaction_node
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.compaction_service import (
    CompactionResult,
    CompactionService,
    SafetyCheckResult,
)
from src.infrastructure.llm.message_view import stamped_now

pytestmark = pytest.mark.unit

TOKYO = ZoneInfo("Asia/Tokyo")
TUESDAY = datetime(2026, 11, 10, 0, 12, tzinfo=UTC)  # Tue 10 Nov 2026, 09:12 in Tokyo


def test_each_message_reaches_the_summarizer_with_its_moment() -> None:
    service = CompactionService(token_counter=MagicMock())
    chunk = [
        stamped_now(HumanMessage("I have the dentist tomorrow at 10."), TUESDAY),
        AIMessage("Noted."),
    ]

    text = service._format_messages_for_summary(chunk, zone=TOKYO)

    assert (
        text == "[human] [Tue 10 Nov 2026, 09:12] I have the dentist tomorrow at 10.\n\n[ai] Noted."
    )


def test_the_summarizer_is_told_what_the_stamp_is() -> None:
    assert "date and time it was written, in brackets" in load_prompt("compaction_prompt")


@pytest.fixture
def _writer() -> Any:
    with patch(
        "src.domains.agents.nodes.compaction_node.get_stream_writer", return_value=MagicMock()
    ):
        yield


@pytest.mark.usefixtures("_writer")
async def test_the_node_compacts_in_the_zone_its_state_holds() -> None:
    service = MagicMock()
    service.should_compact.return_value = True
    service.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
    service.compact = AsyncMock(
        return_value=CompactionResult(
            summary="Summary.",
            tokens_before=10,
            tokens_after=1,
            tokens_saved=9,
            identifiers_preserved=[],
            strategy="single_chunk",
        )
    )
    state = {
        "messages": [
            SystemMessage("System", id="s1"),
            HumanMessage("One", id="h1"),
            AIMessage("Two", id="a1"),
            HumanMessage("Three", id="h2"),
        ],
        "user_language": "en",
        "user_timezone": "Asia/Tokyo",
        "compaction_count": 0,
        "pending_draft_critique": None,
    }

    with (
        patch("src.domains.agents.nodes.compaction_node.settings") as node_settings,
        patch("src.domains.agents.nodes.compaction_node.CompactionService", return_value=service),
    ):
        node_settings.compaction_enabled = True
        node_settings.compaction_preserve_recent_messages = 2
        await compaction_node(state, config={})

    assert service.compact.await_args.kwargs["zone"] == TOKYO
