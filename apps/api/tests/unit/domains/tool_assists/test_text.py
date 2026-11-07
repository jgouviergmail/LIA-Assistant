"""What LIA writes on words a person is writing (ADR-372, lot 3).

Each helper fills its versioned prompt and asks once; the words are data below the marker, never
beside the rules; and an empty answer is a failure, never an empty proposal.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.core.exceptions import BaseAPIException
from src.domains.tool_assists import text
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.text import (
    RewriteTone,
    WritingKind,
    WrittenText,
    rewrite_text,
    translate_text,
    write_text,
)

pytestmark = pytest.mark.unit


def _run() -> AssistRun:
    return AssistRun(user_id=uuid4(), language="fr", config=RunnableConfig(callbacks=[]))


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every prompt that reached the slot, answered with a fixed text."""
    prompts: list[str] = []

    async def answer(run: AssistRun, rendered: str, schema: type[Any]) -> WrittenText:
        prompts.append(rendered)
        return WrittenText(text="  Better words.  ")

    monkeypatch.setattr(text, "ask_slot", answer)
    return prompts


def _data(prompt: str) -> str:
    """What stands below the marker: the only part a call changes."""
    return prompt.split(DYNAMIC_CONTEXT_MARKER, 1)[1]


@pytest.mark.parametrize("tone", list(RewriteTone))
async def test_a_rewrite_names_its_change_and_carries_the_words_as_data(
    asked: list[str], tone: RewriteTone
) -> None:
    words = await rewrite_text(_run(), "my words {not a field}", tone)

    assert words == "Better words."
    assert f"The change: {tone.value}" in _data(asked[0])
    assert "my words {not a field}" in _data(asked[0])


def test_the_prompt_defines_every_change_a_person_can_ask() -> None:
    from src.domains.agents.prompts import load_prompt

    rules = load_prompt("tool_assist_rewrite_prompt").split(DYNAMIC_CONTEXT_MARKER, 1)[0]

    assert all(f"- {tone.value}:" in rules for tone in RewriteTone)


def test_the_prompt_defines_every_kind_of_text() -> None:
    from src.domains.agents.prompts import load_prompt

    rules = load_prompt("tool_assist_write_prompt").split(DYNAMIC_CONTEXT_MARKER, 1)[0]

    assert all(f"- {kind.value}:" in rules for kind in WritingKind)


async def test_a_translation_goes_to_the_language_asked(asked: list[str]) -> None:
    await translate_text(_run(), "Bonjour", "Spanish")

    assert "Target language: Spanish" in _data(asked[0])
    assert "Bonjour" in _data(asked[0])


async def test_a_text_is_written_in_the_person_s_language_from_their_words(
    asked: list[str],
) -> None:
    await write_text(_run(), WritingKind.AUTO_REPLY, "away until Monday")

    data = _data(asked[0])
    assert "The kind of text: auto_reply" in data
    assert "away until Monday" in data
    assert "Language: " in data


@pytest.mark.parametrize(
    "call",
    [
        lambda run: rewrite_text(run, "words", RewriteTone.FIX),
        lambda run: translate_text(run, "words", "Spanish"),
        lambda run: write_text(run, WritingKind.DOCUMENT, "words"),
    ],
)
async def test_an_empty_answer_is_a_failure(monkeypatch: pytest.MonkeyPatch, call: Any) -> None:
    async def blank(run: AssistRun, rendered: str, schema: type[Any]) -> WrittenText:
        return WrittenText(text="   ")

    monkeypatch.setattr(text, "ask_slot", blank)

    with pytest.raises(BaseAPIException) as refused:
        await call(_run())

    assert isinstance(refused.value.detail, dict)
    assert refused.value.detail["code"] == "assist_failed"
