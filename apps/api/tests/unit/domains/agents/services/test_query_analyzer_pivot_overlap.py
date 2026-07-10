"""Latency lot R1 — semantic pivot ∥ memory resolution overlap in analyze_full.

Verifies the exact behavioral contract of the `english_query_task` parameter:
- the memory phase receives the ORIGINAL query (embedding language invariant);
- the awaited pivot result replaces `query` for the analyzer LLM call,
  reproducing the historical caller behaviour (router awaited the pivot first);
- without the task, analyze_full behaves exactly as before (backward compat);
- on a failure before the gather completes, the pivot task is not orphaned.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.core.config.agents import V3RoutingConfig
from src.domains.agents.analysis.query_intelligence import UserGoal
from src.domains.agents.services.analysis.memory_resolver import MemoryResolution
from src.domains.agents.services.query_analyzer_service import (
    QueryAnalysisResult,
    QueryAnalyzerService,
)

ORIGINAL_QUERY = "quel temps fait-il chez mon frère ?"
TRANSLATED_QUERY = "what is the weather at my brother's place?"


def _make_service(memory_resolver: MagicMock) -> QueryAnalyzerService:
    """Build a QueryAnalyzerService with mocked collaborators."""
    context_resolver = MagicMock()
    context_resolver.resolve_context = AsyncMock(return_value=(None, None))
    goal_inferrer = MagicMock()
    goal_inferrer.infer = MagicMock(return_value=(UserGoal.FIND_INFORMATION, "test"))
    routing_decider = MagicMock()
    routing_decider.decide = MagicMock(return_value=("response", 0.9, False))
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


def _analysis_result() -> QueryAnalysisResult:
    """Minimal real QueryAnalysisResult (conversation intent, no domains)."""
    return QueryAnalysisResult(
        intent="conversation",
        primary_domain=None,
        secondary_domains=[],
        confidence=0.9,
        english_query=TRANSLATED_QUERY,
        resolved_references=[],
        reasoning="test",
    )


@pytest.mark.asyncio
async def test_pivot_task_awaited_and_used_as_analyzer_input():
    """The awaited pivot result must feed the analyzer; memory gets the original."""
    memory_resolver = MagicMock()
    memory_resolver.retrieve_and_resolve = AsyncMock(
        return_value=MemoryResolution(facts=None, resolved=None)
    )
    service = _make_service(memory_resolver)

    async def _pivot() -> str:
        await asyncio.sleep(0)
        return TRANSLATED_QUERY

    task = asyncio.create_task(_pivot())

    with patch.object(
        service, "analyze", AsyncMock(return_value=_analysis_result())
    ) as mock_analyze:
        intelligence = await service.analyze_full(
            query=ORIGINAL_QUERY,
            messages=[HumanMessage(content=ORIGINAL_QUERY)],
            state={"user_language": "fr"},
            config={"configurable": {}},
            original_query=ORIGINAL_QUERY,
            english_query_task=task,
        )

    assert task.done()
    # Analyzer LLM receives the TRANSLATED query (historical semantics).
    assert mock_analyze.await_args.kwargs["query"] == TRANSLATED_QUERY
    # Memory phase receives the ORIGINAL query (embedding language invariant).
    memory_resolver.retrieve_and_resolve.assert_awaited_once()
    assert memory_resolver.retrieve_and_resolve.await_args.kwargs["query"] == ORIGINAL_QUERY
    # Debug-panel field keeps the user's original input.
    assert intelligence.original_query == ORIGINAL_QUERY


@pytest.mark.asyncio
async def test_backward_compat_without_pivot_task():
    """Without english_query_task, `query` is used verbatim (pre-R1 behaviour)."""
    memory_resolver = MagicMock()
    memory_resolver.retrieve_and_resolve = AsyncMock(
        return_value=MemoryResolution(facts=None, resolved=None)
    )
    service = _make_service(memory_resolver)

    with patch.object(
        service, "analyze", AsyncMock(return_value=_analysis_result())
    ) as mock_analyze:
        await service.analyze_full(
            query=TRANSLATED_QUERY,
            messages=[HumanMessage(content=ORIGINAL_QUERY)],
            state={"user_language": "fr"},
            config={"configurable": {}},
            original_query=ORIGINAL_QUERY,
        )

    assert mock_analyze.await_args.kwargs["query"] == TRANSLATED_QUERY
    # Memory still prefers original_query over the (English) query param.
    assert memory_resolver.retrieve_and_resolve.await_args.kwargs["query"] == ORIGINAL_QUERY


@pytest.mark.asyncio
async def test_no_pivot_task_downstream_steps_use_analyzer_english():
    """R3 (pivot disabled): downstream EN pattern-matching uses the analyzer's english_query.

    Without a pivot task the analyzer receives the raw query, and the
    post-analyzer steps tuned on English input (context resolution, goal
    inference) receive the english_query the analyzer itself produced.
    """
    memory_resolver = MagicMock()
    memory_resolver.retrieve_and_resolve = AsyncMock(
        return_value=MemoryResolution(facts=None, resolved=None)
    )
    service = _make_service(memory_resolver)

    with patch.object(
        service, "analyze", AsyncMock(return_value=_analysis_result())
    ) as mock_analyze:
        await service.analyze_full(
            query=ORIGINAL_QUERY,
            messages=[HumanMessage(content=ORIGINAL_QUERY)],
            state={"user_language": "fr"},
            config={"configurable": {}},
            original_query=ORIGINAL_QUERY,
        )

    # Analyzer receives the raw (original) query…
    assert mock_analyze.await_args.kwargs["query"] == ORIGINAL_QUERY
    # …and context resolution receives the analyzer's own English output.
    ctx_kwargs = service.context_resolver.resolve_context.await_args.kwargs
    assert ctx_kwargs["query"] == TRANSLATED_QUERY


@pytest.mark.asyncio
async def test_router_pivot_task_gated_by_semantic_pivot_flag(monkeypatch):
    """R3 flag: semantic_pivot_enabled=False → router passes english_query_task=None."""
    from langchain_core.runnables import RunnableConfig

    from src.core.config import settings as app_settings
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.nodes import router_node

    monkeypatch.setattr(app_settings, "semantic_pivot_enabled", False, raising=False)
    monkeypatch.setattr(
        app_settings, "response_context_prefetch_at_router_enabled", False, raising=False
    )

    mock_intelligence = QueryIntelligence(
        original_query=ORIGINAL_QUERY,
        english_query=TRANSLATED_QUERY,
        immediate_intent="chat",
        immediate_confidence=0.9,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="test",
        domains=[],
        route_to="response",
        confidence=0.9,
    )
    mock_service = MagicMock()
    mock_service.analyze_full = AsyncMock(return_value=mock_intelligence)

    with patch(
        "src.domains.agents.services.query_analyzer_service.get_query_analyzer_service",
        return_value=mock_service,
    ):
        await router_node(
            {"messages": [HumanMessage(content=ORIGINAL_QUERY)]},
            RunnableConfig(metadata={"run_id": "test-r3"}),
        )

    assert mock_service.analyze_full.await_args.kwargs["english_query_task"] is None


@pytest.mark.asyncio
async def test_router_pivot_task_created_when_flag_enabled(monkeypatch):
    """R3 flag default: semantic_pivot_enabled=True → router passes a real task."""
    from langchain_core.runnables import RunnableConfig

    from src.core.config import settings as app_settings
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.nodes import router_node

    monkeypatch.setattr(app_settings, "semantic_pivot_enabled", True, raising=False)
    monkeypatch.setattr(
        app_settings, "response_context_prefetch_at_router_enabled", False, raising=False
    )

    mock_intelligence = QueryIntelligence(
        original_query=ORIGINAL_QUERY,
        english_query=TRANSLATED_QUERY,
        immediate_intent="chat",
        immediate_confidence=0.9,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="test",
        domains=[],
        route_to="response",
        confidence=0.9,
    )
    mock_service = MagicMock()
    mock_service.analyze_full = AsyncMock(return_value=mock_intelligence)

    with patch(
        "src.domains.agents.services.query_analyzer_service.get_query_analyzer_service",
        return_value=mock_service,
    ):
        await router_node(
            {"messages": [HumanMessage(content=ORIGINAL_QUERY)]},
            RunnableConfig(metadata={"run_id": "test-r3"}),
        )

    task = mock_service.analyze_full.await_args.kwargs["english_query_task"]
    assert isinstance(task, asyncio.Task)
    # Drain the task (translate_to_english falls back internally, never raises)
    await task


@pytest.mark.asyncio
async def test_pivot_task_not_orphaned_when_memory_phase_fails():
    """A failure racing the pivot must cancel the still-pending task (no orphan)."""
    memory_resolver = MagicMock()
    memory_resolver.retrieve_and_resolve = AsyncMock(side_effect=RuntimeError("boom"))
    service = _make_service(memory_resolver)

    async def _slow_pivot() -> str:
        await asyncio.sleep(30)
        return TRANSLATED_QUERY

    task = asyncio.create_task(_slow_pivot())

    intelligence = await service.analyze_full(
        query=ORIGINAL_QUERY,
        messages=[HumanMessage(content=ORIGINAL_QUERY)],
        state={"user_language": "fr"},
        config={"configurable": {}},
        original_query=ORIGINAL_QUERY,
        english_query_task=task,
    )

    # Fallback intelligence is returned (analyze_full never raises)...
    assert intelligence is not None
    assert intelligence.original_query == ORIGINAL_QUERY
    # ...and the pivot task was cancelled, not left pending.
    await asyncio.sleep(0)
    assert task.cancelled()
