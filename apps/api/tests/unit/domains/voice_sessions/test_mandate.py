"""The delegation block every voice mandate composes (ADR-301).

The browser's live mandate and the phone's Live mandate render the SAME
block; its shape follows the provider's wire (a declared function or the
model's own act; a model that keeps talking or one that waits) and says a
delivery note's use only when notes are on.
"""

from __future__ import annotations

import pytest

from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.domains.voice_sessions.mandate import (
    DelegationBlockInputs,
    delegation_request_schema,
    delegation_tool_description,
    render_delegation_block,
    voice_lines,
)

pytestmark = pytest.mark.unit


def _block(
    *, async_delegation: bool = True, native_delegation: bool = False, tone_notes: bool = False
) -> str:
    return render_delegation_block(
        DelegationBlockInputs(
            user_name="Alex",
            result_budget_tokens=350,
            async_delegation=async_delegation,
            native_delegation=native_delegation,
            tone_notes=tone_notes,
        )
    )


def test_the_block_names_the_function_and_the_budget() -> None:
    block = _block()
    assert f"call {LIVE_DELEGATION_TOOL_NAME}" in block
    assert "at most 350 tokens" in block
    assert "Alex" in block
    assert not block.endswith("\n")


def test_an_async_wire_keeps_the_conversation_going_a_blocking_one_waits() -> None:
    lines = voice_lines()
    assert lines["delegation_async"].format(delegate="x")[:40] in _block(async_delegation=True)
    assert lines["delegation_blocking"].format(delegate="x")[:40] in _block(async_delegation=False)


def test_a_native_wire_delegates_by_its_own_act() -> None:
    block = _block(native_delegation=True)
    assert "delegate to LIA" in block
    assert f"call {LIVE_DELEGATION_TOOL_NAME}" not in block


def test_the_tone_note_line_is_emitted_only_when_notes_are_on() -> None:
    lines = voice_lines()
    assert lines["tone_note_call"] in _block(tone_notes=True)
    assert lines["tone_note_call"] not in _block(tone_notes=False)
    assert lines["tone_note_native"] in _block(tone_notes=True, native_delegation=True)
    # Emitted only when the content exists (ADR-284): an absent note leaves no
    # blank line inside the list, and a present one is one line of it.
    assert "\n\n-" not in _block(tone_notes=False).split("HOW A DELEGATION BEHAVES")[1]
    assert "\n\n-" not in _block(tone_notes=True).split("HOW A DELEGATION BEHAVES")[1]


def test_the_tool_description_and_schema_are_the_provider_neutral_contract() -> None:
    assert "Alex" in delegation_tool_description("Alex")
    schema = delegation_request_schema()
    assert schema["required"] == ["request"]
    assert schema["properties"]["request"]["type"] == "string"
    # The parameter's description is prose the model reads: it lives in the
    # lines file (ADR-284), once, and every wire copies it from here.
    assert schema["properties"]["request"]["description"] == voice_lines()["request_parameter"]
