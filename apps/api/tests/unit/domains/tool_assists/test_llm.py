"""One short structured call of an assist (ADR-372): who it asks, and who pays for it.

Every other test of the assists replaces this call. Here it is the real one, the model alone being
absent: the slot it names, that slot's short budget, the static rules travelling as the system
message, and the person's id and the run's config handed to the structured door, which answers to
both ceilings and bills on them (ADR-272, ADR-275).
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from src.core.constants import (
    DYNAMIC_CONTEXT_MARKER,
    TOOL_ASSIST_LLM_TYPE,
    TOOL_ASSIST_VISION_LLM_TYPE,
)
from src.domains.tool_assists import llm as assist_llm
from src.domains.tool_assists.door import AssistRun

pytestmark = pytest.mark.unit

PICTURE = b"\xff\xd8\xff a picture"
RULES = "The rules"
WORDS = "The person's words"


class _Answer(BaseModel):
    """What a call is asked to return."""

    text: str


@pytest.fixture
def door(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What reached the structured door, the client it was handed standing for the model."""
    seen: dict[str, Any] = {}

    def client_of(slot: str, config_override: dict[str, str]) -> str:
        seen.update(slot=slot, override=config_override)
        return f"the client of {slot}"

    def provider_of(config: object, slot: str) -> SimpleNamespace:
        return SimpleNamespace(provider=f"the provider of {slot}")

    async def structured(
        llm: str, messages: list[Any], schema: type[BaseModel], provider: str, **fields: Any
    ) -> _Answer:
        seen.update(fields, llm=llm, messages=messages, schema=schema, provider=provider)
        return _Answer(text="answered")

    monkeypatch.setattr(assist_llm, "get_llm", client_of)
    monkeypatch.setattr(assist_llm, "short_answer_config", lambda slot: {"short": slot})
    monkeypatch.setattr(assist_llm, "get_llm_config_for_agent", provider_of)
    monkeypatch.setattr(assist_llm, "get_structured_output", structured)
    return seen


def _run() -> AssistRun:
    return AssistRun(user_id=uuid4(), language="fr", config=RunnableConfig(callbacks=[]))


def _prompt() -> str:
    return f"{RULES}\n{DYNAMIC_CONTEXT_MARKER}\n{WORDS}"


async def test_a_call_asks_the_assists_slot_on_its_short_budget(door: dict[str, Any]) -> None:
    answer = await assist_llm.ask_slot(_run(), _prompt(), _Answer)

    assert answer.text == "answered"
    assert door["slot"] == TOOL_ASSIST_LLM_TYPE
    assert door["override"] == {"short": TOOL_ASSIST_LLM_TYPE}
    assert door["llm"] == f"the client of {TOOL_ASSIST_LLM_TYPE}"
    assert door["provider"] == f"the provider of {TOOL_ASSIST_LLM_TYPE}"
    assert door["schema"] is _Answer


@pytest.mark.parametrize(
    ("ask", "slot"),
    [
        (lambda run: assist_llm.ask_slot(run, _prompt(), _Answer), TOOL_ASSIST_LLM_TYPE),
        (
            lambda run: assist_llm.ask_slot_on_image(run, _prompt(), PICTURE, _Answer),
            TOOL_ASSIST_VISION_LLM_TYPE,
        ),
    ],
    ids=["words", "image"],
)
async def test_a_call_is_billed_to_the_person_on_the_run(
    door: dict[str, Any], ask: Any, slot: str
) -> None:
    """The door reads no owner from a config: without the id, nobody would answer for the call."""
    run = _run()

    await ask(run)

    assert door["user_id"] == str(run.user_id)
    assert door["config"] is run.config
    assert door["node_name"] == slot


async def test_the_rules_travel_as_the_system_message_and_the_words_below_them(
    door: dict[str, Any],
) -> None:
    await assist_llm.ask_slot(_run(), _prompt(), _Answer)

    rules, words = door["messages"]
    assert isinstance(rules, SystemMessage)
    assert isinstance(words, HumanMessage)
    assert RULES in str(rules.content)
    assert WORDS not in str(rules.content)
    assert WORDS in str(words.content)


async def test_a_picture_joins_the_words_on_the_vision_slot(door: dict[str, Any]) -> None:
    answer = await assist_llm.ask_slot_on_image(_run(), _prompt(), PICTURE, _Answer)

    assert answer.text == "answered"
    assert door["slot"] == TOOL_ASSIST_VISION_LLM_TYPE
    assert door["override"] == {"short": TOOL_ASSIST_VISION_LLM_TYPE}
    assert door["provider"] == f"the provider of {TOOL_ASSIST_VISION_LLM_TYPE}"
    rules, last = door["messages"]
    assert isinstance(rules, SystemMessage)
    assert isinstance(last, HumanMessage)
    words, image = last.content
    assert WORDS in words["text"]
    encoded = base64.b64encode(PICTURE).decode("ascii")
    assert image["image_url"]["url"] == f"data:image/jpeg;base64,{encoded}"


async def test_a_prompt_with_no_marker_still_carries_its_picture(door: dict[str, Any]) -> None:
    await assist_llm.ask_slot_on_image(_run(), WORDS, PICTURE, _Answer)

    (only,) = door["messages"]
    words, image = only.content
    assert words == {"type": "text", "text": WORDS}
    assert image["type"] == "image_url"
