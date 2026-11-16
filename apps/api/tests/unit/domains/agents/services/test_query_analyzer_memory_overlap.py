"""Latency lot 1 — the analyzer does not wait for the memory reference chain.

The analyzer's prompt reads the broad memory facts only. The reference chain
(presence gate, extraction, targeted search, resolution) serves what follows
the analyzer: the resolved names, the person evidence of the domain expansion.
So the chain runs beside the analyzer call and is joined right after it; a
production replay measured the router 0.53 s shorter on average, up to 3.8 s on
a turn whose chain resolved a reference.

The chain is owned: on a failure or a cancellation of the analysis it is
cancelled and awaited, never left spending model calls behind a dead turn.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.core.config.agents import V3RoutingConfig
from src.domains.agents.analysis.query_intelligence import UserGoal
from src.domains.agents.services.analysis.memory_resolver import MemoryResolver
from src.domains.agents.services.memory_reference_resolution_service import (
    ResolvedReferences,
)
from src.domains.agents.services.query_analyzer_service import (
    QueryAnalysisResult,
    QueryAnalyzerService,
)

QUERY = "Quelle est la date d'anniversaire de ma femme ?"
WATCHDOG_SECONDS = 2.0


def _service(resolver: MemoryResolver) -> QueryAnalyzerService:
    """The real analysis service around a real resolver; collaborators mocked."""
    context_resolver = MagicMock()
    context_resolver.resolve_context = AsyncMock(return_value=(None, None))
    goal_inferrer = MagicMock()
    goal_inferrer.infer = MagicMock(return_value=(UserGoal.FIND_INFORMATION, "test"))
    routing_decider = MagicMock()
    routing_decider.decide = MagicMock(return_value=("response", 0.9, False))
    return QueryAnalyzerService(
        memory_resolver=resolver,
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


def _analysis() -> QueryAnalysisResult:
    return QueryAnalysisResult(
        intent="conversation",
        primary_domain=None,
        secondary_domains=[],
        confidence=0.9,
        english_query="What is my wife's birthday?",
        resolved_references=[],
        reasoning="test",
    )


async def _analyze(service: QueryAnalyzerService) -> object:
    return await service.analyze_full(
        query=QUERY,
        messages=[HumanMessage(content=QUERY)],
        state={"user_language": "fr"},
        config={"configurable": {}},
        original_query=QUERY,
    )


@pytest.mark.asyncio
async def test_the_analyzer_starts_while_the_reference_chain_still_runs() -> None:
    """The chain can only finish once the analyzer has started: no deadlock."""
    resolver = MemoryResolver()
    analyzer_started = asyncio.Event()
    facts_seen: list[object] = []

    async def extraction(_query: str, _config: object) -> list[str]:
        await analyzer_started.wait()
        return ["ma femme"]

    async def analyze(**kwargs: object) -> QueryAnalysisResult:
        facts_seen.append(kwargs["memory_facts"])
        analyzer_started.set()
        return _analysis()

    resolved = ResolvedReferences(
        original_query=QUERY,
        enriched_query="Quelle est la date d'anniversaire de Claire ?",
        mappings={"ma femme": "Claire"},
    )
    service = _service(resolver)
    with (
        patch.object(resolver, "_retrieve_memory_facts", AsyncMock(return_value=["wife: Claire"])),
        patch.object(resolver, "_extract_references", side_effect=extraction),
        patch.object(resolver, "_search_memories_targeted", AsyncMock(return_value=["Claire"])),
        patch.object(resolver, "_resolve_memory_references", AsyncMock(return_value=resolved)),
        patch.object(service, "analyze", side_effect=analyze),
    ):
        intelligence = await asyncio.wait_for(_analyze(service), WATCHDOG_SECONDS)

    # The analyzer read the broad facts, as before.
    assert facts_seen == [["wife: Claire"]]
    # The chain's result, joined after the analyzer, still reaches the turn.
    assert [(entry.reference, entry.value) for entry in intelligence.resolved_references] == [
        ("ma femme", "Claire")
    ]


@pytest.mark.asyncio
async def test_a_failed_analysis_cancels_and_awaits_the_chain() -> None:
    """The analyzer fails: the chain still running is cancelled, never orphaned."""
    resolver = MemoryResolver()
    chain_cancelled = asyncio.Event()

    async def extraction(_query: str, _config: object) -> list[str]:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            chain_cancelled.set()
            raise
        return []

    service = _service(resolver)
    with (
        patch.object(resolver, "_retrieve_memory_facts", AsyncMock(return_value=None)),
        patch.object(resolver, "_extract_references", side_effect=extraction),
        patch.object(service, "analyze", AsyncMock(side_effect=RuntimeError("provider down"))),
    ):
        intelligence = await asyncio.wait_for(_analyze(service), WATCHDOG_SECONDS)

    assert intelligence is not None  # analyze_full answers its fallback, never raises
    assert chain_cancelled.is_set()


@pytest.mark.asyncio
async def test_a_cancelled_turn_cancels_and_awaits_the_chain() -> None:
    """The turn is cancelled during the analyzer call: the chain goes with it."""
    resolver = MemoryResolver()
    analyzer_started = asyncio.Event()
    chain_cancelled = asyncio.Event()

    async def extraction(_query: str, _config: object) -> list[str]:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            chain_cancelled.set()
            raise
        return []

    async def analyze(**_kwargs: object) -> QueryAnalysisResult:
        analyzer_started.set()
        await asyncio.Event().wait()
        return _analysis()

    service = _service(resolver)
    with (
        patch.object(resolver, "_retrieve_memory_facts", AsyncMock(return_value=None)),
        patch.object(resolver, "_extract_references", side_effect=extraction),
        patch.object(service, "analyze", side_effect=analyze),
    ):
        turn = asyncio.create_task(_analyze(service))
        await asyncio.wait_for(analyzer_started.wait(), WATCHDOG_SECONDS)
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn

    assert chain_cancelled.is_set()
