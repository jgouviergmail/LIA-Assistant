"""Wiring of the peer-routing fix inside the analyzer (defect 2026-07-30).

The unit behaviour of the two layers lives in
``tests/unit/domains/agents/services/analysis/test_peer_directory.py``. What is
proved here is that they are actually CONNECTED to the turn:

- the directory is loaded once and reaches the prompt builder;
- the deterministic correction runs on the analyzer's verdict, over the texts
  that can carry the name (original query, English pivot, resolved references);
- the corrected domain list is what the rest of the turn consumes — the
  expansion step, and therefore the tool catalogue.

Regression target: request 303d7ce3, "Jerome G est-il disponible demain à
10h ?" analyzed ``event`` + ``contact``, planned over the ASKING user's own
calendar, invalidated on missing scopes.
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

QUERY = "Jerome G est-il disponible demain à 10h ?"
PEER = "Jérôme G"


def _make_service(memory_resolution: MemoryResolution | None = None) -> QueryAnalyzerService:
    """Build a service whose every collaborator is inert but the analysis."""
    resolution = memory_resolution or MemoryResolution(facts=None, resolved=None, references=[])
    memory_resolver = MagicMock()
    memory_resolver.retrieve_and_resolve = AsyncMock(return_value=resolution)
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


def _misrouted_result() -> QueryAnalysisResult:
    """The verbatim analyzer verdict of the failing production turn."""
    return QueryAnalysisResult(
        intent="action",
        primary_domain="event",
        secondary_domains=["contact"],
        confidence=0.95,
        english_query="Is Jerome G available tomorrow at 10am?",
        resolved_references=[],
        reasoning="User asks about another person's availability",
    )


async def _run(
    service: QueryAnalyzerService,
    peers: list[str],
    analysis_result: QueryAnalysisResult | None = None,
    query: str = QUERY,
) -> tuple[MagicMock, MagicMock]:
    """Run analyze_full with a stubbed directory; return (analyze, expand) mocks."""
    with (
        patch(
            "src.domains.agents.services.query_analyzer_service.load_connected_peer_names",
            AsyncMock(return_value=peers),
        ),
        patch.object(
            service,
            "analyze",
            AsyncMock(return_value=analysis_result or _misrouted_result()),
        ) as mock_analyze,
        patch.object(
            service,
            "_expand_domains_for_semantic_types",
            AsyncMock(side_effect=lambda **kw: list(kw["domains"])),
        ) as mock_expand,
    ):
        await service.analyze_full(
            query=query,
            messages=[HumanMessage(content=query)],
            state={"user_language": "fr"},
            config={"configurable": {"langgraph_user_id": "u-1"}},
            original_query=query,
        )
    return mock_analyze, mock_expand


@pytest.mark.asyncio
async def test_misrouted_turn_gains_the_peer_domain():
    """The production defect, end to end through the analyzer."""
    _, mock_expand = await _run(_make_service(), [PEER])

    assert mock_expand.await_args.kwargs["domains"] == ["event", "contact", "peer"]


@pytest.mark.asyncio
async def test_directory_reaches_the_prompt_builder():
    """The awareness layer is wired: the LLM call receives the connections."""
    mock_analyze, _ = await _run(_make_service(), [PEER])

    assert mock_analyze.await_args.kwargs["connected_peers"] == [PEER]


@pytest.mark.asyncio
async def test_user_without_connections_is_untouched():
    """No peers, no correction — and no behaviour change for everyone else."""
    _, mock_expand = await _run(_make_service(), [])

    assert mock_expand.await_args.kwargs["domains"] == ["event", "contact"]


@pytest.mark.asyncio
async def test_correctly_routed_turn_is_left_alone():
    """The 13:23 run already answered `peer` — it must not be touched twice."""
    already_right = QueryAnalysisResult(
        intent="action",
        primary_domain="peer",
        secondary_domains=[],
        confidence=0.95,
        english_query="Is Jerome G available tomorrow?",
        resolved_references=[],
        reasoning="peer availability",
    )
    _, mock_expand = await _run(_make_service(), [PEER], already_right)

    assert mock_expand.await_args.kwargs["domains"] == ["peer"]


@pytest.mark.asyncio
async def test_name_carried_only_by_a_resolved_reference_is_seen():
    """ "mon frère est-il dispo ?" — the name exists only in the mapping value."""
    query = "mon frère est-il dispo demain ?"
    resolution = MemoryResolution(
        facts=None,
        resolved=ResolvedReferences(
            original_query=query,
            enriched_query=query.replace("mon frère", PEER),
            mappings={"mon frère": PEER},
        ),
        references=["mon frère"],
    )
    result = QueryAnalysisResult(
        intent="action",
        primary_domain="event",
        secondary_domains=[],
        confidence=0.9,
        english_query="is my brother available tomorrow?",
        resolved_references=[],
        reasoning="availability",
    )
    _, mock_expand = await _run(_make_service(resolution), [PEER], result, query=query)

    assert mock_expand.await_args.kwargs["domains"] == ["event", "peer"]


@pytest.mark.asyncio
async def test_name_carried_only_by_the_english_pivot_is_seen():
    """The user's own wording may hide the name the pivot spells out."""
    result = QueryAnalysisResult(
        intent="action",
        primary_domain="event",
        secondary_domains=[],
        confidence=0.9,
        english_query="Is Jerome G free tomorrow?",
        resolved_references=[],
        reasoning="availability",
    )
    _, mock_expand = await _run(_make_service(), [PEER], result, query="il est dispo demain ?")

    assert mock_expand.await_args.kwargs["domains"] == ["event", "peer"]


@pytest.mark.asyncio
async def test_a_question_about_a_peers_TASKS_is_corrected_too():
    """Shared tasks are the other half of spec A1 — same defect, same guard.

    Only the availability phrasing was ever observed failing, so nothing but
    this test stops the tasks half from being quietly dropped from the gate.
    """
    tasks_turn = QueryAnalysisResult(
        intent="action",
        primary_domain="task",
        secondary_domains=[],
        confidence=0.9,
        english_query="What are Jerome G's tasks?",
        resolved_references=[],
        reasoning="user asks for tasks",
    )
    _, mock_expand = await _run(
        _make_service(), [PEER], tasks_turn, query="quelles sont les tâches de Jerome G ?"
    )

    assert mock_expand.await_args.kwargs["domains"] == ["task", "peer"]


@pytest.mark.asyncio
async def test_directory_is_loaded_once_per_turn():
    """One indexed query per turn — never one per prompt rebuild."""
    service = _make_service()
    with (
        patch(
            "src.domains.agents.services.query_analyzer_service.load_connected_peer_names",
            AsyncMock(return_value=[PEER]),
        ) as mock_load,
        patch.object(service, "analyze", AsyncMock(return_value=_misrouted_result())),
        patch.object(
            service,
            "_expand_domains_for_semantic_types",
            AsyncMock(side_effect=lambda **kw: list(kw["domains"])),
        ),
    ):
        await service.analyze_full(
            query=QUERY,
            messages=[HumanMessage(content=QUERY)],
            state={"user_language": "fr"},
            config={"configurable": {"langgraph_user_id": "u-1"}},
            original_query=QUERY,
        )

    mock_load.assert_awaited_once_with("u-1")
