"""Unit tests for the shared journal prompt renderers.

``prompt_builders`` exists so the measurement harness renders the exact prompt
the runtime renders. These tests pin the two properties that guarantee it:

1. Every placeholder of the shipped templates is filled — a leftover ``{name}``
   reaches the model as literal text, and a missing key raises at runtime, in a
   fire-and-forget background task where it degrades into a silent no-op.
2. The persona reaches both prompts, with the personality code substituted and
   a safe fallback when there is none — in the extraction prompt's FIXED part,
   above its dynamic-context boundary (ADR-309).
"""

from __future__ import annotations

import re

import pytest

from src.core.prompt_layout import single_call_messages, split_at_marker
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.journals.prompt_builders import (
    build_consolidation_prompt,
    build_introspection_prompt,
    render_consolidation_prompt,
    render_introspection_prompt,
)

pytestmark = pytest.mark.unit

INTROSPECTION_FIELDS: dict[str, object] = {
    "conversation": "USER: bonjour\nASSISTANT: bonjour",
    "existing_entries": "No existing entries yet.",
    "current_chars": 120,
    "max_chars": 30000,
    "size_warning": "",
    "user_language": "fr",
    "max_entry_chars": 300,
    "health_context": "",
    "inner_state_section": "",
    "previous_turn_directives_section": "",
}

CONSOLIDATION_FIELDS: dict[str, object] = {
    "all_entries": "No entries to review.",
    "current_chars": 120,
    "max_chars": 30000,
    "size_warning": "",
    "current_datetime": "2026-07-27 00:00 UTC",
    "conversation_history_section": "",
    "usage_patterns_section": "",
    "user_language": "fr",
    "max_entry_chars": 300,
    "size_management_instruction": "within limit",
    "health_signals_section": "",
    "memories_section": "",
    "interests_section": "",
    "habits_section": "",
    "debriefs_section": "",
}

#: The pure renderer takes the portrait budgets as arguments; the builder
#: reads them from settings (ADR-184: a tunable number never lives in prose).
RENDER_ONLY_FIELDS: dict[str, object] = {
    "portrait_full_tokens": 300,
    "portrait_brief_tokens": 70,
}

# A literal placeholder surviving into the rendered prompt. Excludes the JSON
# examples' escaped braces, which render as real braces, by requiring a bare
# lowercase identifier.
_LEFTOVER_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


class TestIntrospectionPrompt:
    """The post-conversation extraction prompt."""

    def test_renders_without_leftover_placeholders(self) -> None:
        """Every ``{field}`` of the shipped template is supplied."""
        prompt = build_introspection_prompt(personality_code="cynic", **INTROSPECTION_FIELDS)  # type: ignore[arg-type]
        leftovers = _LEFTOVER_PLACEHOLDER.findall(prompt)
        assert not leftovers, f"unfilled placeholders reached the model: {leftovers}"

    def test_substitutes_the_supplied_values(self) -> None:
        """The conversation and the language actually reach the prompt."""
        prompt = build_introspection_prompt(personality_code=None, **INTROSPECTION_FIELDS)  # type: ignore[arg-type]
        assert "USER: bonjour" in prompt
        assert "fr" in prompt

    def test_carries_the_persona_with_the_personality_code(self) -> None:
        """The analyst persona is there and carries the active code."""
        prompt = build_introspection_prompt(personality_code="cynic", **INTROSPECTION_FIELDS)  # type: ignore[arg-type]
        assert "ANALYST PERSONA" in prompt
        assert "cynic" in prompt

    def test_persona_falls_back_to_none_literal(self) -> None:
        """A user without a personality still gets a well-formed persona."""
        prompt = build_introspection_prompt(personality_code=None, **INTROSPECTION_FIELDS)  # type: ignore[arg-type]
        assert 'Active personality: "none"' in prompt

    def test_render_accepts_an_alternative_template(self) -> None:
        """A candidate prompt renders through the very same path.

        This is what lets the harness A/B a candidate against the shipped file
        without duplicating the assembly logic — the duplication that would
        otherwise drift.
        """
        prompt = render_introspection_prompt(
            "CANDIDATE {conversation} / {user_language} / {current_chars} / {max_chars} / "
            "{size_warning}{existing_entries}{max_entry_chars}{health_context}"
            "{inner_state_section}{previous_turn_directives_section}{analyst_persona}",
            str(load_prompt("journal_analyst_persona")),
            personality_code=None,
            **INTROSPECTION_FIELDS,  # type: ignore[arg-type]
        )
        assert prompt.startswith("CANDIDATE USER: bonjour")
        assert "ANALYST PERSONA" in prompt

    def test_a_template_that_does_not_place_the_persona_is_refused(self) -> None:
        """``str.format`` would drop the persona in silence, and a harness run would
        measure a prompt production never sends."""
        with pytest.raises(ValueError, match="analyst_persona"):
            render_introspection_prompt(
                "CANDIDATE {conversation}",
                str(load_prompt("journal_analyst_persona")),
                personality_code=None,
                **INTROSPECTION_FIELDS,  # type: ignore[arg-type]
            )


