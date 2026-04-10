"""
Unit tests for _has_potential_skill_match guard in planner_node_v3.

Verifies that the early insufficient content detection is correctly
skipped when a deterministic skill has high domain overlap with the
query, preventing false positive clarification requests for multi-domain
skill triggers (e.g., "briefing quotidien" misclassified as "create event").
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.nodes.planner_node_v3 import _has_potential_skill_match


def _make_intelligence(
    primary_domain: str | None = None,
    domains: list[str] | None = None,
) -> MagicMock:
    """Create a minimal QueryIntelligence mock."""
    intel = MagicMock()
    intel.primary_domain = primary_domain
    intel.domains = domains or []
    return intel


def _make_skill(
    name: str,
    agent_names: list[str],
    deterministic: bool = True,
    priority: int = 50,
) -> dict:
    """Create a skill dict matching SkillsCache format."""
    steps = [
        {"step_id": f"step_{i}", "agent_name": f"{a}_agent", "tool_name": f"{a}_tool"}
        for i, a in enumerate(agent_names)
    ]
    return {
        "name": name,
        "priority": priority,
        "plan_template": {
            "deterministic": deterministic,
            "steps": steps,
        },
    }


BRIEFING_SKILL = _make_skill(
    "briefing-quotidien",
    ["event", "task", "weather", "email", "reminder"],
    priority=70,
)
# Briefing tolerates up to 2 missing domains (5 domains total)
BRIEFING_SKILL["plan_template"]["max_missing_domains"] = 2

COACHING_SKILL = _make_skill(
    "coaching-productivite",
    ["task"],
    priority=60,
)


@pytest.fixture(autouse=True)
def _enable_skills():
    """Enable skills feature flag for all tests."""
    mock_settings = MagicMock()
    mock_settings.skills_enabled = True
    with patch(
        "src.core.config.get_settings",
        return_value=mock_settings,
    ):
        yield


@pytest.fixture(autouse=True)
def _skills_cache_loaded():
    """Mock SkillsCache as loaded with test skills."""
    with (
        patch(
            "src.domains.skills.cache.SkillsCache.is_loaded",
            return_value=True,
        ),
        patch(
            "src.domains.skills.cache.SkillsCache.get_all",
            return_value=[BRIEFING_SKILL, COACHING_SKILL],
        ),
    ):
        yield


class TestHasPotentialSkillMatch:
    """Tests for _has_potential_skill_match guard function."""

    # =================================================================
    # Positive cases: should detect potential match (skip early detection)
    # =================================================================

    def test_briefing_with_two_missing_domains(self):
        """Briefing skill should match when 3/5 domains detected (email+reminder missing).

        This is the exact production scenario: "Fais mon briefing quotidien"
        gets domains {weather, event, task, brave} but skill needs {event, task,
        weather, email, reminder}. With max_missing_domains=2, this should match.
        """
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "brave"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = {"briefing-quotidien", "coaching-productivite"}
            assert _has_potential_skill_match(intel) is True

    def test_briefing_exact_match(self):
        """Exact domain match should also trigger (superset of relaxed match)."""
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email", "reminder"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = {"briefing-quotidien"}
            assert _has_potential_skill_match(intel) is True

    def test_briefing_superset_domains(self):
        """Query with extra domains should still match (superset)."""
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email", "reminder", "brave", "contact"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = None  # None = all skills considered
            assert _has_potential_skill_match(intel) is True

    def test_single_domain_skill_exact_match(self):
        """Single-domain skill should match with exact domain overlap."""
        intel = _make_intelligence(primary_domain="task", domains=[])
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = None
            assert _has_potential_skill_match(intel) is True

    # =================================================================
    # Negative cases: should NOT match (early detection stays active)
    # =================================================================

    def test_single_domain_query_vs_multidomain_skill(self):
        """Single-domain query should NOT match a 5-domain skill.

        "Créer un événement" with domains={event} has only 1/5 overlap
        with briefing {event,task,weather,email,reminder}. This is a real
        "create event", not a skill invocation.
        """
        intel = _make_intelligence(primary_domain="event", domains=[])
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = {"briefing-quotidien"}
            # coaching (single domain=task) doesn't match event
            # briefing: 1/5 overlap, 4 missing > max_missing_domains=2 → no match
            assert _has_potential_skill_match(intel) is False

    def test_two_domains_vs_five_domain_skill(self):
        """Two domains should NOT match a 5-domain skill (3 missing > max_missing_domains=2)."""
        intel = _make_intelligence(
            primary_domain="event",
            domains=["weather"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = {"briefing-quotidien"}
            assert _has_potential_skill_match(intel) is False

    def test_no_domain_overlap(self):
        """No domain overlap should never match."""
        intel = _make_intelligence(
            primary_domain="contact",
            domains=["brave"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = None
            assert _has_potential_skill_match(intel) is False

    def test_empty_domains(self):
        """Empty query domains should never match."""
        intel = _make_intelligence(primary_domain=None, domains=[])
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = None
            assert _has_potential_skill_match(intel) is False

    # =================================================================
    # Filtering: active skills, feature flags, cache state
    # =================================================================

    def test_inactive_skill_not_considered(self):
        """Skill not in active_skills set should be ignored.

        Query domains overlap 3/4 with briefing, but briefing is not active.
        Coaching is active but has only 1 domain (task) — not enough overlap
        since query primary_domain=weather, domains=[event, brave] don't
        include 'task'.
        """
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "brave"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            # Only coaching active (domain=task), not briefing
            # Query = {weather, event, brave} → no overlap with coaching {task}
            ctx.get.return_value = {"coaching-productivite"}
            assert _has_potential_skill_match(intel) is False

    def test_skills_disabled_returns_false(self):
        """When SKILLS_ENABLED=False, should always return False."""
        mock_settings = MagicMock()
        mock_settings.skills_enabled = False
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email"],
        )
        with patch(
            "src.core.config.get_settings",
            return_value=mock_settings,
        ):
            assert _has_potential_skill_match(intel) is False

    def test_cache_not_loaded_returns_false(self):
        """When SkillsCache is not loaded, should always return False."""
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email"],
        )
        with patch(
            "src.domains.skills.cache.SkillsCache.is_loaded",
            return_value=False,
        ):
            assert _has_potential_skill_match(intel) is False

    def test_non_deterministic_skill_ignored(self):
        """Non-deterministic skills should not be considered for bypass guard."""
        non_det_skill = _make_skill(
            "research-skill",
            ["brave", "email", "task", "event"],
            deterministic=False,
        )
        intel = _make_intelligence(
            primary_domain="brave",
            domains=["email", "task", "event"],
        )
        with (
            patch(
                "src.domains.skills.cache.SkillsCache.get_all",
                return_value=[non_det_skill],
            ),
            patch("src.core.context.active_skills_ctx") as ctx,
        ):
            ctx.get.return_value = None
            assert _has_potential_skill_match(intel) is False

    # =================================================================
    # Edge cases
    # =================================================================

    def test_skill_with_no_steps(self):
        """Skill with empty steps list should not match."""
        empty_skill = {
            "name": "empty-skill",
            "plan_template": {"deterministic": True, "steps": []},
        }
        intel = _make_intelligence(primary_domain="event", domains=["task"])
        with (
            patch(
                "src.domains.skills.cache.SkillsCache.get_all",
                return_value=[empty_skill],
            ),
            patch("src.core.context.active_skills_ctx") as ctx,
        ):
            ctx.get.return_value = None
            assert _has_potential_skill_match(intel) is False

    def test_active_skills_none_considers_all(self):
        """active_skills=None means all skills are considered (backward compat)."""
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "brave"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = None  # None = consider all
            assert _has_potential_skill_match(intel) is True

    def test_primary_domain_added_to_domains(self):
        """primary_domain should be included in the query domains set."""
        # 3 domains from list + 1 from primary = {weather, event, task, email} → exact match
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = None
            assert _has_potential_skill_match(intel) is True
