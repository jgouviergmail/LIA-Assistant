"""The history summarizer of the generic agents writes with the ``compaction`` slot.

It used to name a model of its own in a setting (``SUMMARIZATION_MODEL``) and to
ask for the OpenAI key: one more model chosen outside the administration screen,
which an installation holding no OpenAI key could not call. « Context
Compaction » is the slot where that model is chosen (owner decision 2026-11-11).

The summarizer asks the factory for it at EACH summary. The agents that carry it
are built once per process, so a model held from their construction would keep
answering after an administrator moved the slot. And the call takes the slot's
own retry policy, never the blanket retry the library wraps its model in, which
relaunches a generation whose outcome is unknown (ADR-221).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.core.config import settings
from src.domains.agents.sms.model_middleware import SmsSafeSummarization
from src.infrastructure.llm import middleware_config, slot_summarization
from src.infrastructure.llm.middleware_config import (
    _create_summarization_middleware,
    create_agent_middleware_stack,
)
from src.infrastructure.llm.slot_summarization import (
    SUMMARIZATION_LLM_TYPE,
    SlotSummarizationMiddleware,
)

pytestmark = pytest.mark.unit

_HISTORY: list[BaseMessage] = [
    HumanMessage(content="What did we decide for Thursday?"),
    AIMessage(content="The review moves to ten."),
]

#: Which scribe wrote, in call order.
_wrote: list[str] = []


class _Scribe(BaseChatModel):
    """A chat model that signs its one answer, or times out."""

    label: str
    times_out: bool = False

    @property
    def _llm_type(self) -> str:
        return "scribe"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        _wrote.append(self.label)
        if self.times_out:
            raise TimeoutError("the provider did not answer in time")
        answer = AIMessage(content=f"summary by {self.label}")
        return ChatResult(generations=[ChatGeneration(message=answer)])


class _Door:
    """Stands where ``get_llm`` stands: records the slot asked, hands the model in force."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.model: BaseChatModel = _Scribe(label="first")

    def __call__(self, llm_type: str) -> BaseChatModel:
        self.asked.append(llm_type)
        return self.model


@pytest.fixture
def door(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Door]:
    _wrote.clear()
    stand_in = _Door()
    monkeypatch.setattr(slot_summarization, "get_llm", stand_in)
    yield stand_in
    _wrote.clear()


def _summarizer() -> SlotSummarizationMiddleware:
    middleware = _create_summarization_middleware()
    assert isinstance(middleware, SlotSummarizationMiddleware)
    return middleware


def test_the_slot_is_context_compaction() -> None:
    assert SUMMARIZATION_LLM_TYPE == "compaction"


def test_the_summary_is_written_by_the_compaction_slot(door: _Door) -> None:
    summary = _summarizer()._create_summary(_HISTORY)

    assert summary == "summary by first"
    assert set(door.asked) == {"compaction"}


def test_a_slot_moved_after_the_agent_was_built_is_followed(door: _Door) -> None:
    """Agents are built once per process: the summarizer must not keep the model
    the slot named that day."""
    summarizer = _summarizer()

    door.model = _Scribe(label="second")

    assert summarizer._create_summary(_HISTORY) == "summary by second"
    assert _wrote == ["second"]


async def test_the_asynchronous_summary_takes_the_same_door(door: _Door) -> None:
    summarizer = _summarizer()
    door.model = _Scribe(label="second")

    assert await summarizer._acreate_summary(_HISTORY) == "summary by second"


def test_a_summary_whose_outcome_is_unknown_is_asked_once(door: _Door) -> None:
    """The library wraps its model in a retry that relaunches on ANY failure; the
    slot's client carries the one policy, which never relaunches a timeout."""
    summarizer = _summarizer()
    door.model = _Scribe(label="slow", times_out=True)

    with pytest.raises(TimeoutError):
        summarizer._create_summary(_HISTORY)

    assert _wrote == ["slow"]


def test_the_summarizer_the_agents_carry_is_a_slot_summarizer(door: _Door) -> None:
    assert issubclass(SmsSafeSummarization, SlotSummarizationMiddleware)

    stack = create_agent_middleware_stack("query_agent", summarization_class=SmsSafeSummarization)
    summarizers = [m for m in stack if isinstance(m, SlotSummarizationMiddleware)]

    assert len(summarizers) == 1
    assert isinstance(summarizers[0], SmsSafeSummarization)
    assert summarizers[0]._create_summary(_HISTORY) == "summary by first"


def test_no_model_is_named_outside_the_slot() -> None:
    """The setting and its default are gone, and the stack no longer calls the generic
    builder the summarizer's model was made with (``init_chat_model``)."""
    import src.core.constants as constants

    assert not hasattr(settings, "summarization_model")
    assert not hasattr(constants, "SUMMARIZATION_MODEL_DEFAULT")

    tree = ast.parse(Path(middleware_config.__file__).read_text(encoding="utf-8"))
    called = {
        node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "init_chat_model" not in called
