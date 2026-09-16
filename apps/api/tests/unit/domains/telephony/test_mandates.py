"""Unit tests for the call mandates — one agent, two ways of speaking (lot 2).

The vendor agent is provisioned once with the third-party mandate baked in;
the owner's own call and the verification call REPLACE its prompt, greeting
and language through a per-call override the vendor accepts (measured
2026-09-16). What each mandate needs is declared once, here, and the boot
refuses a kind without one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core.time_utils import format_datetime_for_display
from src.domains.telephony.mandates import (
    MANDATES,
    MandateInputs,
    assert_mandate_completeness,
    build_override,
    mandate_for,
)
from src.domains.telephony.models import CallKind


@pytest.mark.unit
def test_every_kind_has_a_mandate() -> None:
    assert set(MANDATES) == set(CallKind)
    assert_mandate_completeness()


@pytest.mark.unit
def test_third_party_mandate_keeps_the_baked_agent() -> None:
    mandate = mandate_for(CallKind.THIRD_PARTY)
    assert mandate.overrides_agent is False
    assert mandate.prefetch_availability is True
    assert mandate.rich_context is False


@pytest.mark.unit
def test_self_mandate_overrides_prompt_and_greeting() -> None:
    mandate = mandate_for(CallKind.SELF)
    assert mandate.overrides_agent is True
    assert mandate.prefetch_availability is True
    assert mandate.rich_context is True


@pytest.mark.unit
def test_verification_mandate_reads_nothing_of_the_person() -> None:
    mandate = mandate_for(CallKind.VERIFICATION)
    assert mandate.overrides_agent is True
    assert mandate.prefetch_availability is False
    assert mandate.rich_context is False


def _inputs(**overrides: object) -> MandateInputs:
    base: dict[str, object] = {
        "language": "fr",
        "user_name": "Alex",
        "objective": "go over the week's plan",
        "user_context": "## Agenda\n- 10:00 dentist",
        "availability_summary": "Busy: 10:00-11:00",
        "now": datetime(2026, 9, 16, 9, 30, tzinfo=UTC),
        "timezone": "Europe/Paris",
        "verification_code": "",
    }
    base.update(overrides)
    return MandateInputs(**base)  # type: ignore[arg-type]


@pytest.mark.unit
def test_self_override_is_fully_rendered_for_the_vendor() -> None:
    inputs = _inputs()
    override = build_override(CallKind.SELF, inputs)
    assert override is not None
    agent = override["agent"]
    prompt = agent["prompt"]["prompt"]
    assert "{" not in prompt  # no placeholder survives
    assert "go over the week's plan" in prompt
    assert "10:00 dentist" in prompt
    assert "Busy: 10:00-11:00" in prompt
    # The clock is spoken in the person's language and zone, like the third-party
    # agent's anchor (a bare ISO date is not what a voice reads out).
    assert format_datetime_for_display(inputs.now, "Europe/Paris", "fr") in prompt
    assert "Alex" in agent["first_message"]
    assert "{{" not in agent["first_message"]
    # The language, the duration cap and the tools are the portal's or the
    # agent's (owner decision 2026-09-16): an override is the prompt and the
    # greeting, nothing else.
    assert set(override) == {"agent"}
    assert set(agent) == {"prompt", "first_message"}
    assert set(agent["prompt"]) == {"prompt"}


@pytest.mark.unit
def test_self_override_carries_the_assistant_s_personality() -> None:
    """Lot 9 (owner question 2026-09-16): the voice adopts the personality the
    person configured for LIA — the same instruction the chat and the voice
    flow weave into `<personality_profile>` — neutralised like every value."""
    override = build_override(
        CallKind.SELF, _inputs(personality="Warm and playful; {{never}} pompous.")
    )
    assert override is not None
    prompt = override["agent"]["prompt"]["prompt"]
    assert "<personality_profile>" in prompt
    assert "Warm and playful; { {never} } pompous." in prompt
    assert "Modulate" in prompt  # the frame says how the profile applies


@pytest.mark.unit
def test_self_override_without_a_personality_keeps_the_default_voice() -> None:
    override = build_override(CallKind.SELF, _inputs(personality=""))
    assert override is not None
    prompt = override["agent"]["prompt"]["prompt"]
    assert "<personality_profile>" in prompt
    assert "no particular personality" in prompt


@pytest.mark.unit
def test_self_override_without_context_says_so_rather_than_leaving_a_hole() -> None:
    override = build_override(CallKind.SELF, _inputs(user_context=""))
    assert override is not None
    prompt = override["agent"]["prompt"]["prompt"]
    assert "{" not in prompt
    assert "user_context" not in prompt


@pytest.mark.unit
def test_vendor_variable_syntax_in_values_is_neutralised() -> None:
    """A ``{{x}}`` in the person's data must not become a vendor variable."""
    override = build_override(CallKind.SELF, _inputs(user_context="subject: {{hello}} world"))
    assert override is not None
    assert "{{hello}}" not in override["agent"]["prompt"]["prompt"]
    assert "hello" in override["agent"]["prompt"]["prompt"]


@pytest.mark.unit
def test_verification_override_speaks_the_code_digit_by_digit() -> None:
    override = build_override(CallKind.VERIFICATION, _inputs(verification_code="4719"))
    assert override is not None
    prompt = override["agent"]["prompt"]["prompt"]
    assert "4 7 1 9" in prompt
    assert "4719" not in prompt  # never one number the TTS would read as "four thousand"
    assert "{" not in prompt
    assert set(override) == {"agent"}


@pytest.mark.unit
def test_third_party_has_no_override() -> None:
    assert build_override(CallKind.THIRD_PARTY, _inputs()) is None


@pytest.mark.unit
@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_greetings_exist_in_every_language(language: str) -> None:
    for kind in (CallKind.SELF, CallKind.VERIFICATION):
        override = build_override(kind, _inputs(language=language, verification_code="1234"))
        assert override is not None
        assert override["agent"]["first_message"].strip()
        assert "language" not in override["agent"]  # the spoken language is the portal's


# ---------------------------------------------------------------------------
# Live tools (lot 7): the prompt names them; the ids are attached to the AGENT
# by the dial path, never carried by the override (the vendor refuses it —
# measured on a real call, 2026-09-16: « Tool IDs not attached to this agent »)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_self_override_names_the_live_lookups_by_domain_and_carries_no_ids() -> None:
    """Fifty tool names would drown the prompt (lot 8): the mandate names the
    DOMAINS the agent may look into, in words, and the vendor reads each
    tool's own description beside it."""
    override = build_override(CallKind.SELF, _inputs(live_tool_domains=("event", "task")))
    assert override is not None
    prompt = override["agent"]["prompt"]["prompt"]
    assert "Calendar, Tasks" in prompt
    assert "get_events_tool" not in prompt
    assert "no live lookup" not in prompt
    assert "tool_ids" not in override["agent"]["prompt"]


@pytest.mark.unit
def test_self_override_without_live_tools_says_so() -> None:
    override = build_override(CallKind.SELF, _inputs())
    assert override is not None
    assert "no live lookup" in override["agent"]["prompt"]["prompt"]
