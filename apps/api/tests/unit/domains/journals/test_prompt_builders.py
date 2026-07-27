"""Unit tests for the shared journal prompt renderers.

``prompt_builders`` exists so the measurement harness renders the exact prompt
the runtime renders. These tests pin the two properties that guarantee it:

1. Every placeholder of the shipped templates is filled — a leftover ``{name}``
   reaches the model as literal text, and a missing key raises at runtime, in a
   fire-and-forget background task where it degrades into a silent no-op.
2. The persona is appended to both prompts, with the personality code
   substituted and a safe fallback when there is none.
"""

from __future__ import annotations

import re

import pytest

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

    def test_appends_the_persona_with_the_personality_code(self) -> None:
        """The analyst persona is appended and carries the active code."""
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
            "{inner_state_section}{previous_turn_directives_section}",
            str(load_prompt("journal_analyst_persona")),
            personality_code=None,
            **INTROSPECTION_FIELDS,  # type: ignore[arg-type]
        )
        assert prompt.startswith("CANDIDATE USER: bonjour")
        assert "ANALYST PERSONA" in prompt


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

    def test_render_accepts_an_alternative_template(self) -> None:
        """A candidate consolidation prompt renders through the same path."""
        prompt = render_consolidation_prompt(
            "CANDIDATE {all_entries}{current_chars}{max_chars}{size_warning}"
            "{current_datetime}{conversation_history_section}{usage_patterns_section}"
            "{user_language}{max_entry_chars}{size_management_instruction}"
            "{health_signals_section}",
            str(load_prompt("journal_analyst_persona")),
            personality_code=None,
            **CONSOLIDATION_FIELDS,  # type: ignore[arg-type]
        )
        assert prompt.startswith("CANDIDATE No entries to review.")
