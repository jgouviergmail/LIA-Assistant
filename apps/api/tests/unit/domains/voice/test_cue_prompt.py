"""The cue block a spoken-comment writer reads states what the code enforces (ADR-345, ADR-284).

Three promises, each one a way the block could lie: it names exactly the cues
the engine that will speak performs (a cue it cannot perform would be dropped
in silence, the writer believing it was obeyed), its example shows one of them,
and the budget it publishes is the bound :class:`AuthoredCues` enforces.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.domains.voice import expressive_cues
from src.domains.voice import service as voice_service
from src.domains.voice.cue_prompt import expressive_cues_block
from src.domains.voice.expressive_cues import (
    DELIVERY_CUES,
    EVENT_CUES,
    FISH_S1_CUES,
    GEMINI_VOCAL_TAGS,
    NO_CUES,
    AuthoredCues,
    Cue,
    CueDialect,
)
from src.domains.voice.schemas import VoiceCommentRequest
from src.domains.voice.service import VoiceCommentService

pytestmark = pytest.mark.unit

#: Every dialect an engine is mapped to, the silent one included.
_DIALECTS = sorted(
    {dialect.name: dialect for *_, dialect in expressive_cues._RULES}.values(),
    key=lambda dialect: dialect.name,
)
_CUE_WORDS = re.compile(r"\[([^\[\]]+)\]")


def _listed(block: str, key_line_start: str) -> set[Cue]:
    lines = [line for line in block.splitlines() if line.startswith(key_line_start)]
    return {Cue(word) for line in lines for word in _CUE_WORDS.findall(line)}


@pytest.mark.parametrize("dialect", _DIALECTS, ids=lambda dialect: dialect.name)
def test_the_block_names_exactly_the_cues_the_engine_performs(dialect: CueDialect) -> None:
    block = expressive_cues_block(dialect, budget=2)

    assert _listed(block, "- How a sentence") == dialect.performs() & DELIVERY_CUES
    assert _listed(block, "- A sound") == dialect.performs() & EVENT_CUES


@pytest.mark.parametrize("dialect", _DIALECTS, ids=lambda dialect: dialect.name)
def test_the_example_shows_a_cue_the_engine_performs(dialect: CueDialect) -> None:
    example = next(
        line
        for line in expressive_cues_block(dialect, 2).splitlines()
        if line.startswith("Example")
    )

    assert _listed(example, "Example") <= dialect.performs()
    assert len(_listed(example, "Example")) == 1


def test_an_engine_without_warm_is_shown_a_delivery_it_performs() -> None:
    """Fish ``s1``'s fixed set has no warm: the example must not teach one."""
    block = expressive_cues_block(FISH_S1_CUES, 2)

    assert "[warm]" not in block
    assert "Example: [calm] " in block


def test_an_engine_with_sounds_only_is_never_told_about_delivery() -> None:
    block = expressive_cues_block(GEMINI_VOCAL_TAGS, 2)

    assert "How a sentence is said" not in block
    assert "Example: That one took a while [sighs]" in block


@pytest.mark.parametrize("budget", [0, -1])
def test_no_budget_or_no_cue_writes_no_block(budget: int) -> None:
    assert expressive_cues_block(expressive_cues.FISH_S2_CUES, budget) == ""
    assert expressive_cues_block(NO_CUES, 3) == ""


@pytest.mark.parametrize("budget", [1, 2, 5])
def test_the_published_budget_is_the_one_the_renderer_enforces(budget: int) -> None:
    dialect = expressive_cues.ELEVENLABS_AUDIO_TAGS
    published = re.search(r"Use at most (\d+) cues", expressive_cues_block(dialect, budget))
    assert published is not None

    over = " ".join(f"[{Cue.SIGHS.value}] word{index}." for index in range(budget + 3))
    spoken = AuthoredCues(dialect, budget).render(over)

    assert spoken.count("[sighs]") == int(published.group(1)) == budget


async def test_the_comment_prompt_carries_the_block_of_the_engine_that_speaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(voice_service, "get_llm", lambda llm_type: SimpleNamespace())
    request = VoiceCommentRequest(
        context_summary="Booked.",
        personality_instruction="",
        user_language="en",
        current_datetime="2026-10-14 09:00",
    )

    async def prompt_for(provider: str, model: str) -> str:
        service = VoiceCommentService()
        config = SimpleNamespace(provider=provider, model=model)
        client = SimpleNamespace(provider_name=provider)
        service._serve_tts = AsyncMock(return_value=(config, client))  # type: ignore[method-assign]
        return (await service._build_voice_llm_invocation(request))[1]

    expressive = await prompt_for("elevenlabs", "eleven_v4")
    plain = await prompt_for("elevenlabs", "eleven_multilingual_v2")

    budget = voice_service.settings.voice_expressive_cues_max
    assert (f"Use at most {budget} cues" in expressive) is (budget > 0)
    assert "<expressive_cues>" not in plain
    # The block comes after every rule it makes an exception to.
    if budget > 0:
        assert (
            expressive.index("</output_specifications>")
            < expressive.index("<expressive_cues>")
            < expressive.index("<execution_context>")
        )
