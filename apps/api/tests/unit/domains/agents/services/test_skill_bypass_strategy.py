"""Unit tests for SkillBypassStrategy — relaxed domain matching + scope filtering.

Verifies that:
1. Deterministic skill templates match with up to N missing domains
2. Steps requiring unavailable OAuth scopes are filtered out
3. Exact match still works (backward compatibility)
4. Edge cases: empty scopes, all steps filtered, inactive skills
"""

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.planner.strategies.skill_bypass import (
    SkillBypassStrategy,
    _filter_steps_by_scopes,
)

# ============================================================================
# Fixtures and helpers
# ============================================================================


def _make_intelligence(
    primary_domain: str | None = None,
    domains: list[str] | None = None,
) -> MagicMock:
    """Create a minimal QueryIntelligence mock."""
    intel = MagicMock()
    intel.primary_domain = primary_domain
    intel.domains = domains or []
    intel.immediate_intent = "search"
    intel.user_goal = MagicMock(value="information")
    intel.anticipated_needs = []
    intel.resolved_references = None
    return intel


def _make_skill(
    name: str,
    agent_names: list[str],
    deterministic: bool = True,
    priority: int = 50,
) -> dict:
    """Create a skill dict matching SkillsCache format."""
    steps = [
        {
            "step_id": f"step_{a}",
            "agent_name": f"{a}_agent",
            "tool_name": f"get_{a}_tool",
        }
        for a in agent_names
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
# Override: briefing tolerates up to 2 missing domains (5 domains total)
BRIEFING_SKILL["plan_template"]["max_missing_domains"] = 2

SINGLE_SKILL = _make_skill(
    "coaching-productivite",
    ["task"],
    priority=60,
)


def _make_config(oauth_scopes: list[str] | None = None) -> dict:
    """Create a minimal RunnableConfig dict."""
    return {
        "configurable": {
            "user_id": "test-user-123",
            "run_id": "test-run",
            "session_id": "test-session",
            "oauth_scopes": oauth_scopes or [],
        }
    }


@dataclass(frozen=True)
class _MockPermissions:
    required_scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _MockManifest:
    name: str
    permissions: _MockPermissions


# Tool manifests for scope checking
TOOL_MANIFESTS = {
    "get_event_tool": _MockManifest("get_event_tool", _MockPermissions(["calendar.read"])),
    "get_task_tool": _MockManifest("get_task_tool", _MockPermissions(["tasks.read"])),
    "get_weather_tool": _MockManifest("get_weather_tool", _MockPermissions([])),
    "get_email_tool": _MockManifest("get_email_tool", _MockPermissions(["gmail.read"])),
    "get_reminder_tool": _MockManifest("get_reminder_tool", _MockPermissions([])),
}


@pytest.fixture(autouse=True)
def _enable_skills():
    """Enable skills feature flag for all tests."""
    mock_settings = MagicMock()
    mock_settings.skills_enabled = True
    with patch("src.core.config.get_settings", return_value=mock_settings):
        yield


@pytest.fixture(autouse=True)
def _skills_cache():
    """Mock SkillsCache as loaded with test skills."""
    with (
        patch(
            "src.domains.skills.cache.SkillsCache.is_loaded",
            return_value=True,
        ),
        patch(
            "src.domains.skills.cache.SkillsCache.get_all",
            return_value=[BRIEFING_SKILL, SINGLE_SKILL],
        ),
        patch(
            "src.domains.skills.cache.SkillsCache.get_for_user",
            return_value=[BRIEFING_SKILL, SINGLE_SKILL],
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _active_skills_all():
    """Default: all skills active."""
    with patch("src.core.context.active_skills_ctx") as ctx:
        ctx.get.return_value = None  # None = all considered
        yield ctx


@pytest.fixture(autouse=True)
def _mock_registry():
    """Mock global registry for scope-based filtering."""
    mock_registry = MagicMock()
    mock_registry.get_tool_manifest.side_effect = lambda name: TOOL_MANIFESTS.get(name)
    with patch(
        "src.domains.agents.registry.get_global_registry",
        return_value=mock_registry,
    ):
        yield


# ============================================================================
# can_handle — relaxed domain matching
# ============================================================================


class TestCanHandle:
    """Tests for SkillBypassStrategy.can_handle()."""

    @pytest.mark.unit
    async def test_briefing_with_two_missing_domains(self):
        """Briefing should match with 3/5 domains (email + reminder missing).

        This is the exact production scenario: 'Fais mon briefing quotidien'
        gets domains {weather, event, task} but skill needs {event, task,
        weather, email, reminder}. With max_missing_domains=2 in the template,
        2 missing domains should match.
        """
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task"],
        )
        assert await strategy.can_handle(intel) is True

    @pytest.mark.unit
    async def test_exact_match(self):
        """All 5 domains present → should match."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email", "reminder"],
        )
        assert await strategy.can_handle(intel) is True

    @pytest.mark.unit
    async def test_superset_match(self):
        """Extra domains beyond template → should still match."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email", "reminder", "brave"],
        )
        assert await strategy.can_handle(intel) is True

    @pytest.mark.unit
    async def test_three_missing_no_match(self):
        """3 missing domains → exceeds max_missing_domains=2 → no match."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event"],
        )
        assert await strategy.can_handle(intel) is False

    @pytest.mark.unit
    async def test_single_domain_no_match_multidomain_skill(self):
        """Single domain 'event' → 4 missing out of 5 → no match for briefing."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(primary_domain="event", domains=[])
        # coaching has task only, event != task → no match either
        assert await strategy.can_handle(intel) is False

    @pytest.mark.unit
    async def test_single_domain_skill_exact_match(self):
        """Single-domain skill 'task' → exact match with primary_domain=task."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(primary_domain="task", domains=[])
        assert await strategy.can_handle(intel) is True

    @pytest.mark.unit
    async def test_inactive_skill_not_matched(self):
        """Skill not in active set should not match even with full domain overlap."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email"],
        )
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = {"coaching-productivite"}  # briefing NOT active
            # coaching: domain=task, query has task → 0 missing → matches
            assert await strategy.can_handle(intel) is True

        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = set()  # NO skill active
            assert await strategy.can_handle(intel) is False


