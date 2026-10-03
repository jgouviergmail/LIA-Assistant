"""The validated selection reaches both real prompt assembly paths, and expires."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.core.card_composition import CardComposition, card_composition_ctx
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.nodes import react_context
from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue
from src.domains.agents.services.smart_planner_service import SmartPlannerService

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_pipeline_and_react_receive_only_the_current_validated_selection(monkeypatch):
    monkeypatch.setattr(
        "src.domains.agents.services.plan_pattern_learner.get_learned_patterns_prompt",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.domains.diagnostics.advisor.get_active_degradations", AsyncMock(return_value=[])
    )
    for name in (
        "build_memory_profile_block",
        "build_knowledge_block",
        "build_user_model_block",
        "build_journal_directives_block",
        "build_degradations_block",
        "build_mcp_auth_notices_block",
    ):
        monkeypatch.setattr(react_context, name, AsyncMock(return_value=None))
    monkeypatch.setattr(react_context, "build_reference_resolution_block", lambda *args: None)
    monkeypatch.setattr(react_context, "build_skills_catalog_block", lambda: None)
    intelligence = QueryIntelligence(
        original_query="Prepare this reply",
        english_query="Prepare this reply",
        immediate_intent="send",
        immediate_confidence=1.0,
        user_goal=UserGoal.COMMUNICATE,
        goal_reasoning="Reply to selected email",
        domains=["emails"],
    )
    catalogue = FilteredCatalogue([], 0, 0, ["emails"], [])
    planner = SmartPlannerService()
    monkeypatch.setattr(planner, "_build_iot_device_context", AsyncMock(return_value=""))
    monkeypatch.setattr(planner, "_build_skills_catalog", lambda *args: "")
    monkeypatch.setattr(planner, "_build_sub_agents_section", lambda: "")

    async def build():
        pipeline = await planner._build_prompt(intelligence, catalogue, {})
        react = await react_context.build_setup_blocks({}, {}, intelligence)
        return pipeline, "\n".join(react.blocks)

    before = await build()
    assert all("<CardComposition>" not in prompt for prompt in before)
    token = card_composition_ctx.set(
        CardComposition(UUID(int=1), "EMAIL", "exact-target", "reply", "google_gmail")
    )
    try:
        selected = await build()
        for prompt in selected:
            assert prompt.count("<CardComposition>") == 1
            assert '"target_id": "exact-target"' in prompt
            assert "HITL" in prompt
            assert "account_binding" not in prompt
    finally:
        card_composition_ctx.reset(token)
    for prompt in await build():
        assert "<CardComposition>" not in prompt and "exact-target" not in prompt
