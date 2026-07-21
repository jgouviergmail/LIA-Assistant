"""Tests for the MCP-domain skill-detection guard.

Pins the three production hijacks of 2026-07-21 (18:16-18:21): the analyzer
LLM answered ``primary_domain=mcp_excalidraw`` at 0.95 confidence on three
diagram requests, yet filled ``skill_name`` with ``interactive-map`` (a water
cycle rendered on a Google Maps embed), ``skill-generator`` (failed import,
inline SVG in the chat), then a hallucinated ``"mcp_excalidraw"``. The
routing decider gives the skill absolute priority, so the incoherent field
hijacked the whole turn twice out of three.
"""

from collections.abc import Iterator
from typing import Any

import pytest

from src.domains.agents.services.analysis.skill_suppression import (
    _is_dialogue_skill,
    effective_skill_name,
)
from src.domains.skills.cache import SkillsCache

pytestmark = pytest.mark.unit


@pytest.fixture()
def skills_cache() -> Iterator[None]:
    """Install cache entries shaped like the loader's, then restore.

    ``skill-generator`` declares ``dialogue: true`` (ADR-118), the others not.
    """
    entries: dict[str, dict[str, Any]] = {
        "admin:interactive-map": {
            "name": "interactive-map",
            "scope": "admin",
            "dialogue": False,
        },
        "admin:skill-generator": {
            "name": "skill-generator",
            "scope": "admin",
            "dialogue": True,
        },
    }
    saved_skills = SkillsCache._skills
    saved_loaded = SkillsCache._loaded
    SkillsCache._skills = entries
    SkillsCache._loaded = True
    try:
        yield
    finally:
        SkillsCache._skills = saved_skills
        SkillsCache._loaded = saved_loaded


class TestProductionHijacks:
    """The three proven cases — every one must come back suppressed."""

    def test_interactive_map_on_mcp_domain_is_suppressed(self, skills_cache: None) -> None:
        assert effective_skill_name("interactive-map", ["mcp_excalidraw"], "search") is None

    def test_dialogue_skill_on_fresh_mcp_request_is_suppressed(self, skills_cache: None) -> None:
        """skill-generator is a dialogue skill, but the production hijack was
        a FRESH imperative request (intent action) — the ADR-118 exemption
        must not shield it there."""
        assert effective_skill_name("skill-generator", ["mcp_excalidraw"], "action") is None

    def test_hallucinated_mcp_skill_name_is_suppressed(self, skills_cache: None) -> None:
        """'mcp_excalidraw' is not a skill; today it only reached the right
        path because the bypass failed. The guard makes that deterministic."""
        assert effective_skill_name("mcp_excalidraw", ["mcp_excalidraw"], "action") is None


class TestAdr118DialogueExemption:
    def test_conversational_answer_keeps_the_dialogue_skill(self, skills_cache: None) -> None:
        """Mid-dialogue answer mentioning an MCP surface ('un skill qui
        utilise excalidraw') — the continuation must survive, mirroring the
        chat override's own exemption predicate."""
        assert (
            effective_skill_name("skill-generator", ["mcp_excalidraw"], "conversation")
            == "skill-generator"
        )

    def test_conversational_answer_does_not_shield_one_shot_skills(
        self, skills_cache: None
    ) -> None:
        assert effective_skill_name("interactive-map", ["mcp_excalidraw"], "conversation") is None


class TestGuardScope:
    """The guard fires on the PRIMARY domain only, and passes everything else."""

    def test_non_mcp_primary_domain_passes_through(self, skills_cache: None) -> None:
        assert effective_skill_name("interactive-map", ["place"], "search") == "interactive-map"

    def test_secondary_mcp_domain_does_not_suppress(self, skills_cache: None) -> None:
        """Mixed request: the MCP domain is secondary, the skill may be the
        legitimate main act — deliberately out of the guard's scope."""
        assert (
            effective_skill_name("preparation-reunion", ["task", "mcp_excalidraw"], "action")
            == "preparation-reunion"
        )

    def test_no_skill_and_no_domains_pass_through(self, skills_cache: None) -> None:
        assert effective_skill_name(None, ["mcp_excalidraw"], "action") is None
        assert effective_skill_name("interactive-map", [], "action") == "interactive-map"


class TestDialoguePredicateReExport:
    """The predicate moved modules; the historical import path must survive."""

    def test_reexported_from_query_analyzer_service(self) -> None:
        from src.domains.agents.services.query_analyzer_service import (
            _is_dialogue_skill as reexported,
        )

        assert reexported is _is_dialogue_skill