# ============================================================================
# plan — relaxed matching + scope filtering
# ============================================================================


class TestPlan:
    """Tests for SkillBypassStrategy.plan()."""

    @pytest.mark.unit
    async def test_briefing_with_missing_domains_and_all_scopes(self):
        """Briefing with 3/5 domains + all scopes → 5-step plan."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task"],
        )
        config = _make_config(oauth_scopes=["calendar.read", "tasks.read", "gmail.read"])
        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is True
        assert result.plan is not None
        assert len(result.plan.steps) == 5
        assert result.plan.metadata["skill_name"] == "briefing-quotidien"
        assert result.plan.metadata["skill_bypass"] is True

    @pytest.mark.unit
    async def test_briefing_without_gmail_scope_filters_email_step(self):
        """Briefing with 3/5 domains + no gmail scope → 4-step plan (email filtered)."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task"],
        )
        config = _make_config(oauth_scopes=["calendar.read", "tasks.read"])
        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is True
        assert result.plan is not None
        assert len(result.plan.steps) == 4
        # Email step should be filtered out, reminder kept (no scopes needed)
        step_agents = [s.agent_name for s in result.plan.steps]
        assert "email_agent" not in step_agents
        assert "event_agent" in step_agents
        assert "task_agent" in step_agents
        assert "weather_agent" in step_agents
        assert "reminder_agent" in step_agents

    @pytest.mark.unit
    async def test_briefing_exact_match_all_scopes(self):
        """All 5 domains + all scopes → 5-step plan."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email", "reminder"],
        )
        config = _make_config(oauth_scopes=["calendar.read", "tasks.read", "gmail.read"])
        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is True
        assert len(result.plan.steps) == 5

    @pytest.mark.unit
    async def test_no_matching_skill_returns_failure(self):
        """No domain overlap → PlanningResult with success=False."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(primary_domain="contact", domains=["brave"])
        config = _make_config()
        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is False
        assert result.plan is None

    @pytest.mark.unit
    async def test_missing_oauth_scopes_key_in_config_falls_back(self):
        """Config without oauth_scopes key → empty set → scope-requiring steps filtered."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task"],
        )
        # Config explicitly without oauth_scopes key
        config = {
            "configurable": {
                "user_id": "test-user",
                "run_id": "test-run",
                "session_id": "test-session",
            }
        }
        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is True
        # Tools with required scopes should be filtered (no scopes available)
        # Only weather and reminder (no required scopes) should remain
        step_agents = [s.agent_name for s in result.plan.steps]
        assert "weather_agent" in step_agents
        assert "reminder_agent" in step_agents
        assert "email_agent" not in step_agents
        assert "event_agent" not in step_agents
        assert "task_agent" not in step_agents

    @pytest.mark.unit
    async def test_inactive_skill_skipped_in_plan(self):
        """Skill not in active set should be skipped during planning."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(
            primary_domain="weather",
            domains=["event", "task", "email"],
        )
        config = _make_config(oauth_scopes=["calendar.read", "tasks.read", "gmail.read"])
        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = set()  # No skill active
            result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is False


