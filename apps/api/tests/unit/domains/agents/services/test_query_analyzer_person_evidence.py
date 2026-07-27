"""Person-reference evidence gate for semantic domain expansion (STEP 3).

The expansion trigger `has_person_reference` must be the union of three
evidence sources, not only the analyzer LLM's typed references (historical
failure: the analyzer intermittently omits the person typing, the contact
domain is never added, and get_route receives a person name as destination):

- E1 `memory_mappings`: the memory resolver resolved identity mappings;
- E2 `memory_extraction`: Phase 1 extracted relational references, preserved
  even when resolution found no memory fact;
- E3 `analyzer_llm`: the analyzer LLM typed a resolved reference as person.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.core.config.agents import V3RoutingConfig
from src.domains.agents.analysis.query_intelligence import UserGoal
from src.domains.agents.services.analysis.memory_resolver import MemoryResolution
from src.domains.agents.services.memory_reference_resolution_service import (
    ResolvedReferences,
)
from src.domains.agents.services.query_analyzer_service import (
    QueryAnalysisResult,
    QueryAnalyzerService,
)

QUERY = "comment aller chez mon frère en voiture demain pour 18h ?"


def _make_service(memory_resolution: MemoryResolution) -> QueryAnalyzerService:
    """Build a QueryAnalyzerService whose memory phase yields `memory_resolution`."""
    memory_resolver = MagicMock()
    memory_resolver.retrieve_and_resolve = AsyncMock(return_value=memory_resolution)
    context_resolver = MagicMock()
    context_resolver.resolve_context = AsyncMock(return_value=(None, None))
    goal_inferrer = MagicMock()
    goal_inferrer.infer = MagicMock(return_value=(UserGoal.TAKE_ACTION, "test"))
    routing_decider = MagicMock()
    routing_decider.decide = MagicMock(return_value=("planner", 0.9, False))
    return QueryAnalyzerService(
        memory_resolver=memory_resolver,
        context_resolver=context_resolver,
        goal_inferrer=goal_inferrer,
        routing_decider=routing_decider,
        thresholds=V3RoutingConfig(
            chat_semantic_threshold=0.3,
            high_semantic_threshold=0.7,
            min_confidence=0.5,
            chat_override_threshold=0.8,
            cross_domain_threshold=0.5,
        ),
    )


def _analysis_result(
    resolved_references: list[dict[str, str]] | None = None,
) -> QueryAnalysisResult:
    """Action analysis on the route domain, with configurable LLM references."""
    return QueryAnalysisResult(
        intent="action",
        primary_domain="route",
        secondary_domains=[],
        confidence=0.9,
        english_query="how to drive to my brother's place tomorrow by 6pm?",
        resolved_references=resolved_references or [],
        reasoning="test",
    )


async def _run_and_capture_gate(
    service: QueryAnalyzerService,
    analysis_result: QueryAnalysisResult,
) -> bool:
    """Run analyze_full and return the has_person_reference passed to expansion."""
    with (
        patch.object(service, "analyze", AsyncMock(return_value=analysis_result)),
        patch.object(
            service,
            "_expand_domains_for_semantic_types",
            AsyncMock(return_value=["route"]),
        ) as mock_expand,
    ):
        await service.analyze_full(
            query=QUERY,
            messages=[HumanMessage(content=QUERY)],
            state={"user_language": "fr"},
            config={"configurable": {}},
            original_query=QUERY,
        )
    mock_expand.assert_awaited_once()
    result = mock_expand.await_args.kwargs["has_person_reference"]
    assert isinstance(result, bool)
    return result


@pytest.mark.asyncio
async def test_e1_memory_mappings_trigger_gate_without_analyzer_refs():
    """Resolved identity mappings alone must open the expansion gate.

    This is the exact shape of the historical failing turn: the resolver
    resolved {"mon frère": "Marc Lemoine"} but the analyzer returned no
    person-typed reference — expansion was skipped and the plan geocoded the
    person name.
    """
    resolution = MemoryResolution(
        facts=None,
        resolved=ResolvedReferences(
            original_query=QUERY,
            enriched_query=QUERY.replace("mon frère", "Marc Lemoine"),
            mappings={"mon frère": "Marc Lemoine"},
        ),
        references=["mon frère"],
    )
    service = _make_service(resolution)

    assert await _run_and_capture_gate(service, _analysis_result()) is True


@pytest.mark.asyncio
async def test_e2_extracted_references_trigger_gate_when_resolution_failed():
    """Phase 1 references must open the gate even with no mappings (no memory fact)."""
    resolution = MemoryResolution(facts=None, resolved=None, references=["mon frère"])
    service = _make_service(resolution)

    assert await _run_and_capture_gate(service, _analysis_result()) is True


@pytest.mark.asyncio
async def test_e3_analyzer_person_reference_still_triggers_gate():
    """Backward compat: the analyzer LLM's person-typed refs alone still work."""
    resolution = MemoryResolution(facts=None, resolved=None)
    service = _make_service(resolution)
    analysis = _analysis_result(
        resolved_references=[{"original": "mon frère", "resolved": "Alexandre", "type": "person"}]
    )

    assert await _run_and_capture_gate(service, analysis) is True


@pytest.mark.asyncio
async def test_no_evidence_keeps_gate_closed():
    """Without any evidence source the gate stays closed (no expansion)."""
    resolution = MemoryResolution(facts=None, resolved=None)
    service = _make_service(resolution)

    assert await _run_and_capture_gate(service, _analysis_result()) is False


@pytest.mark.asyncio
async def test_non_person_analyzer_reference_does_not_open_gate():
    """Analyzer refs of a non-person type must not count as person evidence."""
    resolution = MemoryResolution(facts=None, resolved=None)
    service = _make_service(resolution)
    analysis = _analysis_result(
        resolved_references=[{"original": "là-bas", "resolved": "Lyon", "type": "place"}]
    )

    assert await _run_and_capture_gate(service, analysis) is False


@pytest.mark.asyncio
async def test_person_evidence_maps_to_contact_entity_for_expansion():
    """STEP 3 passes evidence_entities={"Contact"} for person evidence
    (consumed by evidence-driven expansion when the flag is enabled)."""
    resolution = MemoryResolution(facts=None, resolved=None, references=["mon frère"])
    service = _make_service(resolution)

    with (
        patch.object(service, "analyze", AsyncMock(return_value=_analysis_result())),
        patch.object(
            service,
            "_expand_domains_for_semantic_types",
            AsyncMock(return_value=["route"]),
        ) as mock_expand,
    ):
        await service.analyze_full(
            query=QUERY,
            messages=[HumanMessage(content=QUERY)],
            state={"user_language": "fr"},
            config={"configurable": {}},
            original_query=QUERY,
        )

    assert mock_expand.await_args.kwargs["evidence_entities"] == {"Contact"}
