"""The query analysis the auto-tool door refused on 2026-10-22, replayed.

Haiku 5.5 with thinking (a forced tool is refused there) answered a complete
analysis with one key the contract never declared, left empty, inside a
requested outcome: ``"source_quote_note": ""``. ``GoalRequirement`` forbids
extras, so the whole analysis was refused and the turn fell back to a bare
conversation without its tools. An empty key says nothing any reader could
read: it is dropped, and the analysis stands.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from src.domains.agents.services.analysis.query_analysis_schemas import QueryAnalysisOutput
from src.infrastructure.llm.structured_output import _get_native_structured_output

pytestmark = pytest.mark.unit


class _ThinkingClaude(FakeMessagesListChatModel):
    """The measured client: thinking on, so the forced tool is refused."""

    model_name: str = "claude-haiku-5-5"
    thinking: dict[str, str] = {"type": "adaptive"}

    def bind_tools(
        self,
        tools: Sequence[object],
        *,
        tool_choice: str | None = None,
        **kwargs: object,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self


async def test_the_refused_analysis_now_stands() -> None:
    args = {
        "intent": "action",
        "primary_domain": "calculation",
        "english_query": "Compute 1234 × 5678 with the calculation tool.",
        "reasoning": "Explicit arithmetic request with a tool.",
        "requested_outcomes": [
            {
                "domain": "calculation",
                "label": "product of two numbers",
                "source_quote": "Calcule 1234 × 5678",
                "kind": "read",
                "source_quote_note": "",
            }
        ],
    }
    answer = AIMessage(
        content="",
        tool_calls=[
            {"name": "QueryAnalysisOutput", "args": args, "id": "toolu_1", "type": "tool_call"}
        ],
    )
    analysis = await _get_native_structured_output(
        _ThinkingClaude(responses=[answer]),
        [HumanMessage(content="Calcule 1234 × 5678 avec l'outil de calcul.")],
        QueryAnalysisOutput,
        provider="anthropic",
    )
    assert analysis.intent == "action"
    assert [goal.source_quote for goal in analysis.requested_outcomes] == ["Calcule 1234 × 5678"]
