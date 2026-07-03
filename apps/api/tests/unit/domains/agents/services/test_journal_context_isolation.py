"""Concurrency isolation tests for SmartPlannerService journal context (audit B6/N-47).

SmartPlannerService is a module-level singleton. Storing the per-request
``journal_context`` on ``self`` and reading it back through ``getattr()`` in
``_build_prompt()`` leaks user A's private journal into user B's planner
prompt whenever two ``plan()`` calls interleave on an await point.

These tests interleave two ``plan()`` calls deterministically (a gate inside
the strategy's ``can_handle`` — scheduling only, the defective write/read
path runs unmodified) and assert strict per-user prompt isolation.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.services.planner.strategies.single_domain import (
    SingleDomainStrategy,
)
from src.domains.agents.services.smart_catalogue_service import (
    CatalogueMetrics,
    FilteredCatalogue,
)
from src.domains.agents.services.smart_planner_service import SmartPlannerService

JOURNAL_A = "JOURNAL-SENTINEL-USER-A"
JOURNAL_B = "JOURNAL-SENTINEL-USER-B"
QUERY_A = "query of user A"
QUERY_B = "query of user B"


def _intelligence(query: str) -> QueryIntelligence:
    """Minimal single-domain read-only intelligence."""
    return QueryIntelligence(
        original_query=query,
        english_query=query,
        immediate_intent="search",
        immediate_confidence=0.9,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="test",
        domains=["contact"],
        primary_domain="contact",
    )


def _catalogue() -> FilteredCatalogue:
    return FilteredCatalogue(
        tools=[{"name": "get_contacts_tool", "description": "test"}],
        tool_count=1,
        token_estimate=50,
        domains_included=["contact"],
        categories_included=[],
    )


class _FakeCatalogueService:
    """Catalogue stub: deterministic catalogue, no registry access."""

    def reset_panic_mode(self) -> None:  # called at plan() entry
        return None

    def filter_for_intelligence(self, *args: Any, **kwargs: Any) -> FilteredCatalogue:
        return _catalogue()

    def get_metrics(self) -> CatalogueMetrics:
        return CatalogueMetrics()


class _GatedSingleDomain(SingleDomainStrategy):
    """Real strategy with a controllable await inside can_handle.

    The gate only reorders task scheduling; plan()/_build_prompt() run
    unmodified, so the singleton write/read race is exercised for real.
    """

    def __init__(self, service: Any, gates: dict[str, asyncio.Event]) -> None:
        super().__init__(service=service)
        self._gates = gates

    async def can_handle(
        self, intelligence: QueryIntelligence, catalogue: FilteredCatalogue | None = None
    ) -> bool:
        gate = self._gates.get(intelligence.original_query)
        if gate is not None:
            await gate.wait()
        return await super().can_handle(intelligence, catalogue)


class _PromptCaptureLLM:
    """Captures the system prompt then aborts (no plan parsing needed)."""

    def __init__(self, captured: dict[str, list[str]]) -> None:
        self._captured = captured

    async def ainvoke(self, messages: list[Any], config: Any = None) -> Any:
        query = str(messages[1].content).removeprefix("Query: ")
        self._captured.setdefault(query, []).append(str(messages[0].content))
        raise RuntimeError("prompt captured - abort before plan parsing")


@pytest.mark.asyncio
async def test_journal_context_isolated_between_interleaved_plans() -> None:
    """User A's planner prompt must contain A's journal, never B's.

    Scenario (the production race): A enters plan() and parks on an await
    before prompt building; B enters plan() on the same singleton and
    completes; A resumes and builds its prompt. Any shared instance state
    makes A's prompt carry B's journal.
    """
    service = SmartPlannerService()
    service.catalogue_service = _FakeCatalogueService()

    gate_a = asyncio.Event()
    strategy = _GatedSingleDomain(service, gates={QUERY_A: gate_a})
    service.strategies = [strategy]

    captured: dict[str, list[str]] = {}
    config: dict[str, Any] = {"configurable": {"user_timezone": "UTC", "user_language": "en"}}

    with (
        patch(
            "src.infrastructure.llm.get_llm",
            return_value=_PromptCaptureLLM(captured),
        ),
        patch(
            "src.domains.agents.services.plan_pattern_learner.get_learned_patterns_prompt",
            new=AsyncMock(return_value=""),
        ),
        patch.object(
            SmartPlannerService, "_build_iot_device_context", new=AsyncMock(return_value="")
        ),
        patch.object(SmartPlannerService, "_build_mcp_reference", return_value=""),
        patch.object(SmartPlannerService, "_build_skills_catalog", return_value=""),
        patch.object(SmartPlannerService, "_build_sub_agents_section", return_value=""),
    ):
        task_a = asyncio.create_task(
            service.plan(_intelligence(QUERY_A), config, journal_context=JOURNAL_A)
        )
        # Let A reach the gate (it has stored its journal by then)
        await asyncio.sleep(0)

        # B runs to completion on the same singleton while A is parked
        await service.plan(_intelligence(QUERY_B), config, journal_context=JOURNAL_B)

        # Release A: it now builds its prompt
        gate_a.set()
        await task_a

    prompts_a = captured.get(QUERY_A, [])
    prompts_b = captured.get(QUERY_B, [])
    assert prompts_a, "user A never reached the LLM"
    assert prompts_b, "user B never reached the LLM"

    for prompt in prompts_a:
        assert JOURNAL_B not in prompt, "user B's journal leaked into user A's planner prompt"
        assert JOURNAL_A in prompt, "user A's own journal is missing from A's planner prompt"
    for prompt in prompts_b:
        assert JOURNAL_A not in prompt, "user A's journal leaked into user B's planner prompt"
        assert JOURNAL_B in prompt


@pytest.mark.asyncio
async def test_plan_does_not_store_journal_context_on_singleton() -> None:
    """plan() must not write per-request journal state on the shared instance."""
    service = SmartPlannerService()
    service.catalogue_service = _FakeCatalogueService()
    service.strategies = [SingleDomainStrategy(service=service)]

    config: dict[str, Any] = {"configurable": {}}

    with (
        patch(
            "src.infrastructure.llm.get_llm",
            return_value=_PromptCaptureLLM({}),
        ),
        patch(
            "src.domains.agents.services.plan_pattern_learner.get_learned_patterns_prompt",
            new=AsyncMock(return_value=""),
        ),
        patch.object(
            SmartPlannerService, "_build_iot_device_context", new=AsyncMock(return_value="")
        ),
        patch.object(SmartPlannerService, "_build_mcp_reference", return_value=""),
        patch.object(SmartPlannerService, "_build_skills_catalog", return_value=""),
        patch.object(SmartPlannerService, "_build_sub_agents_section", return_value=""),
    ):
        await service.plan(_intelligence(QUERY_A), config, journal_context=JOURNAL_A)

    leftover = [attr for attr in vars(service) if "journal" in attr.lower()]
    assert not leftover, f"per-request journal state left on singleton: {leftover}"
