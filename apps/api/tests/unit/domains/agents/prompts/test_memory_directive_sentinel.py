"""Sentinel-coupling guard between the memory danger directive and the response prompt.

``response_context_sections.txt`` (the profile section) instructs the LLM to comply with all
prohibitions when the psychological profile contains the LITERAL string
"DIRECTIVE DE SÉCURITÉ ÉMOTIONNELLE"; that string is produced by
``memory_danger_directive.txt`` (injected via the memory-injection middleware).
If either side is reworded without the other, the emotional-safety escalation
silently stops firing. This test pins the coupling.
"""

from __future__ import annotations

import pytest

from src.domains.agents.prompts import load_prompt

pytestmark = [pytest.mark.unit]

SENTINEL = "DIRECTIVE DE SÉCURITÉ ÉMOTIONNELLE"


def test_danger_directive_carries_the_sentinel_header() -> None:
    directive = load_prompt("memory_danger_directive")
    first_line = directive.splitlines()[0]
    assert SENTINEL in first_line, (
        "memory_danger_directive.txt no longer opens with the sentinel header "
        f"'{SENTINEL}' — the response prompt matches it literally."
    )


def test_response_prompt_matches_the_same_sentinel() -> None:
    """The instruction travels with the profile section (response_context_sections)."""
    from src.domains.agents.prompts import get_response_prompt

    rendered = get_response_prompt(user_language="fr", user_query="q", psychological_profile="P")
    assert SENTINEL in rendered, (
        "the psychological-profile section no longer references the sentinel "
        f"'{SENTINEL}' — emotional-safety compliance would silently stop firing."
    )


def test_normal_directive_does_not_carry_the_sentinel() -> None:
    """The escalation must fire ONLY for the danger state."""
    directive = load_prompt("memory_normal_directive")
    assert SENTINEL not in directive
