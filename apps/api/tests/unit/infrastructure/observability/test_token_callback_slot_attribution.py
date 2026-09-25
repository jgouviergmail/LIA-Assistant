"""A model call is filed under the SLOT that configured it, never under the graph (B8).

The debug panel's « Slot » row read ``agent_graph`` on every call of a chat
turn: the orchestration service writes that value into the GRAPH's config
metadata, every node inherits it, and the token callback read it as the call's
slot — measured on dev 2026-09-24, router, planner, response and the extractions
all filed as « agent_graph », Qwen calls as « openai », DeepSeek ones as
« chat-deepseek ». The factory now stamps the slot and the provider on the model
itself, and LangChain merges a model's own metadata OVER its caller's.

The model name the provider REPORTS stays what is billed; the one the request
NAMED — the slot's configuration — now travels beside it: a provider resolving an
alias (a retired DeepSeek name) or answering under a dated snapshot made the
panel show a model nobody configured.

Proven with a real LangChain chat model and the real callback: only the tracker
is a double, and it records what it is handed.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.core.field_names import FIELD_LLM_PROVIDER, FIELD_LLM_TYPE
from src.infrastructure.observability.callbacks import TokenTrackingCallback

pytestmark = [pytest.mark.unit]


class _Tracker:
    """Records what the callback files, and nothing else."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record_node_tokens(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _ConfiguredFakeModel(GenericFakeChatModel):
    """A fake that names its model the way every real client does.

    ``ChatOpenAI(model=…)._get_invocation_params()`` carries ``model`` and
    ``model_name`` (probed); the stock fake carries neither, so it publishes its
    model through ``_identifying_params`` exactly like the real clients.
    """

    model: str = "deepseek-v4-flash"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model}


def _answer() -> AIMessage:
    return AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
        # The provider answers under its CURRENT name for the alias requested.
        response_metadata={"model_name": "deepseek-flash"},
    )


async def _call_under_the_graph_config(model: GenericFakeChatModel) -> dict[str, Any]:
    tracker = _Tracker()
    await model.ainvoke(
        "plan this",
        config={
            # What the orchestration service puts on the graph's config.
            "metadata": {FIELD_LLM_TYPE: "agent_graph"},
            "callbacks": [TokenTrackingCallback(tracker, "run-1")],  # type: ignore[arg-type]
        },
    )
    (call,) = tracker.calls
    return call


async def test_the_slot_the_model_carries_wins_over_the_graph_config() -> None:
    model = _ConfiguredFakeModel(
        messages=iter([_answer()]),
        metadata={FIELD_LLM_TYPE: "planner", FIELD_LLM_PROVIDER: "qwen"},
    )

    call = await _call_under_the_graph_config(model)

    assert call["llm_type"] == "planner"
    # The provider LIA configured, not the client class's family.
    assert call["params"].provider == "qwen"


async def test_the_requested_and_the_served_model_are_both_kept() -> None:
    model = _ConfiguredFakeModel(
        messages=iter([_answer()]),
        metadata={FIELD_LLM_TYPE: "memory_extraction", FIELD_LLM_PROVIDER: "deepseek"},
    )

    call = await _call_under_the_graph_config(model)

    # What the request named (the configuration) and what the provider
    # reported (what is billed) differ on an alias — both are true.
    assert call["requested_model"] == "deepseek-v4-flash"
    assert call["model_name"] == "deepseek-flash"


async def test_a_model_that_carries_no_slot_keeps_the_callers() -> None:
    """A model built outside the factory still reads the instrumented config."""
    model = _ConfiguredFakeModel(messages=iter([_answer()]))

    call = await _call_under_the_graph_config(model)

    assert call["llm_type"] == "agent_graph"
