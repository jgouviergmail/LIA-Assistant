"""Every character a voice prompt teaches as output is spoken aloud (production 2026-11-14).

The vendor's voice model read its few-shot examples literally: an example that
wrote a tool call as text (``[Action: voicemail_detection(reason="…")]``) was
copied into the agent's words, and the speech engine read it on the callee's
voicemail before the portal's message — measured on three calls of the
production account, the closing ``[Action: end_call()]`` of an answered call
included. A tool is called through the tool interface, never written: the
prompts must show no notation a model could copy into its speech.
"""

from __future__ import annotations

import re

import pytest

from src.core.prompt_store import read_prompt_file

pytestmark = pytest.mark.unit

#: The four frames a voice speaks under: the third party, the owner (direct and
#: Live) and the number verification.
VOICE_PROMPTS = (
    "telephony_agent_system_prompt",
    "telephony_self_call_system_prompt",
    "telephony_self_live_system_prompt",
    "telephony_verification_prompt",
)

#: The one sentence every frame states, so the rule is said, not only shown.
RULE = "A tool is called, never written"

_TOOL_CALL_SYNTAX = re.compile(r"\b(?:end_call|voicemail_detection|send_to_lia)\s*\(")
_EXAMPLES = re.compile(r"<canonical_examples>(.*?)</canonical_examples>", re.DOTALL)


def _read(name: str) -> str:
    return read_prompt_file(name)


def _bracketed_lines(text: str) -> list[str]:
    """The lines of the examples that open with a bracket: an action or a stage direction."""
    examples = _EXAMPLES.search(text)
    body = examples.group(1) if examples else ""
    return [line.strip() for line in body.splitlines() if line.strip().startswith("[")]


@pytest.mark.unit
@pytest.mark.parametrize("name", VOICE_PROMPTS)
def test_no_tool_call_is_written_as_text(name: str) -> None:
    """No ``[Action: …]`` marker and no call syntax a model could say aloud."""
    text = _read(name)
    assert "[Action" not in text
    assert _TOOL_CALL_SYNTAX.findall(text) == []


@pytest.mark.unit
@pytest.mark.parametrize("name", VOICE_PROMPTS)
def test_examples_hold_no_bracketed_line(name: str) -> None:
    """A stage direction belongs to the context line, never to the spoken output."""
    assert _bracketed_lines(_read(name)) == []


@pytest.mark.unit
@pytest.mark.parametrize("name", VOICE_PROMPTS)
def test_every_frame_states_the_rule(name: str) -> None:
    """The rule is written in every frame, not only implied by the examples."""
    assert RULE in _read(name)


@pytest.mark.unit
def test_the_guard_catches_the_shape_measured_in_production() -> None:
    """Proven on the defect itself: the guard would have refused the shipped examples."""
    shipped = (
        "<canonical_examples>\nExample 3: Voicemail Handoff\nAssistant Output:\n"
        '[Action: voicemail_detection(reason="Automated greeting requesting a voicemail")]\n'
        "</canonical_examples>"
    )
    assert "[Action" in shipped
    assert _TOOL_CALL_SYNTAX.findall(shipped)
    assert _bracketed_lines(shipped)
