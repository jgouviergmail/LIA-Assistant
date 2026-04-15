"""Unit tests for SkillBypassStrategy — semantic identification + scope filtering.

Verifies that:
1. ``can_handle`` returns True iff ``detected_skill_name`` is set (cheap presence check).
2. ``plan`` builds a plan only when the identified skill exists (user-scoped lookup),
   is deterministic, and is active for the user.
3. Steps requiring unavailable OAuth scopes are filtered out.
4. Edge cases: skill not found, non-deterministic, inactive, empty steps.
5. User isolation: lookups go through ``SkillsCache.get_by_name_for_user``.
"""

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.planner.strategies.skill_bypass import (
    SkillBypassStrategy,
    _filter_steps_by_scopes,
)


def _make_intelligence(
    detected_skill_name: str | None = None,
    domains: list[str] | None = None,
    primary_domain: str | None = None,
) -> MagicMock:
    """Create a minimal QueryIntelligence mock."""
    intel = MagicMock()
    intel.detected_skill_name = detected_skill_name
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
    scope: str = "admin",
    owner_id: str | None = None,
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
        "scope": scope,
        "owner_id": owner_id,
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

COACHING_SKILL = _make_skill(
    "coaching-productivite",
    ["task"],
    priority=60,
)

NON_DETERMINISTIC_SKILL = _make_skill(
    "research-assistant",
    ["brave"],
    deterministic=False,
)


