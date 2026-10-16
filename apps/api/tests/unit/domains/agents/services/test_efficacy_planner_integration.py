"""The actual planner prompt path consumes the shared policy without a new model call."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.analysis.efficacy_context import EfficacyAnalysis, EfficacyTurnContext
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue
from src.domains.agents.services.smart_planner_service import SmartPlannerService
from src.domains.psyche.efficacy_contracts import (
    EfficacyEpisodeView,
    EfficacyEpoch,
    EfficacyObservation,
)
from src.domains.psyche.efficacy_scoring import build_profile

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "answer,expected_adjustment", [(None, True), ("Le dossier principal", False)]
)
async def test_real_planner_keeps_clarification_only_while_the_choice_is_unresolved(
    monkeypatch, answer, expected_adjustment
):
    from src.domains.agents.services import efficacy_runtime, plan_pattern_learner
    from src.domains.diagnostics import advisor

    now = datetime.now(UTC)
    owner = uuid4()
    turn = EfficacyTurnContext(
        owner_id=owner,
        run_id="real-planner-run",
        epoch=EfficacyEpoch(state_id=uuid4(), generation=uuid4()),
        analysis=EfficacyAnalysis(domains=("technical",), ambiguous=True),
        issued_at=now,
    )
    episodes = [
        EfficacyEpisodeView(
            run_id=str(uuid4()),
            message_id=uuid4(),
            terminal_at=now,
            observations=(
                EfficacyObservation(
                    domain="technical", verdict="unknown", reason="insufficient_evidence"
                ),
            ),
            feedback="unhelpful",
        )
        for _ in range(5)
    ]
    profile = build_profile(episodes, now=now)
    monkeypatch.setattr(efficacy_runtime, "_current_profile", AsyncMock(return_value=profile))
    monkeypatch.setattr(
        efficacy_runtime,
        "runtime_context_if_running",
        lambda: LiaRuntimeContext.for_conversation(
            user_id=owner, conversation_id=owner, psyche_enabled=True
        ),
    )
    monkeypatch.setattr(
        plan_pattern_learner, "get_learned_patterns_prompt", AsyncMock(return_value="")
    )
    monkeypatch.setattr(advisor, "get_active_degradations", AsyncMock(return_value=[]))
    qi = QueryIntelligence(
        original_query="Dans quel dossier ?",
        english_query="Which folder?",
        immediate_intent="search",
        immediate_confidence=1,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="explicit",
        domains=["file"],
        efficacy_context=turn,
    )
    catalogue = FilteredCatalogue(
        tools=[], tool_count=0, token_estimate=0, domains_included=["file"], categories_included=[]
    )
    prompt = await SmartPlannerService()._build_prompt(
        qi, catalogue, {"metadata": {"run_id": turn.run_id}}, clarification_response=answer
    )
    assert bool(prompt.strip())
    assert ("<WorkAdjustment>" in prompt) == expected_adjustment
