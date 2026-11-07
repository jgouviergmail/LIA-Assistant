"""What LIA says aloud from the Tools (ADR-372, lot 8).

The voice reads the words on the screen, up to its bound, on its own run: the reading says when it
stopped short and what it cost, and is never read as an answer that was merely held.
"""

from __future__ import annotations

import base64
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from src.core.constants import TOOL_ASSIST_READOUT_MAX_SENTENCES
from src.domains.tool_assists import speech
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.speech import read_aloud
from src.domains.voice.text_readout import TextReadout

pytestmark = pytest.mark.unit

PERSON = uuid4()


def _run() -> AssistRun:
    return AssistRun(user_id=PERSON, language="fr", config=RunnableConfig(callbacks=[]))


@pytest.fixture
def voice(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """What reached the voice."""
    heard: list[dict[str, Any]] = []

    async def synthesize(
        *, user_id: UUID, user_language: str, text: str, max_sentences: int, run_prefix: str
    ) -> TextReadout:
        heard.append({"user_id": user_id, "language": user_language, "text": text})
        heard[-1].update(max_sentences=max_sentences, run_prefix=run_prefix)
        return TextReadout(audio=b"ID3", cost_eur=0.002)

    monkeypatch.setattr(speech, "synthesize_user_text", synthesize)
    return heard


async def test_a_reading_the_voice_stopped_short_is_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def stopped(**_fields: Any) -> TextReadout:
        return TextReadout(audio=b"ID3", cost_eur=0.0, cut=True)

    monkeypatch.setattr(speech, "synthesize_user_text", stopped)

    heard = await read_aloud(_run(), "Hello there")

    assert heard.cut is True


async def test_the_words_on_the_screen_are_read_in_the_reader_s_language(
    voice: list[dict[str, Any]],
) -> None:
    run = _run()

    heard = await read_aloud(run, "Hello there")

    assert base64.b64decode(heard.audio) == b"ID3"
    assert heard.cut is False
    assert heard.cost_eur == 0.002
    assert run.served is True
    assert voice == [
        {
            "user_id": PERSON,
            "language": "fr",
            "text": "Hello there",
            "max_sentences": TOOL_ASSIST_READOUT_MAX_SENTENCES,
            "run_prefix": "tool_assist",
        }
    ]


async def test_past_its_bound_only_the_beginning_is_read_and_that_is_said(
    voice: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(speech.settings, "tool_assist_readout_max_chars", 5)

    heard = await read_aloud(_run(), "Hello there")

    assert voice[0]["text"] == "Hello"
    assert heard.cut is True
