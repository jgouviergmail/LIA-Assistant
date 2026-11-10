"""How a voice session's engine expresses itself (ADR-373): words alone, or LIA's cues.

An ElevenLabs agent speaks through the engine its stored configuration
names: a realtime model (the vendor then manages the speech model and the
expressive mode, and measured on 2026-11-07 it applied the suggested tags),
else its TTS model — the v3 and v4 families perform audio tags unless the
person switched the expressive mode off. Anything else, or a configuration
LIA cannot read, is words alone: a cue LIA cannot prove the engine performs
is never offered.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.voice.expressive_cues import (
    DELIVERY_CUES,
    ELEVENLABS_AGENT_TAGS,
    EVENT_CUES,
    NO_CUES,
    PERSONA_CUES,
    Cue,
    CueDialect,
)
from src.domains.voice_sessions.expression import (
    PERSON_CUES,
    STRANGER_CUES,
    agent_dialect,
    invented_cues,
    palette_block,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            {
                "realtime_model": "eleven_realtime_v1_max",
                "tts": {"model_id": "eleven_flash_v2_5", "expressive_mode": False},
            },
            ELEVENLABS_AGENT_TAGS,
        ),
        ({"tts": {"model_id": "eleven_v4_turbo"}}, ELEVENLABS_AGENT_TAGS),
        (
            {"tts": {"model_id": "eleven_v3_conversational", "expressive_mode": True}},
            ELEVENLABS_AGENT_TAGS,
        ),
        ({"tts": {"model_id": "eleven_v4_turbo", "expressive_mode": False}}, NO_CUES),
        ({"tts": {"model_id": "eleven_flash_v2_5"}}, NO_CUES),
        ({"realtime_model": None, "tts": {"model_id": "eleven_turbo_v2_5"}}, NO_CUES),
        ({"realtime_model": "", "tts": {"model_id": "eleven_v4_turbo"}}, ELEVENLABS_AGENT_TAGS),
        ({}, NO_CUES),
    ],
    ids=[
        "realtime",
        "v4 turbo",
        "v3 conversational",
        "v4 with expressive off",
        "v2 generation",
        "no realtime, v2",
        "empty realtime, v4",
        "nothing stored",
    ],
)
def test_the_agents_speaking_engine_decides_the_wire(
    config: dict[str, Any], expected: CueDialect
) -> None:
    assert agent_dialect({"conversation_config": config}) is expected


@pytest.mark.parametrize(
    "agent",
    [
        {},
        {"conversation_config": None},
        {"conversation_config": []},
        {"conversation_config": {"tts": "eleven_v4"}},
        {"conversation_config": {"realtime_model": 3}},
    ],
)
def test_a_configuration_lia_cannot_read_is_words_alone(agent: dict[str, Any]) -> None:
    assert agent_dialect(agent) is NO_CUES


def test_a_stranger_is_never_offered_a_persona_or_a_familiar_cue() -> None:
    assert not STRANGER_CUES & PERSONA_CUES
    assert not STRANGER_CUES & {Cue.EXCITED, Cue.WHISPERING, Cue.LAUGHS}
    assert STRANGER_CUES <= DELIVERY_CUES | EVENT_CUES


def test_the_person_is_offered_the_whole_vocabulary() -> None:
    assert PERSON_CUES == frozenset(Cue)


# -- the palette is written into the agent's WHOLE speaking block -----------------------------

_TAGS = [{"tag": "sarcastically", "description": "a dry, mocking edge on the next words"}]


def test_the_palette_travels_inside_the_agents_whole_tts_block() -> None:
    """Every other stored setting is sent back as stored: whatever the vendor's merge
    (a PATCHed block had its omitted booleans replaced on the overrides, 2026-09-16),
    the person's voice, engine and expressive switch survive LIA's palette."""
    stored = {
        "voice_id": "the-persons-voice",
        "model_id": "eleven_v3_conversational",
        "expressive_mode": True,
        "stability": 0.4,
        "suggested_audio_tags": [{"tag": "happy", "description": "Use when the user is happy"}],
    }
    agent = {"conversation_config": {"tts": stored}}

    block = palette_block(agent, _TAGS)

    assert block == {**stored, "suggested_audio_tags": _TAGS}
    # The agent as read is left as read.
    assert stored["suggested_audio_tags"] == [
        {"tag": "happy", "description": "Use when the user is happy"}
    ]


def test_an_agent_already_holding_the_palette_is_not_written() -> None:
    agent = {"conversation_config": {"tts": {"voice_id": "v", "suggested_audio_tags": _TAGS}}}
    assert palette_block(agent, _TAGS) is None


@pytest.mark.parametrize(
    "agent",
    [{}, {"conversation_config": {"tts": None}}, {"conversation_config": {"tts": "eleven_v4"}}],
    ids=["nothing stored", "no tts block", "an unreadable tts block"],
)
def test_an_agent_with_no_readable_tts_block_gets_the_palette_alone(
    agent: dict[str, Any],
) -> None:
    assert palette_block(agent, _TAGS) == {"suggested_audio_tags": _TAGS}


def test_a_tag_outside_the_persons_palette_is_invented_whatever_its_case_or_blanks() -> None:
    tags = ["sarcastically", "Sighs", "  laughs ", "tired", "whispers", "laughs harder", "1"]
    assert invented_cues(tags, ELEVENLABS_AGENT_TAGS) == 2
    # An engine that performs no tag offered nothing: every tag is invented.
    assert invented_cues(["laughs"], NO_CUES) == 1
