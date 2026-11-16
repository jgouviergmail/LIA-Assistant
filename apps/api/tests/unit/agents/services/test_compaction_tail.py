"""The tail a compaction keeps begins on the person's message (lot 16).

Measured 2026-11-15 on the recall bench (``task agents:compaction:measure``): with the
tail counted in messages, two of five fictional discussions kept a tail beginning
inside an exchange, the person's request summarised and LIA's answer kept. The summary
then reported the request as unanswered (« no result recorded »), and the response
model read an answer without its question. The tail keeps at least the configured
number of messages and extends back to the person's message of the exchange it would
cut: the documented contract (recent messages are never compacted), whole. The node,
the summary and the truncation fallback read the same rule.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)

from src.domains.agents.nodes.compaction_node import compaction_node
from src.domains.agents.services.compaction_service import (
    CompactionResult,
    CompactionService,
    SafetyCheckResult,
    compactable_messages,
)

pytestmark = pytest.mark.unit


def _exchange(name: str, tools: int = 0) -> list[BaseMessage]:
    """The person's message, a round of ``tools`` calls when any, and the answer."""
    messages: list[BaseMessage] = [HumanMessage(f"{name}?", id=f"{name}-person")]
    if tools:
        ids = [f"{name}-call-{n}" for n in range(tools)]
        messages.append(
            AIMessage(
                "",
                id=f"{name}-calls",
                tool_calls=[{"name": "t", "args": {}, "id": call} for call in ids],
            )
        )
        messages.extend(ToolMessage("{}", tool_call_id=call, id=f"{call}-result") for call in ids)
    messages.append(AIMessage(f"{name}.", id=f"{name}-answer"))
    return messages


def _ids(messages: list[BaseMessage]) -> list[str]:
    return [str(message.id) for message in messages]


#: A summary, a short exchange, one heavy in tool calls, and a short one.
_HISTORY: list[BaseMessage] = [
    SystemMessage("[Conversation history compacted — compaction #1.]", id="summary"),
    *_exchange("first"),
    *_exchange("search", tools=3),
    *_exchange("last"),
]


class TestTheRule:
    def test_a_cut_inside_an_exchange_moves_back_to_its_person_message(self) -> None:
        # Six messages kept would begin on a tool result of the « search » exchange.
        summarised = compactable_messages(_HISTORY, 6)

        assert _ids(summarised) == ["first-person", "first-answer"]

    def test_a_cut_on_a_person_message_stays(self) -> None:
        summarised = compactable_messages(_HISTORY, 2)

        assert _ids(summarised)[-1] == "search-answer"

    @pytest.mark.parametrize("preserve", range(1, 12))
    def test_whatever_the_setting_the_tail_is_whole_exchanges_and_at_least_kept(
        self, preserve: int
    ) -> None:
        non_system = [m for m in _HISTORY if not isinstance(m, SystemMessage)]
        summarised = compactable_messages(_HISTORY, preserve)
        kept = non_system[len(summarised) :]

        assert non_system[: len(summarised)] == summarised
        assert len(kept) >= min(preserve, len(non_system))
        assert not summarised or isinstance(kept[0], HumanMessage)

    def test_no_tail_kept_means_nothing_summarised(self) -> None:
        assert compactable_messages(_HISTORY, 0) == []
        assert compactable_messages(_exchange("only"), 5) == []


@pytest.fixture
def _writer() -> Iterator[None]:
    with patch(
        "src.domains.agents.nodes.compaction_node.get_stream_writer", return_value=MagicMock()
    ):
        yield


class TestEveryReaderAgrees:
    @pytest.mark.usefixtures("_writer")
    async def test_the_node_removes_exactly_what_the_rule_summarises(self) -> None:
        service = MagicMock()
        service.should_compact.return_value = True
        service.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        service.compact = AsyncMock(
            return_value=CompactionResult(
                summary="Recap.",
                tokens_before=900,
                tokens_after=50,
                tokens_saved=850,
                identifiers_preserved=[],
                strategy="single_chunk",
            )
        )
        state = {"messages": _HISTORY, "user_language": "en", "compaction_count": 1}

        with (
            patch(
                "src.domains.agents.nodes.compaction_node.CompactionService", return_value=service
            ),
            patch("src.domains.agents.nodes.compaction_node.settings") as settings,
        ):
            settings.compaction_enabled = True
            settings.compaction_preserve_recent_messages = 6
            settings.compaction_include_previous_summaries = False
            result = await compaction_node(state, config={})

        removed = [m.id for m in result["messages"] if isinstance(m, RemoveMessage)]
        assert removed == ["first-person", "first-answer"]

    def test_the_truncation_fallback_drops_what_the_rule_summarises(self) -> None:
        service = CompactionService()

        fallback = service._truncation_fallback(_HISTORY, 6, reason="timeout", zone=UTC)

        dropped = compactable_messages(_HISTORY, 6)
        assert fallback.tokens_before == service._token_counter.count_messages_tokens(dropped)
