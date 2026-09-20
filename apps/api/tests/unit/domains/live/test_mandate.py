"""The mandate says what the code enforces (ADR-284, ADR-299): one function,
the wait, the questions — and nothing personal, nothing French."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.core.prompt_store import read_prompt_file
from src.domains.agents.expressivity.vocabulary import TONE_REGISTERS
from src.domains.live.mandate import (
    MandateInputs,
    delegation_tool_declaration,
    live_lines,
    render_live_mandate,
    tone_lines,
)

pytestmark = pytest.mark.unit


def _inputs(**overrides: object) -> MandateInputs:
    base: dict[str, object] = {
        "language": "zh",
        "user_name": "Alex",
        "personality": "",
        "now": datetime(2026, 9, 18, 9, 30, tzinfo=UTC),
        "timezone": "Europe/Paris",
        "result_budget_tokens": 600,
        "async_delegation": True,
        "native_delegation": False,
    }
    base.update(overrides)
    return MandateInputs(**base)  # type: ignore[arg-type]


def test_mandate_names_the_language_the_person_and_the_function() -> None:
    text = render_live_mandate(_inputs())
    # The Live API's documented shape for the output language, unmistakable.
    assert "YOU MUST RESPOND UNMISTAKABLY IN Simplified Chinese" in text
    assert "Alex" in text
    assert LIVE_DELEGATION_TOOL_NAME in text
    assert "600" in text
    # Every placeholder was produced: no single-brace key survives.
    assert not re.search(r"(?<!\{)\{[a-z_]+\}(?!\})", text)


def test_delegation_block_follows_the_models_capability() -> None:
    # A model that keeps talking during a call is told to acknowledge BEFORE it
    # calls; a model that waits for the response (3.1 Flash Live) is not asked
    # to fill a silence it cannot fill (ADR-284: the prompt states what the
    # code enforces, and only when the content exists).
    lines = live_lines()
    call = lines["delegate_by_call"].format(tool_name=LIVE_DELEGATION_TOOL_NAME)
    async_text = render_live_mandate(_inputs(async_delegation=True))
    blocking_text = render_live_mandate(_inputs(async_delegation=False))
    assert lines["delegation_async"].format(delegate=call) in async_text
    assert lines["delegation_blocking"].format(delegate=call) in blocking_text
    assert lines["delegation_async"].format(delegate=call) not in blocking_text


def test_native_delegation_names_no_function_and_says_delegate() -> None:
    # GPT-Live delegates by its own act (wave 2 A9): the mandate says « delegate
    # to LIA », never names a function the model cannot call, and carries the
    # documented rules — delegate BEFORE answering, never guess while waiting,
    # stopping speech is not cancelling work.
    lines = live_lines()
    text = render_live_mandate(_inputs(native_delegation=True))
    assert LIVE_DELEGATION_TOOL_NAME not in text
    assert lines["delegation_native"].format(delegate=lines["delegate_native"]) in text
    assert "delegate to LIA, with the request in Alex's own words" in text
    assert "never guess the result while waiting" in text
    assert "Stopping your speech does not cancel LIA's work" in text
    assert not re.search(r"(?<!\{)\{[a-z_]+\}(?!\})", text)


def test_personality_line_only_when_given() -> None:
    without = render_live_mandate(_inputs())
    with_it = render_live_mandate(_inputs(personality="Warm and brief."))
    assert "Warm and brief." in with_it
    assert live_lines()["no_personality"] in without
    assert live_lines()["no_personality"] not in with_it


def test_inner_state_and_tone_notes_are_said_only_when_they_exist() -> None:
    # Owner question 5 (2026-09-19): the psyche block is placed verbatim when the
    # engine hands one, and the delivery-note rule is stated only under the
    # annotation flag — in the vocabulary of the provider's wire (ADR-284).
    lines = live_lines()
    bare = render_live_mandate(_inputs())
    assert "InnerVoice" not in bare
    assert lines["tone_note_call"] not in bare and lines["tone_note_native"] not in bare
    assert "\n\n\n" not in bare
    block = "<InnerVoice>\nRight now, inside, you are slightly serene.\n</InnerVoice>"
    by_call = render_live_mandate(_inputs(psyche_block=block, tone_notes=True))
    assert block in by_call
    assert lines["tone_note_call"] in by_call and lines["tone_note_native"] not in by_call
    native = render_live_mandate(_inputs(native_delegation=True, tone_notes=True))
    assert lines["tone_note_native"] in native and lines["tone_note_call"] not in native


def test_tone_lines_cover_the_closed_vocabulary_and_nothing_else() -> None:
    # One delivery note per register (ADR-253's vocabulary is the authority):
    # a register without a note would hand the voice nothing, a note without a
    # register could never be chosen.
    notes = tone_lines()
    assert set(notes) == set(TONE_REGISTERS)
    assert all(note.strip() and "{" not in note for note in notes.values())


def test_declaration_is_non_blocking_with_one_required_string() -> None:
    declaration = delegation_tool_declaration("Alex")
    assert declaration["name"] == LIVE_DELEGATION_TOOL_NAME
    assert declaration["behavior"] == "NON_BLOCKING"
    assert declaration["parameters"]["required"] == ["request"]
    assert declaration["parameters"]["properties"]["request"]["type"] == "string"
    assert "Alex" in declaration["description"]


def test_lines_carry_the_bridge_results() -> None:
    # A second request while one runs REPLACES it (wave 2 spec A7): no
    # « still working » line exists any more, the old call is closed silently.
    lines = live_lines()
    assert {"timed_out", "result_cut", "superseded", "empty_request"} <= set(lines)
    assert "still_working" not in lines


@pytest.mark.parametrize("name", ["live_system_prompt", "live_lines", "live_tone_lines"])
def test_no_french_and_no_doubled_braces_in_the_prompt_files(name: str) -> None:
    text = read_prompt_file(name)
    assert not any(ch in text for ch in "àâéèêîôûç"), name
    assert "{{" not in text, name
