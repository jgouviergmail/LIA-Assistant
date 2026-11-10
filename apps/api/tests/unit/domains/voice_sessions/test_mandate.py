"""The delegation block every voice mandate composes (ADR-301).

The browser's live mandate and the phone's Live mandate render the SAME
block; its shape follows the provider's wire (a declared function or the
model's own act; a model that keeps talking or one that waits) and says a
delivery note's use only when notes are on.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.core.prompt_store import read_prompt_file
from src.domains.live.direct_mandate import DirectMandateInputs, render_direct_mandate
from src.domains.live.mandate import MandateInputs as LiveMandateInputs
from src.domains.live.mandate import render_live_mandate
from src.domains.telephony.mandates import MandateInputs as PhoneMandateInputs
from src.domains.telephony.mandates import build_override
from src.domains.telephony.models import CallKind
from src.domains.voice_sessions.mandate import (
    DelegationBlockInputs,
    delegation_request_schema,
    delegation_tool_description,
    neutralise_vendor_syntax,
    personality_block,
    render_delegation_block,
    voice_lines,
)
from src.domains.voice_sessions.session import VoiceSessionMode

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)
_PERSONALITY = "A rebel mind, sarcastic, with a dark sense of humour.\nAlways says tu."


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


def _four_mandates(personality: str) -> dict[str, str]:
    """The four mandates a person hears LIA through, rendered for one personality."""
    live = render_live_mandate(
        LiveMandateInputs(
            language="fr",
            user_name="Alex",
            personality=personality,
            now=_NOW,
            timezone="Europe/Paris",
            result_budget_tokens=350,
            async_delegation=False,
            native_delegation=False,
        )
    )
    direct = render_direct_mandate(
        DirectMandateInputs(
            language="fr",
            user_name="Alex",
            personality=personality,
            now=_NOW,
            timezone="Europe/Paris",
            psyche_block="",
            user_context="",
            tool_domains=(),
        )
    )
    phone = PhoneMandateInputs(
        language="fr",
        user_name="Alex",
        objective="a catch-up",
        user_context="",
        availability_summary="",
        now=_NOW,
        timezone="Europe/Paris",
        personality=personality,
        result_budget_tokens=350,
    )
    rendered = {"live": live, "live_direct": direct}
    modes: tuple[VoiceSessionMode, ...] = ("direct", "delegated")
    for mode in modes:
        override = build_override(CallKind.SELF, phone, mode=mode)
        assert override is not None
        rendered[f"phone_{mode}"] = override["agent"]["prompt"]["prompt"]
    return rendered


def test_the_block_carries_the_configured_personality_verbatim() -> None:
    block = personality_block(_PERSONALITY, user_name="Alex")
    assert _PERSONALITY in block
    assert "Alex" in block
    assert not re.search(r"(?<!\{)\{[a-z_]+\}(?!\})", block)


def test_without_a_personality_the_block_carries_lias_default_manner() -> None:
    assert voice_lines()["default_personality"] in personality_block("  ", user_name="Alex")


def test_braces_in_a_personality_are_text_never_placeholders() -> None:
    odd = "Uses {x} and {{y}} in writing."
    assert odd in personality_block(odd, user_name="Alex")


def test_the_four_mandates_carry_the_one_block() -> None:
    """One wording for every line LIA speaks to the person on (owner, 2026-11-07)."""
    block = personality_block(_PERSONALITY, user_name="Alex")
    for name, prompt in _four_mandates(_PERSONALITY).items():
        expected = neutralise_vendor_syntax(block) if name.startswith("phone") else block
        assert expected in prompt, name


@pytest.mark.parametrize("personality", [_PERSONALITY, "Bubbly and loud!", ""])
def test_no_mandate_imposes_a_tone_of_its_own(personality: str) -> None:
    """The measured defect: « keep small talk brief and warm » fought every personality."""
    for name, prompt in _four_mandates(personality).items():
        without_block = prompt.replace(
            neutralise_vendor_syntax(personality_block(personality, user_name="Alex")), ""
        )
        assert not re.search(r"\b(warm\w*|kindly)\b", without_block, re.IGNORECASE), name


@pytest.mark.parametrize(
    "value",
    ["{{x}}", "{{{x}}}", "{{{{x}}}}", "}}{{", "a {{ b }} c", "{{", "}}}"],
)
def test_no_run_of_braces_reaches_the_vendor_doubled(value: str) -> None:
    """The vendor reads ``{{name}}`` as a variable: a run of any length is broken
    apart (a left-to-right replace left ``{ {{x} }}`` of ``{{{x}}}``), and the
    text is kept whole, a space between braces aside."""
    neutralised = neutralise_vendor_syntax(value)

    assert "{{" not in neutralised and "}}" not in neutralised
    assert neutralised.replace(" ", "") == value.replace(" ", "")


def test_a_doubled_brace_reads_as_it_always_did() -> None:
    """The phone's mandates keep their rendering: only longer runs change."""
    assert neutralise_vendor_syntax("Hi {{user_name}}") == "Hi { {user_name} }"


def test_the_block_file_is_technical_english_without_vendor_syntax() -> None:
    text = read_prompt_file("voice_personality_block")
    assert not any(ch in text for ch in "àâéèêîôûç")
    assert "{{" not in text


def test_the_tool_description_and_schema_are_the_provider_neutral_contract() -> None:
    assert "Alex" in delegation_tool_description("Alex")
    schema = delegation_request_schema()
    assert schema["required"] == ["request"]
    assert schema["properties"]["request"]["type"] == "string"
    # The parameter's description is prose the model reads: it lives in the
    # lines file (ADR-284), once, and every wire copies it from here.
    assert schema["properties"]["request"]["description"] == voice_lines()["request_parameter"]
