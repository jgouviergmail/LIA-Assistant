"""Characterization tests for the two highest-risk extracted async helpers:
``_resolve_response_context_summary`` (turn-type-aware summary + draft/rejection)
and ``_activate_response_skills`` (hybrid skill activation).

These pin the branching logic that the end-to-end suite exercises only on the
nominal path — reference turns, draft fast-execution, plan rejection/planner
error, and the passive-L2 vs ReAct-runner skill routes.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_TURN_TYPE,
    TURN_TYPE_ACTION,
    TURN_TYPE_CONVERSATIONAL,
    TURN_TYPE_REFERENCE,
)
from src.domains.agents.nodes.response_node import (
    _activate_response_skills,
    _resolve_response_context_summary,
)

_RESP = "src.domains.agents.nodes.response_node"


# ---------------------------------------------------------------------------
# _resolve_response_context_summary
# ---------------------------------------------------------------------------


async def _resolve(state, **kw):
    base = {
        "resolved_context": None,
        "current_turn_id": 0,
        "current_turn_registry": None,
        "override_action": None,
        "user_timezone": "UTC",
        "user_language": "fr",
        "user_viewport": "desktop",
    }
    base.update(kw)
    with patch(f"{_RESP}._execute_draft_if_confirmed", AsyncMock(return_value=None)):
        return await _resolve_response_context_summary(state, {"configurable": {}}, "r", **base)


@pytest.mark.asyncio
async def test_resolve_conversational_turn_yields_empty_summary():
    state = {STATE_KEY_TURN_TYPE: TURN_TYPE_CONVERSATIONAL, STATE_KEY_AGENT_RESULTS: {}}
    summary, rc_html, turn_type, rejection = await _resolve(state)
    assert summary == ""
    assert rc_html is None
    assert turn_type == TURN_TYPE_CONVERSATIONAL
    assert rejection is None


@pytest.mark.asyncio
async def test_resolve_action_turn_formats_agent_results():
    state = {STATE_KEY_TURN_TYPE: TURN_TYPE_ACTION, STATE_KEY_AGENT_RESULTS: {"0:emails": {}}}
    with patch(f"{_RESP}.format_agent_results_for_prompt", Mock(return_value="SUM")):
        summary, rc_html, turn_type, rejection = await _resolve(state)
    assert summary == "SUM"
    assert rc_html is None
    assert rejection is None


@pytest.mark.asyncio
async def test_resolve_reference_turn_uses_resolved_context_when_no_current_results():
    state = {STATE_KEY_TURN_TYPE: TURN_TYPE_REFERENCE, STATE_KEY_AGENT_RESULTS: {}}
    resolved_context = {"items": [{"id": "x"}], "source_turn_id": 1}
    with patch(f"{_RESP}._format_resolved_context_for_prompt", Mock(return_value="RCTX")):
        summary, rc_html, _turn, _rej = await _resolve(state, resolved_context=resolved_context)
    assert summary == "RCTX"
    # resolved_context is threaded to HTML rendering post-LLM.
    assert rc_html == resolved_context


@pytest.mark.asyncio
async def test_resolve_reference_turn_prefers_current_turn_results():
    # current-turn agent_results (keyed "0:...") take precedence over resolved_context items.
    state = {STATE_KEY_TURN_TYPE: TURN_TYPE_REFERENCE, STATE_KEY_AGENT_RESULTS: {"0:emails": {}}}
    resolved_context = {"items": [{"id": "x"}], "source_turn_id": 1}
    with patch(f"{_RESP}.format_agent_results_for_prompt", Mock(return_value="ENRICHED")):
        summary, rc_html, _turn, _rej = await _resolve(state, resolved_context=resolved_context)
    assert summary == "ENRICHED"
    assert rc_html is None  # not set on the current-turn-results branch


@pytest.mark.asyncio
async def test_resolve_plan_rejection_overrides_summary():
    state = {
        STATE_KEY_TURN_TYPE: TURN_TYPE_ACTION,
        STATE_KEY_AGENT_RESULTS: {},
        "plan_rejection_reason": "refused",
    }
    with (
        patch(f"{_RESP}.format_agent_results_for_prompt", Mock(return_value="SUM")),
        patch(f"{_RESP}._format_rejection_details", Mock(return_value="REJECTED")),
    ):
        summary, _rc, _turn, rejection = await _resolve(state)
    assert summary == "REJECTED"
    assert rejection == "refused"


@pytest.mark.asyncio
async def test_resolve_confirmed_draft_replaces_summary():
    state = {STATE_KEY_TURN_TYPE: TURN_TYPE_ACTION, STATE_KEY_AGENT_RESULTS: {}}
    draft_result = {"status": "success", "draft_id": "d1", "action": "confirm"}
    with (
        patch(f"{_RESP}._execute_draft_if_confirmed", AsyncMock(return_value=draft_result)),
        patch(f"{_RESP}._format_draft_execution_result", Mock(return_value="  DRAFT DONE  ")),
        patch(f"{_RESP}.format_agent_results_for_prompt", Mock(return_value="SUM")),
    ):
        summary, _rc, _turn, _rej = await _resolve_response_context_summary(
            state,
            {"configurable": {}},
            "r",
            resolved_context=None,
            current_turn_id=0,
            current_turn_registry=None,
            override_action=None,
            user_timezone="UTC",
            user_language="fr",
            user_viewport="desktop",
        )
    # Draft execution result replaces (and strips) the summary.
    assert summary == "DRAFT DONE"


# ---------------------------------------------------------------------------
# _activate_response_skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_skills_disabled_is_noop():
    registry = {"a": 1}
    with patch(f"{_RESP}.settings.skills_enabled", False):
        res = await _activate_response_skills(
            {},
            {"configurable": {}},
            "r",
            last_user_message="q",
            current_turn_registry=registry,
            react_result=None,
        )
    assert res.skills_context == ""
    assert res.skill_react_response is None
    assert res.activated_skill_name is None
    assert res.skill_registry_updates is None
    assert res.current_turn_registry is registry
    assert res.react_result is None


@pytest.mark.asyncio
async def test_activate_skills_always_loaded_passive_injection():
    with (
        patch(f"{_RESP}.settings.skills_enabled", True),
        patch(
            "src.domains.skills.cache.SkillsCache.get_always_loaded",
            Mock(return_value=[{"name": "always"}]),
        ),
        patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", Mock(return_value=None)),
        patch("src.domains.skills.cache.SkillsCache.get_by_name", Mock(return_value=None)),
        patch("src.domains.skills.activation.activate_skill", Mock(return_value="ALWAYS_CTX")),
    ):
        res = await _activate_response_skills(
            {},
            {"configurable": {}},
            "r",
            last_user_message="q",
            current_turn_registry=None,
            react_result=None,
        )
    assert "ALWAYS_CTX" in res.skills_context
    assert res.skill_react_response is None


@pytest.mark.asyncio
async def test_activate_skills_script_skill_runs_react_runner():
    """A query-analyzer-detected script skill runs the ReAct sub-agent and propagates registry."""
    state = {"query_intelligence": {"detected_skill_name": "my_skill"}}
    skill_data = {
        "scripts": ["run.py"],
        "references": [],
        "source_path": "/skills/my_skill/SKILL.md",
    }
    run_result = SimpleNamespace(
        iteration_count=1,
        final_message="Skill answer",
        duration_ms=42,
        accumulated_registry={"w1": {"type": "SKILL_APP"}},
    )
    runner_instance = Mock(run=AsyncMock(return_value=run_result))
    with (
        patch(f"{_RESP}.settings.skills_enabled", True),
        patch("src.domains.skills.cache.SkillsCache.get_always_loaded", Mock(return_value=[])),
        patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
            Mock(return_value=skill_data),
        ),
        patch("src.domains.skills.cache.SkillsCache.get_by_name", Mock(return_value=skill_data)),
        patch("src.domains.skills.tools.skills_tools", []),
        patch(
            "src.domains.agents.tools.react_runner.ReactSubAgentRunner",
            Mock(return_value=runner_instance),
        ),
    ):
        res = await _activate_response_skills(
            state,
            {"configurable": {}},
            "r",
            last_user_message="lance mon skill",
            current_turn_registry=None,
            react_result=None,
        )
    assert res.skill_react_response == "Skill answer"
    assert res.activated_skill_name == "my_skill"
    # Registry items accumulated by the runner are propagated for cross-turn persistence.
    assert res.skill_registry_updates == {"w1": {"type": "SKILL_APP"}}
    assert res.current_turn_registry == {"w1": {"type": "SKILL_APP"}}


@pytest.mark.asyncio
async def test_activate_skills_runner_error_falls_back_to_passive_l2():
    """If the ReAct runner raises, activation degrades gracefully to passive L2 injection."""
    state = {"query_intelligence": {"detected_skill_name": "my_skill"}}
    skill_data = {
        "scripts": ["run.py"],
        "references": [],
        "source_path": "/skills/my_skill/SKILL.md",
    }
    runner_instance = Mock(run=AsyncMock(side_effect=RuntimeError("runner boom")))
    with (
        patch(f"{_RESP}.settings.skills_enabled", True),
        patch("src.domains.skills.cache.SkillsCache.get_always_loaded", Mock(return_value=[])),
        patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
            Mock(return_value=skill_data),
        ),
        patch("src.domains.skills.cache.SkillsCache.get_by_name", Mock(return_value=skill_data)),
        patch("src.domains.skills.tools.skills_tools", []),
        patch(
            "src.domains.agents.tools.react_runner.ReactSubAgentRunner",
            Mock(return_value=runner_instance),
        ),
        patch("src.domains.skills.activation.activate_skill", Mock(return_value="FALLBACK_L2")),
    ):
        res = await _activate_response_skills(
            state,
            {"configurable": {}},
            "r",
            last_user_message="lance mon skill",
            current_turn_registry=None,
            react_result=None,
        )
    # No react response produced; the passive L2 content is injected instead.
    assert res.skill_react_response is None
    assert "FALLBACK_L2" in res.skills_context
