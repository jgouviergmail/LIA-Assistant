"""Grounding doctrine guard for the response prompt (2026-07-23 fix).

When a turn produces no registry updates of its own, ``current_turn_registry``
is ``{}`` by design and ``{data_for_filtering}`` is therefore empty. (The trigger
is the absence of tool results for the turn — NOT a "conversational" turn type,
which no producer ever emits: QueryIntelligence only yields ACTION / INITIAL /
REFERENCE_PURE / REFERENCE_ACTION.)

Two complementary rules are pinned here:
- the model must never invent an entity attribute it cannot see;
- when recent entities ARE surfaced (see context/recent_entities.py), the block
  stays explicitly non-authoritative so current-turn data always wins.

Prod symptom these guard against: an appointment reported at "16h" when the
prior turn's tool result stated "11h15".
"""

from __future__ import annotations

import pytest

from src.domains.agents.prompts import load_prompt

pytestmark = [pytest.mark.unit]


def test_response_prompt_forbids_inventing_entity_attributes() -> None:
    prompt = load_prompt("response_system_prompt_base")
    # The rule lives in the static <DataAuthority> block (cacheable prefix).
    assert "<DataAuthority>" in prompt
    assert "Never invent or approximate" in prompt, (
        "response_system_prompt_base.txt lost its anti-confabulation rule — the "
        "model could again guess an entity attribute (e.g. an appointment time)."
    )


def test_rule_offers_an_honest_fallback_instead_of_guessing() -> None:
    prompt = load_prompt("response_system_prompt_base")
    # The fallback must be explicit: say so / re-check, never a plausible guess.
    assert "never substitute a plausible-sounding guess" in prompt


def test_data_authority_accepts_recent_entities_as_a_citable_source() -> None:
    """The restrictive rule must not exclude the very block that carries the value.

    <DataAuthority> enumerates where a factual attribute may come from. On a
    tool-less turn the only carrier is <RecentEntities> (current-turn data is
    empty and <History> has no ToolMessages): leaving it out of the enumeration
    told the model to refuse exactly when grounding had just supplied the answer.
    """
    prompt = load_prompt("response_system_prompt_base")
    authority = prompt.split("<DataAuthority>", 1)[1].split("</DataAuthority>", 1)[0]
    assert "<RecentEntities>" in authority


def test_missing_tool_data_must_be_admitted_not_filled_in() -> None:
    """Prod 2026-07-23: no weather step ran, and the model invented temperatures.

    The plan-level fix is elsewhere; the prompt must still refuse to fabricate
    figures for data it was asked about but never received.
    """
    prompt = load_prompt("response_system_prompt_base")
    authority = prompt.split("<DataAuthority>", 1)[1].split("</DataAuthority>", 1)[0]
    assert "never received" in authority
    assert "temperatures" in authority


def test_recent_entities_section_absent_when_nothing_to_ground() -> None:
    """No content -> no emitted <RecentEntities> section (wasted tokens, confusing).

    Checked on the CLOSING tag: <DataAuthority> names ``<RecentEntities>`` as a
    citable source, so the opening form appears in the static prefix even when
    the section itself is not emitted.
    """
    from src.domains.agents.prompts import get_response_prompt

    assert "</RecentEntities>" not in get_response_prompt()


def test_recent_entities_section_carries_content_and_stays_non_authoritative() -> None:
    """When grounding applies, the block is injected AND framed as non-authoritative."""
    from src.domains.agents.prompts import get_response_prompt

    prompt = get_response_prompt(recent_entities="- [events] Rdv podologue | 11:15")
    assert "<RecentEntities>" in prompt
    assert "11:15" in prompt
    # Must not compete with current-turn data (preserves <DataAuthority>).
    assert "current turn data covers the same entity, that data wins" in prompt
    assert "NOT current-turn results" in prompt