# ============================================================================
# _filter_steps_by_scopes
# ============================================================================


class TestFilterStepsByScopes:
    """Tests for the _filter_steps_by_scopes helper."""

    @pytest.mark.unit
    def test_keeps_steps_with_matching_scopes(self):
        """Steps with satisfied scopes are kept."""
        steps = [
            {"step_id": "s1", "tool_name": "get_event_tool"},
            {"step_id": "s2", "tool_name": "get_weather_tool"},
        ]
        result = _filter_steps_by_scopes(steps, {"calendar.read"})
        assert len(result) == 2

    @pytest.mark.unit
    def test_filters_steps_with_missing_scopes(self):
        """Steps requiring unavailable scopes are removed."""
        steps = [
            {"step_id": "s1", "tool_name": "get_event_tool"},
            {"step_id": "s2", "tool_name": "get_email_tool"},
        ]
        result = _filter_steps_by_scopes(steps, {"calendar.read"})
        assert len(result) == 1
        assert result[0]["step_id"] == "s1"

    @pytest.mark.unit
    def test_keeps_steps_without_tool_name(self):
        """Steps without tool_name (e.g., CONDITIONAL) are always kept."""
        steps = [
            {"step_id": "s1", "agent_name": "some_agent"},
        ]
        result = _filter_steps_by_scopes(steps, set())
        assert len(result) == 1

    @pytest.mark.unit
    def test_keeps_steps_with_no_required_scopes(self):
        """Tools without required scopes (e.g., weather) are kept even with empty user scopes."""
        steps = [
            {"step_id": "s1", "tool_name": "get_weather_tool"},
        ]
        result = _filter_steps_by_scopes(steps, set())
        assert len(result) == 1

    @pytest.mark.unit
    def test_unknown_tool_kept(self):
        """Tools not in registry (e.g., MCP tools) are kept."""
        steps = [
            {"step_id": "s1", "tool_name": "mcp_unknown_tool"},
        ]
        result = _filter_steps_by_scopes(steps, set())
        assert len(result) == 1

    @pytest.mark.unit
    def test_empty_steps_returns_empty(self):
        """Empty input returns empty output."""
        result = _filter_steps_by_scopes([], {"calendar.read"})
        assert result == []

    @pytest.mark.unit
    def test_depends_on_sanitized_after_filtering(self):
        """depends_on references to removed steps are cleaned up."""
        steps = [
            {"step_id": "s1", "tool_name": "get_event_tool", "depends_on": []},
            {"step_id": "s2", "tool_name": "get_email_tool", "depends_on": ["s1"]},
            {"step_id": "s3", "tool_name": "get_weather_tool", "depends_on": ["s1", "s2"]},
        ]
        # s2 (email) requires gmail.read → filtered out
        result = _filter_steps_by_scopes(steps, {"calendar.read"})
        assert len(result) == 2
        assert result[0]["step_id"] == "s1"
        assert result[1]["step_id"] == "s3"
        # s3's depends_on should no longer reference s2
        assert result[1]["depends_on"] == ["s1"]
        # Original step dict must NOT be mutated (cache safety)
        assert steps[2]["depends_on"] == ["s1", "s2"]
