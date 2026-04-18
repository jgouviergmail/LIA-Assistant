"""Tests for ContextResolutionService: current_item maintenance after resolution.

Enforces the invariant: current_item always reflects the last item manipulated,
searched, or evoked by the user. Reference resolution is an evocation, so
the resolver must keep current_item consistent.

Regression context: a bug was observed where current_item held a stale item
from a previous HITL create/update, and a subsequent "supprime ce rdv" resolved
to that stale current_item instead of the item the user had just evoked via
ordinal reference ("c'était quoi le premier rdv renvoyé ?"). The fix is to
update current_item as a side effect of successful reference resolution.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context import (
    ContextTypeDefinition,
    ContextTypeRegistry,
    ToolContextManager,
)
from src.domains.agents.services.context_resolution_service import (
    ContextResolutionService,
)
from src.domains.agents.services.query_analyzer_service import ContextReferenceOutput


@pytest.fixture(autouse=True)
def _register_event_domain() -> Iterator[None]:
    """Register the 'events' domain used by these tests."""
    if "events" not in ContextTypeRegistry._registry:
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain="events",
                agent_name="event_agent",
                context_type="events",
                primary_id_field="id",
                display_name_field="summary",
                reference_fields=["summary"],
            )
        )
    yield


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def user_id() -> str:
    return str(uuid4())


@pytest.fixture
def session_id() -> str:
    return "thread-1"


@pytest.fixture
def runnable_config(user_id: str, session_id: str) -> dict[str, Any]:
    return {
        "configurable": {"user_id": user_id, "thread_id": session_id},
        "metadata": {},
    }


@pytest.fixture
def service() -> ContextResolutionService:
    return ContextResolutionService()


@pytest.fixture
def manager() -> ToolContextManager:
    return ToolContextManager()


def _patch_tcm_store(store: InMemoryStore) -> Any:
    """Patch get_tool_context_store to return the fixture store."""
    return patch(
        "src.domains.agents.context.store.get_tool_context_store",
        new=AsyncMock(return_value=store),
    )


async def _seed_events_list(
    manager: ToolContextManager,
    store: InMemoryStore,
    user_id: str,
    session_id: str,
    items: list[dict[str, Any]],
) -> None:
    """Seed the events LIST for the tests."""
    await manager.save_list(
        user_id=user_id,
        session_id=session_id,
        domain="events",
        items=items,
        metadata={
            "turn_id": 0,
            "total_count": len(items),
            "timestamp": "2026-04-18T09:00:00Z",
        },
        store=store,
    )


def _make_state(current_turn_id: int = 5) -> dict[str, Any]:
    """Build a minimal state dict for the resolver."""
    return {
        "current_turn_id": current_turn_id,
        "last_list_turn_id": 0,
        "last_list_domain": "events",
        "agent_results": {},
    }


@pytest.mark.asyncio
async def test_ordinal_resolution_sets_current_to_resolved_item(
    service: ContextResolutionService,
    manager: ToolContextManager,
    store: InMemoryStore,
    runnable_config: dict[str, Any],
    user_id: str,
    session_id: str,
) -> None:
    """After 'le premier rdv', current_item must be that resolved item.

    Regression for the bug: user says 'c'était quoi le premier rdv renvoyé ?',
    resolver returns item[0] in ResolvedContext — but current_item must also
    be updated so a subsequent 'ce rdv' targets the right item.
    """
    # Pre-populate LIST with 2 events, and set a STALE current to simulate the bug
    await _seed_events_list(
        manager,
        store,
        user_id,
        session_id,
        items=[
            {"id": "evt_1", "summary": "test 1"},
            {"id": "evt_2", "summary": "test 2"},
        ],
    )
    # Simulate a previous HITL create that left "test 3" as current
    await manager.set_current_item(
        user_id=user_id,
        session_id=session_id,
        domain="events",
        item={"id": "evt_3", "summary": "test 3", "index": 1},
        set_by="auto",
        turn_id=1,
        store=store,
    )

    context_ref = ContextReferenceOutput(
        has_reference=True,
        reference_type="ordinal",
        ordinal_positions=[1],
        reference_domain="event",
    )

    with _patch_tcm_store(store):
        result, turn_type = await service.resolve_context(
            query="c'était quoi le premier rdv renvoyé ?",
            state=_make_state(current_turn_id=5),
            config=runnable_config,
            run_id="run-1",
            context_reference=context_ref,
        )

    assert result.items and result.items[0]["id"] == "evt_1"

    # CRITICAL: current_item is now the resolved item (test 1), not the stale test 3
    current = await manager.get_current_item(
        user_id=user_id, session_id=session_id, domain="events", store=store
    )
    assert current is not None
    assert current["id"] == "evt_1"
    assert current["summary"] == "test 1"


@pytest.mark.asyncio
async def test_ordinal_multi_resolution_clears_current(
    service: ContextResolutionService,
    manager: ToolContextManager,
    store: InMemoryStore,
    runnable_config: dict[str, Any],
    user_id: str,
    session_id: str,
) -> None:
    """Multi-ordinal 'le 1er et le 3e' must clear current (ambiguous focus)."""
    await _seed_events_list(
        manager,
        store,
        user_id,
        session_id,
        items=[
            {"id": "evt_1", "summary": "test 1"},
            {"id": "evt_2", "summary": "test 2"},
            {"id": "evt_3", "summary": "test 3"},
        ],
    )
    await manager.set_current_item(
        user_id=user_id,
        session_id=session_id,
        domain="events",
        item={"id": "evt_stale", "summary": "stale", "index": 1},
        set_by="auto",
        turn_id=1,
        store=store,
    )

    context_ref = ContextReferenceOutput(
        has_reference=True,
        reference_type="ordinal",
        ordinal_positions=[1, 3],
        reference_domain="event",
    )

    with _patch_tcm_store(store):
        result, _ = await service.resolve_context(
            query="le 1er et le 3e",
            state=_make_state(),
            config=runnable_config,
            run_id="run-1",
            context_reference=context_ref,
        )

    assert len(result.items) == 2

    # current cleared (no single focus)
    current = await manager.get_current_item(
        user_id=user_id, session_id=session_id, domain="events", store=store
    )
    assert current is None


@pytest.mark.asyncio
async def test_demonstrative_resolution_refreshes_current(
    service: ContextResolutionService,
    manager: ToolContextManager,
    store: InMemoryStore,
    runnable_config: dict[str, Any],
    user_id: str,
    session_id: str,
) -> None:
    """'ce rdv' with existing current: resolution is idempotent on item but
    refreshes turn_id/set_at (observability)."""
    await _seed_events_list(
        manager,
        store,
        user_id,
        session_id,
        items=[{"id": "evt_1", "summary": "test 1"}],
    )
    await manager.set_current_item(
        user_id=user_id,
        session_id=session_id,
        domain="events",
        item={"id": "evt_1", "summary": "test 1", "index": 1},
        set_by="auto",
        turn_id=1,
        store=store,
    )

    context_ref = ContextReferenceOutput(
        has_reference=True,
        reference_type="demonstrative",
        ordinal_positions=[],
        reference_domain="event",
    )

    with _patch_tcm_store(store):
        result, _ = await service.resolve_context(
            query="ce rdv",
            state=_make_state(current_turn_id=7),
            config=runnable_config,
            run_id="run-1",
            context_reference=context_ref,
        )

    assert result.items and result.items[0]["id"] == "evt_1"
    current = await manager.get_current_item(
        user_id=user_id, session_id=session_id, domain="events", store=store
    )
    assert current is not None
    assert current["id"] == "evt_1"


@pytest.mark.asyncio
async def test_demonstrative_fallback_sets_current_to_first_list_item(
    service: ContextResolutionService,
    manager: ToolContextManager,
    store: InMemoryStore,
    runnable_config: dict[str, Any],
    user_id: str,
    session_id: str,
) -> None:
    """'ce rdv' with no current → resolver falls back to list[0];
    current must be set to that fallback item (cohérence de la règle d'or)."""
    await _seed_events_list(
        manager,
        store,
        user_id,
        session_id,
        items=[
            {"id": "evt_1", "summary": "test 1"},
            {"id": "evt_2", "summary": "test 2"},
        ],
    )
    # Ensure no current (save_list N>1 clears it by default, but explicit)
    await manager.clear_current_item(
        user_id=user_id, session_id=session_id, domain="events", store=store
    )

    context_ref = ContextReferenceOutput(
        has_reference=True,
        reference_type="demonstrative",
        ordinal_positions=[],
        reference_domain="event",
    )

    with _patch_tcm_store(store):
        result, _ = await service.resolve_context(
            query="ce rdv",
            state=_make_state(),
            config=runnable_config,
            run_id="run-1",
            context_reference=context_ref,
        )

    assert result.items and result.items[0]["id"] == "evt_1"
    current = await manager.get_current_item(
        user_id=user_id, session_id=session_id, domain="events", store=store
    )
    assert current is not None
    assert current["id"] == "evt_1"


@pytest.mark.asyncio
async def test_resolution_failure_preserves_existing_current(
    service: ContextResolutionService,
    manager: ToolContextManager,
    store: InMemoryStore,
    runnable_config: dict[str, Any],
    user_id: str,
    session_id: str,
) -> None:
    """Failed resolution (empty list, out-of-bounds) must NOT touch current."""
    # No list seeded — resolver can't find items
    await manager.set_current_item(
        user_id=user_id,
        session_id=session_id,
        domain="events",
        item={"id": "evt_keep", "summary": "keep me", "index": 1},
        set_by="auto",
        turn_id=1,
        store=store,
    )

    context_ref = ContextReferenceOutput(
        has_reference=True,
        reference_type="ordinal",
        ordinal_positions=[99],  # out of bounds anyway
        reference_domain="event",
    )

    with _patch_tcm_store(store):
        result, _ = await service.resolve_context(
            query="le 99ème",
            state=_make_state(),
            config=runnable_config,
            run_id="run-1",
            context_reference=context_ref,
        )

    assert result.items == []

    # current untouched
    current = await manager.get_current_item(
        user_id=user_id, session_id=session_id, domain="events", store=store
    )
    assert current is not None
    assert current["id"] == "evt_keep"


@pytest.mark.asyncio
async def test_no_reference_does_not_touch_current(
    service: ContextResolutionService,
    manager: ToolContextManager,
    store: InMemoryStore,
    runnable_config: dict[str, Any],
    user_id: str,
    session_id: str,
) -> None:
    """has_reference=False → resolver is a no-op, current is preserved."""
    await manager.set_current_item(
        user_id=user_id,
        session_id=session_id,
        domain="events",
        item={"id": "evt_keep", "summary": "keep me", "index": 1},
        set_by="auto",
        turn_id=1,
        store=store,
    )

    context_ref = ContextReferenceOutput(
        has_reference=False,
        reference_type="none",
        ordinal_positions=[],
        reference_domain="",
    )

    with _patch_tcm_store(store):
        result, _ = await service.resolve_context(
            query="bonjour",
            state=_make_state(),
            config=runnable_config,
            run_id="run-1",
            context_reference=context_ref,
        )

    assert result.items == []

    current = await manager.get_current_item(
        user_id=user_id, session_id=session_id, domain="events", store=store
    )
    assert current is not None
    assert current["id"] == "evt_keep"
