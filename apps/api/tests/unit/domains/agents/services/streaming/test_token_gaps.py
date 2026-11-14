"""The gap between two answer tokens is clocked on every stream (lot 26 follow-up).

Every chunk of the main streaming loop passes ONE hook (``_track_and_observe``):
the stream's clock reads the answer tokens there, so a stall — a long gap no timeout
ends — shows in ``sse_token_gap_seconds`` instead of hiding inside a long answer.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from src.domains.agents.services.streaming.latency_sli import TokenGapClock
from src.domains.agents.services.streaming.service import StreamingService
from tests.fixtures.conversation_cases import streaming_target

pytestmark = pytest.mark.unit


async def test_the_gap_between_two_streamed_tokens_is_clocked() -> None:
    service = StreamingService()
    instants = iter([1.0, 1.4, 99.0])
    gaps: list[float] = []
    service.token_gaps = TokenGapClock(observe=gaps.append, now=lambda: next(instants))

    async def graph_stream():  # noqa: ANN202 — a LangGraph stream double
        yield ("messages", (MagicMock(content="Hello"), {"langgraph_node": "response"}))
        yield ("messages", (MagicMock(content=" world"), {"langgraph_node": "response"}))
        yield ("__end__", {})

    async for _chunk, _content in service.stream_sse_chunks(
        graph_stream(), streaming_target(uuid.uuid4()), "run-token-gaps"
    ):
        pass

    assert gaps == pytest.approx([0.4])


def test_each_stream_has_its_own_clock() -> None:
    first, second = StreamingService(), StreamingService()
    assert isinstance(first.token_gaps, TokenGapClock)
    assert first.token_gaps is not second.token_gaps