def _make_config(
    user_id: str = "test-user-123",
    oauth_scopes: list[str] | None = None,
) -> dict:
    """Create a minimal RunnableConfig dict."""
    return {
        "configurable": {
            "user_id": user_id,
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


TOOL_MANIFESTS = {
    "get_event_tool": _MockManifest("get_event_tool", _MockPermissions(["calendar.read"])),
    "get_task_tool": _MockManifest("get_task_tool", _MockPermissions(["tasks.read"])),
    "get_weather_tool": _MockManifest("get_weather_tool", _MockPermissions([])),
    "get_email_tool": _MockManifest("get_email_tool", _MockPermissions(["gmail.read"])),
    "get_reminder_tool": _MockManifest("get_reminder_tool", _MockPermissions([])),
    "get_brave_tool": _MockManifest("get_brave_tool", _MockPermissions([])),
}


def _make_cache_lookup(skills: list[dict]):
    """Build a get_by_name_for_user side_effect that returns skills by name.

    User override semantics are preserved: the first skill whose ``name`` matches
    and whose ``owner_id`` equals the requested user is preferred, falling back
    to the admin match.
    """

    def _lookup(name: str, user_id: str) -> dict | None:
        admin_match = None
        for s in skills:
            if s["name"] != name:
                continue
            if s["scope"] == "user" and s.get("owner_id") == user_id:
                return s
            if s["scope"] == "admin":
                admin_match = s
        return admin_match

    return _lookup


@pytest.fixture(autouse=True)
def _skills_cache():
    """Mock SkillsCache with test skills.

    Uses ``get_by_name_for_user`` exclusively to ensure user-scoped lookups.
    """
    default_skills = [BRIEFING_SKILL, COACHING_SKILL, NON_DETERMINISTIC_SKILL]
    with patch(
        "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
        side_effect=_make_cache_lookup(default_skills),
    ):
        yield


@pytest.fixture(autouse=True)
def _active_skills_all():
    """Default: all skills active (active_skills_ctx.get() returns None)."""
    with patch("src.core.context.active_skills_ctx") as ctx:
        ctx.get.return_value = None
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
# can_handle — cheap presence check on detected_skill_name
# ============================================================================


class TestCanHandle:
    """Tests for SkillBypassStrategy.can_handle()."""

    @pytest.mark.unit
    async def test_returns_true_when_skill_detected(self):
        """Any detected skill name triggers can_handle=True (verification deferred to plan)."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="briefing-quotidien")
        assert await strategy.can_handle(intel) is True

    @pytest.mark.unit
    async def test_returns_false_when_no_skill_detected(self):
        """No detected skill → can_handle=False, strategy yields to next."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name=None)
        assert await strategy.can_handle(intel) is False

    @pytest.mark.unit
    async def test_returns_true_even_for_non_deterministic_skill(self):
        """can_handle is minimalist; deterministic check happens in plan()."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="research-assistant")
        assert await strategy.can_handle(intel) is True


# ============================================================================
# plan — user-scoped resolution + deterministic filter + scope filtering
# ============================================================================


class TestPlan:
    """Tests for SkillBypassStrategy.plan()."""

    @pytest.mark.unit
    async def test_deterministic_skill_with_all_scopes_builds_full_plan(self):
        """Detected deterministic skill + all scopes → full-template plan."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="briefing-quotidien")
        config = _make_config(oauth_scopes=["calendar.read", "tasks.read", "gmail.read"])

        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is True
        assert result.plan is not None
        assert len(result.plan.steps) == 5
        assert result.plan.metadata["skill_name"] == "briefing-quotidien"
        assert result.plan.metadata["skill_bypass"] is True

    @pytest.mark.unit
    async def test_missing_gmail_scope_filters_email_step(self):
        """Skill steps whose tools require unavailable scopes are dropped gracefully."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="briefing-quotidien")
        config = _make_config(oauth_scopes=["calendar.read", "tasks.read"])

        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is True
        assert result.plan is not None
        step_agents = [s.agent_name for s in result.plan.steps]
        assert "email_agent" not in step_agents
        assert "event_agent" in step_agents
        assert "task_agent" in step_agents
        assert "weather_agent" in step_agents
        assert "reminder_agent" in step_agents
        assert len(result.plan.steps) == 4

    @pytest.mark.unit
    async def test_non_deterministic_skill_returns_failure(self):
        """Non-deterministic skills are left to the LLM planner."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="research-assistant")
        config = _make_config()

        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is False
        assert result.plan is None
        assert "not deterministic" in (result.error or "")

    @pytest.mark.unit
    async def test_skill_not_in_cache_returns_failure(self):
        """Unknown skill name → graceful failure, no crash."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="non-existent-skill")
        config = _make_config()

        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is False
        assert result.plan is None
        assert "not found" in (result.error or "")

    @pytest.mark.unit
    async def test_no_detected_skill_returns_failure(self):
        """Empty detected_skill_name → graceful failure."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name=None)
        config = _make_config()

        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is False
        assert result.plan is None

    @pytest.mark.unit
    async def test_inactive_skill_returns_failure(self):
        """Skill not in active_skills_ctx → not matched even when identified."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="briefing-quotidien")
        config = _make_config(oauth_scopes=["calendar.read", "tasks.read", "gmail.read"])

        with patch("src.core.context.active_skills_ctx") as ctx:
            ctx.get.return_value = {"coaching-productivite"}  # briefing not active
            result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is False
        assert result.plan is None
        assert "not active" in (result.error or "")

    @pytest.mark.unit
    async def test_all_steps_filtered_by_scopes_returns_failure(self):
        """Scope-filtering that strips every step yields a failure result."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="coaching-productivite")
        config = _make_config(oauth_scopes=[])  # coaching needs tasks.read

        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is False
        assert result.plan is None

    @pytest.mark.unit
    async def test_user_override_prefers_user_skill_over_admin(self):
        """A user's own skill with same name must override the admin version."""
        user_id = "alice"
        alice_briefing = _make_skill(
            "briefing-quotidien",
            ["task"],
            deterministic=False,  # Alice's version is non-deterministic
            scope="user",
            owner_id=user_id,
        )

        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="briefing-quotidien")
        config = _make_config(user_id=user_id)

        with patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
            side_effect=_make_cache_lookup([BRIEFING_SKILL, alice_briefing]),
        ):
            result = await strategy.plan(intelligence=intel, config=config)

        # Alice's version is non-deterministic → bypass declines (correctly)
        assert result.success is False
        assert "not deterministic" in (result.error or "")

    @pytest.mark.unit
    async def test_missing_oauth_scopes_key_in_config_falls_back_to_empty(self):
        """Config without oauth_scopes key → scope-requiring steps filtered out."""
        strategy = SkillBypassStrategy()
        intel = _make_intelligence(detected_skill_name="briefing-quotidien")
        config = {
            "configurable": {
                "user_id": "test-user",
                "run_id": "test-run",
                "session_id": "test-session",
            }
        }

        result = await strategy.plan(intelligence=intel, config=config)

        assert result.success is True
        step_agents = [s.agent_name for s in result.plan.steps]
        # Only tools without required scopes remain
        assert "weather_agent" in step_agents
        assert "reminder_agent" in step_agents
        assert "email_agent" not in step_agents
        assert "event_agent" not in step_agents
        assert "task_agent" not in step_agents


# ============================================================================
# _filter_steps_by_scopes — unchanged behaviour
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
        result = _filter_steps_by_scopes(steps, {"calendar.read"})
        assert len(result) == 2
        assert result[0]["step_id"] == "s1"
        assert result[1]["step_id"] == "s3"
        assert result[1]["depends_on"] == ["s1"]
        # Original step dict must NOT be mutated (cache safety)
        assert steps[2]["depends_on"] == ["s1", "s2"]
