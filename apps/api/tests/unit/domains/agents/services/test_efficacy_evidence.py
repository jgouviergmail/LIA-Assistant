"""Only attributable terminal proof may become experience."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.agents.analysis.efficacy_context import EfficacyAnalysis, EfficacyTurnContext
from src.domains.agents.analysis.requested_outcomes import GoalRequirement
from src.domains.agents.services.efficacy_evidence import (
    EfficacyCapture,
    observations_from_coverage,
)
from src.domains.agents.services.outcome_evidence import GoalCoverage
from src.domains.psyche.constants import EfficacyDomain
from src.domains.psyche.efficacy_contracts import EfficacyEpoch

pytestmark = pytest.mark.unit


def coverage(status):
    return GoalCoverage(
        requirement=GoalRequirement(domain="event", label="Agenda", source_quote="agenda"),
        status=status,
    )


def context(run="turn-1"):
    return EfficacyTurnContext(
        owner_id=uuid4(),
        run_id=run,
        epoch=EfficacyEpoch(state_id=uuid4(), generation=uuid4()),
        analysis=EfficacyAnalysis(domains=(EfficacyDomain.ORGANIZATION,)),
        issued_at=datetime.now(UTC),
    )


def test_fulfilled_canonical_requirement_counts_once_not_per_tool():
    observations = observations_from_coverage(
        (EfficacyDomain.ORGANIZATION,), [coverage("satisfied"), coverage("satisfied")]
    )
    assert len(observations) == 1
    assert observations[0].verdict == "success"


@pytest.mark.parametrize(
    "status,verdict",
    [
        ("failed", "unknown"),
        ("missing", "unknown"),
        ("partial", "partial"),
        ("unknown", "unknown"),
        ("pending_confirmation", "excluded"),
    ],
)
def test_provider_failures_and_absence_are_not_competence_failures(status, verdict):
    assert (
        observations_from_coverage((EfficacyDomain.INFORMATION,), [coverage(status)])[0].verdict
        == verdict
    )


def test_social_receipt_does_not_prove_social_quality():
    assert (
        observations_from_coverage((EfficacyDomain.SOCIAL,), [coverage("satisfied")])[0].verdict
        == "unknown"
    )


def test_mixed_domains_cannot_share_global_objective_reward():
    result = observations_from_coverage(
        (EfficacyDomain.INFORMATION, EfficacyDomain.CREATIVITY), [coverage("satisfied")]
    )
    assert [item.verdict for item in result] == ["unknown", "unknown"]


def test_stale_checkpoint_cannot_attribute_previous_turn():
    capture = EfficacyCapture()
    old = context("old")
    capture.update(
        {"query_intelligence": {"efficacy_context": old.model_dump(mode="json")}}, run_id="new"
    )
    assert capture.envelope(run_id="new") == {}


def test_capture_requires_current_run_and_clears_previous_payload():
    capture = EfficacyCapture()
    turn = context()
    capture.update(
        {
            "query_intelligence": {
                "efficacy_context": turn.model_dump(mode="json"),
                "requested_outcomes": [],
                "original_query": "",
                "domains": [],
            }
        },
        run_id="turn-1",
    )
    envelope = capture.envelope(run_id="turn-1")
    assert envelope["psyche_efficacy"]["context"]["run_id"] == "turn-1"
    assert envelope["psyche_efficacy"]["observations"][0]["verdict"] == "unknown"
    assert capture.envelope(run_id="turn-2") == {}


def test_cognitive_context_survives_checkpoint_without_private_scores():
    import json

    from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
    from src.domains.agents.analysis.query_intelligence_helpers import (
        reconstruct_query_intelligence,
    )

    turn = context()
    qi = QueryIntelligence(
        original_query="Bonjour",
        english_query="Hello",
        immediate_intent="chat",
        immediate_confidence=1.0,
        user_goal=UserGoal.UNDERSTAND,
        goal_reasoning="",
        efficacy_analysis=turn.analysis,
        efficacy_context=turn,
    )
    serialized = json.loads(json.dumps(qi.to_serializable_dict()))
    restored = reconstruct_query_intelligence(serialized)
    assert restored.efficacy_context == turn
    assert restored.efficacy_analysis.domains == (EfficacyDomain.ORGANIZATION,)
    assert "result_score" not in json.dumps(serialized["efficacy_context"])


def test_policy_context_expires_at_boundary_and_rejects_clock_reversal():
    from datetime import timedelta

    turn = context()
    assert turn.valid_at(turn.issued_at)
    assert not turn.valid_at(turn.issued_at - timedelta(microseconds=1))
    assert not turn.valid_at(turn.issued_at + timedelta(hours=24))


def test_bad_optional_attribution_does_not_destroy_action_routing():
    from src.domains.agents.services.analysis.query_analysis_schemas import QueryAnalysisOutput

    output = QueryAnalysisOutput(
        intent="action",
        english_query="Find events",
        reasoning="Explicit request",
        efficacy_analysis={"domains": ["hallucinated_domain"]},
    )
    assert output.intent == "action"
    assert output.efficacy_analysis.domains == ()


def test_collection_off_does_not_archive_proof_even_when_context_allows_influence():
    turn = context().model_copy(update={"collection_enabled": False})
    capture = EfficacyCapture()
    capture.update(
        {"query_intelligence": {"efficacy_context": turn.model_dump(mode="json")}},
        run_id=turn.run_id,
    )
    assert capture.envelope(run_id=turn.run_id) == {}


def test_analysis_attaches_to_original_epoch_never_captures_a_post_purge_state():
    from src.domains.agents.services.efficacy_runtime import attach_efficacy_analysis

    start = context()
    updated = attach_efficacy_analysis(start, EfficacyAnalysis(domains=("information",)))
    assert updated.epoch == start.epoch
    assert updated.issued_at == start.issued_at
    assert updated.analysis.domains == ("information",)
    assert attach_efficacy_analysis(None, EfficacyAnalysis(domains=("information",))) is None


def test_introspection_cannot_substitute_for_a_verification_source() -> None:
    from src.core.context import request_tool_manifests_ctx
    from src.domains.agents.context.catalogue_manifests import (
        list_active_domains_catalogue_manifest,
    )
    from src.domains.agents.python_sandbox.catalogue_manifests import (
        run_python_catalogue_manifest,
    )
    from src.domains.agents.services.efficacy_runtime import has_available_verifier
    from src.domains.agents.weather.catalogue_manifests import (
        get_current_weather_catalogue_manifest,
    )

    # Real contracts make an empty registry incapable of satisfying refusals.
    token = request_tool_manifests_ctx.set(
        [
            list_active_domains_catalogue_manifest,
            get_current_weather_catalogue_manifest,
            run_python_catalogue_manifest,
        ]
    )
    try:
        assert has_available_verifier(["get_current_weather_tool"], "pipeline", ["weather"])
        assert not has_available_verifier(["get_current_weather_tool"], "pipeline", ["event"])
        assert not has_available_verifier(["list_active_domains"], "pipeline", ["context"])
        assert not has_available_verifier(["run_python_tool"], "pipeline", ["python_sandbox"])
        assert has_available_verifier(["run_python_tool"], "react", ["python_sandbox"])
        assert not has_available_verifier([], "react", ["event"])
    finally:
        request_tool_manifests_ctx.reset(token)


async def test_global_off_has_no_database_or_model_work(monkeypatch):
    from src.core.config import settings
    from src.domains.agents.context.runtime_context import LiaRuntimeContext
    from src.domains.agents.services import efficacy_runtime

    turn = context()
    database_attempts = []

    def database():
        database_attempts.append(True)
        raise OSError("A disabled optional subsystem must not enter IO")

    monkeypatch.setattr(settings, "psyche_enabled", False)
    monkeypatch.setattr(efficacy_runtime, "get_db_context", database)
    monkeypatch.setattr(
        efficacy_runtime,
        "runtime_context_if_running",
        lambda: LiaRuntimeContext.for_conversation(
            user_id=turn.owner_id, conversation_id=turn.owner_id, psyche_enabled=True
        ),
    )
    assert (
        await efficacy_runtime.capture_efficacy_context(
            turn.analysis, {"metadata": {"run_id": turn.run_id}}
        )
        is None
    )
    assert await efficacy_runtime.build_efficacy_block(turn, run_id=turn.run_id) == ""
    assert not database_attempts
