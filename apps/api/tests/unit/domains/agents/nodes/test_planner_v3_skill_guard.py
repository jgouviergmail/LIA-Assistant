"""Unit tests for the ``_has_potential_skill_match`` guard in planner_node_v3.

Verifies that the early insufficient content detection is correctly skipped
when the QueryAnalyzer has semantically identified a skill (deterministic or
not), and is otherwise allowed to run.

The guard is intentionally minimalist: it checks the presence of
``QueryIntelligence.detected_skill_name`` without touching the cache.
Downstream code enforces the proper user-scoped skill resolution.
"""

from unittest.mock import MagicMock

import pytest

from src.domains.agents.nodes.planner_node_v3 import _has_potential_skill_match


def _make_intelligence(detected_skill_name: str | None = None) -> MagicMock:
    """Create a minimal QueryIntelligence mock."""
    intel = MagicMock()
    intel.detected_skill_name = detected_skill_name
    return intel


class TestHasPotentialSkillMatch:
    """Tests for _has_potential_skill_match guard function."""

    @pytest.mark.unit
    def test_guard_triggers_when_skill_detected(self):
        """Any detected skill name → guard returns True (skip early detection)."""
        intel = _make_intelligence(detected_skill_name="briefing-quotidien")
        assert _has_potential_skill_match(intel) is True

    @pytest.mark.unit
    def test_guard_triggers_for_non_deterministic_skill(self):
        """Guard does not distinguish deterministic vs non-deterministic.

        The downstream planner pipeline makes that distinction; the guard only
        needs to prevent early clarification when a skill-driven flow is on.
        """
        intel = _make_intelligence(detected_skill_name="research-assistant")
        assert _has_potential_skill_match(intel) is True

    @pytest.mark.unit
    def test_guard_does_not_trigger_when_no_skill_detected(self):
        """No detected skill → guard returns False (early detection runs)."""
        intel = _make_intelligence(detected_skill_name=None)
        assert _has_potential_skill_match(intel) is False

    @pytest.mark.unit
    def test_guard_does_not_trigger_on_empty_string(self):
        """Empty string skill name is treated as no detection."""
        intel = _make_intelligence(detected_skill_name="")
        assert _has_potential_skill_match(intel) is False

    @pytest.mark.unit
    def test_guard_resilient_to_missing_attribute(self):
        """Missing ``detected_skill_name`` attribute must not raise."""
        intel = MagicMock(spec=[])  # no detected_skill_name attribute
        assert _has_potential_skill_match(intel) is False