class TestIntrospectionLayout:
    """ADR-309: the extraction runs on every turn, so its rules and persona are
    one fixed part a provider's prompt cache reads again, and the turn's data
    follows the boundary."""

    def _prompt(self, **overrides: object) -> str:
        return build_introspection_prompt(  # type: ignore[arg-type]
            personality_code="cynic", **{**INTROSPECTION_FIELDS, **overrides}
        )

    def test_the_rules_and_the_persona_precede_the_boundary(self) -> None:
        split = split_at_marker(self._prompt())
        assert split is not None
        assert "SECTION 1" in split.static and "OUTPUT FORMAT" in split.static
        assert "ANALYST PERSONA" in split.static and "cynic" in split.static

    def test_the_turn_data_follows_the_boundary(self) -> None:
        split = split_at_marker(self._prompt(size_warning="SIZE-WARNING-7"))
        assert split is not None
        assert "USER: bonjour" in split.dynamic and "No existing entries yet." in split.dynamic
        assert "SIZE-WARNING-7" in split.dynamic and "USER: bonjour" not in split.static

    def test_two_turns_share_the_fixed_part(self) -> None:
        first = split_at_marker(self._prompt())
        second = split_at_marker(
            self._prompt(conversation="USER: autre chose", current_chars=999, user_language="en")
        )
        assert first is not None and second is not None
        assert first.static == second.static

    def test_the_call_sends_the_fixed_part_as_the_system_message(self) -> None:
        system, question = single_call_messages(self._prompt())
        assert system.type == "system" and "ANALYST PERSONA" in str(system.content)
        assert question.type == "human" and "USER: bonjour" in str(question.content)


class TestConsolidationPrompt:
    """The periodic maintenance prompt."""

    def test_renders_without_leftover_placeholders(self) -> None:
        """Every ``{field}`` of the shipped template is supplied."""
        prompt = build_consolidation_prompt(personality_code="cynic", **CONSOLIDATION_FIELDS)  # type: ignore[arg-type]
        leftovers = _LEFTOVER_PLACEHOLDER.findall(prompt)
        assert not leftovers, f"unfilled placeholders reached the model: {leftovers}"

    def test_appends_the_persona(self) -> None:
        """The consolidation prompt carries the same analyst persona."""
        prompt = build_consolidation_prompt(personality_code=None, **CONSOLIDATION_FIELDS)  # type: ignore[arg-type]
        assert "ANALYST PERSONA" in prompt

    def test_the_portrait_budgets_come_from_the_settings_never_from_prose(self) -> None:
        """ADR-184 applied to the portrait: the numbers the model reads are the
        numbers the settings hold, and the old prose figures are gone."""
        from src.core.config import settings

        prompt = build_consolidation_prompt(personality_code=None, **CONSOLIDATION_FIELDS)  # type: ignore[arg-type]
        assert f"about {settings.journal_portrait_full_max_tokens} tokens" in prompt
        assert f"about {settings.journal_portrait_brief_max_tokens} tokens" in prompt
        assert "150-220" not in prompt and "50-70" not in prompt

    def test_the_four_source_sections_render_where_they_are_given(self) -> None:
        prompt = build_consolidation_prompt(
            personality_code=None,
            **{**CONSOLIDATION_FIELDS, "habits_section": "## LEARNED HABITS\n- x"},  # type: ignore[arg-type]
        )
        assert "## LEARNED HABITS" in prompt

    def test_render_accepts_an_alternative_template(self) -> None:
        """A candidate consolidation prompt renders through the same path."""
        prompt = render_consolidation_prompt(
            "CANDIDATE {all_entries}{current_chars}{max_chars}{size_warning}"
            "{current_datetime}{conversation_history_section}{usage_patterns_section}"
            "{user_language}{max_entry_chars}{size_management_instruction}"
            "{health_signals_section}{memories_section}{interests_section}"
            "{habits_section}{debriefs_section}{portrait_full_tokens}{portrait_brief_tokens}",
            str(load_prompt("journal_analyst_persona")),
            personality_code=None,
            **CONSOLIDATION_FIELDS,  # type: ignore[arg-type]
            **RENDER_ONLY_FIELDS,  # type: ignore[arg-type]
        )
        assert prompt.startswith("CANDIDATE No entries to review.")
