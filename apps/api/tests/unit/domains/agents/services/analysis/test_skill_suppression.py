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
    Every name used by the suite must be declared here: since 2026-07-27
    ``effective_skill_name`` also rejects names that match no reachable skill,
    so an incomplete fixture would suppress for the wrong reason and mask the
    behaviour under test.
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
        "admin:preparation-reunion": {
            "name": "preparation-reunion",
            "scope": "admin",
            "dialogue": False,
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


class TestSentinelNames:
    """The LLM writes the *string* "null", not the JSON literal.

    Measured on 2026-07-27 against the production analyzer (deepseek-v4-flash,
    `strict_mode: false`): 104 probes, of which 84 to 100% returned the literal
    text ``"null"`` — the prompt says "leave it null" in prose, and a
    non-strict structured output happily writes those four characters. A
    non-empty string is truthy, so ``RoutingDecider`` rule 1 fired on every one
    of them: route forced to the planner and the early-detection short-circuit
    skipped, on turns where NO skill was detected at all.
    """

    @pytest.mark.parametrize("sentinel", ["null", "NULL", "  null  ", "None", "none", "nil"])
    def test_sentinel_is_rejected(self, sentinel: str, skills_cache: None) -> None:
        assert effective_skill_name(sentinel, ["image_generation"], "create") is None

    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_blank_is_rejected(self, blank: str, skills_cache: None) -> None:
        assert effective_skill_name(blank, ["image_generation"], "create") is None

    def test_surrounding_whitespace_is_stripped_from_a_real_name(self, skills_cache: None) -> None:
        """A real name must survive stripping, not be rejected with the sentinels."""
        assert effective_skill_name("  interactive-map  ", ["place"], "search") == (
            "interactive-map"
        )


class TestSkillMustExist:
    """A name that matches no reachable skill must never reach the router.

    The router grants ``detected_skill_name`` absolute priority, so a
    hallucinated name silently steers the whole turn. ``mcp_excalidraw`` (2026-07-21)
    only ended up on the right path *by accident* — because no skill bore that name.
    """

    def test_unknown_skill_name_is_rejected(self, skills_cache: None) -> None:
        assert effective_skill_name("image-de-chat-realiste", ["image_generation"], "create") is (
            None
        )

    def test_known_skill_is_kept(self, skills_cache: None) -> None:
        assert effective_skill_name("interactive-map", ["place"], "search") == "interactive-map"

    def test_another_users_skill_is_not_reachable(self, skills_cache: None) -> None:
        """User-scoped skills belong to their owner: user B must not reach user A's."""
        SkillsCache._skills["user:owner-a:private-skill"] = {
            "name": "private-skill",
            "scope": "user",
            "owner_id": "owner-a",
            "dialogue": False,
        }
        assert effective_skill_name("private-skill", ["place"], "search", user_id="owner-b") is (
            None
        )
        assert effective_skill_name("private-skill", ["place"], "search", user_id="owner-a") == (
            "private-skill"
        )

    def test_unloaded_cache_does_not_suppress(self) -> None:
        """Fail open: an empty cache means "not loaded yet", not "no skill exists".

        Suppressing on an unloaded cache would disable every skill during the
        boot window instead of reporting a problem.
        """
        saved_skills, saved_loaded = SkillsCache._skills, SkillsCache._loaded
        SkillsCache._skills, SkillsCache._loaded = {}, False
        try:
            assert effective_skill_name("interactive-map", ["place"], "search") == (
                "interactive-map"
            )
        finally:
            SkillsCache._skills, SkillsCache._loaded = saved_skills, saved_loaded


class TestRetainedDetectionIsObservable:
    """A detection that survives every filter must be counted and logged.

    The 2026-07-27 investigation could not reproduce the ``skill-generator``
    hijack in 104 probes, while production hit it 4 times out of 6 — so the
    trigger is still unknown. Without a signal on the *kept* detections there
    is nothing to correlate a recurrence against: the suppression counters only
    describe what was thrown away.

    Labels stay bounded (one per skill, one per domain) and carry no PII.
    """

    def test_kept_detection_is_logged_with_its_domain(
        self, skills_cache: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.INFO):
            assert effective_skill_name("interactive-map", ["place"], "search") == (
                "interactive-map"
            )

        assert "skill_detection_retained" in caplog.text
        assert "interactive-map" in caplog.text
        assert "place" in caplog.text

    def test_suppressed_detection_is_not_logged_as_retained(
        self, skills_cache: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.INFO):
            assert effective_skill_name("null", ["image_generation"], "create") is None

        assert "skill_detection_retained" not in caplog.text

    def test_user_skill_names_do_not_reach_the_metric_label(self, skills_cache: None) -> None:
        """User-imported names are user input — never a Prometheus label value.

        System skills are a closed set (14), but any user can import a skill
        under any name. Labelling by raw name would make the series count grow
        with imports x domains, which is the textbook cardinality explosion.
        The log line still carries the exact name for diagnosis.
        """
        from src.domains.agents.services.analysis.skill_suppression import metric_skill_label

        SkillsCache._skills["user:owner-a:my-private-thing"] = {
            "name": "my-private-thing",
            "scope": "user",
            "owner_id": "owner-a",
            "dialogue": False,
        }
        assert metric_skill_label("interactive-map", "owner-a") == "interactive-map"
        assert metric_skill_label("my-private-thing", "owner-a") == "_user"
        # An unresolvable name must not be echoed either.
        assert metric_skill_label("never-heard-of-it", "owner-a") == "_user"


class TestDialoguePredicateReExport:
    """The predicate moved modules; the historical import path must survive."""

    def test_reexported_from_query_analyzer_service(self) -> None:
        from src.domains.agents.services.query_analyzer_service import (
            _is_dialogue_skill as reexported,
        )

        assert reexported is _is_dialogue_skill
