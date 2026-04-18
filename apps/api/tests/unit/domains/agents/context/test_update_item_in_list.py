"""Tests for ToolContextManager.update_item_in_list().

Ensures the two-keys TCM keeps the list consistent after HITL update:
a successful update must propagate the new payload into the list entry
while preserving the 1-based index and the other items.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context import (
    ContextTypeDefinition,
    ContextTypeRegistry,
    ToolContextManager,
)


@pytest.fixture(autouse=True)
def _register_events_domain() -> Iterator[None]:
    if "events_update_test" not in ContextTypeRegistry._registry:
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain="events_update_test",
                agent_name="event_agent",
                context_type="events_update_test",
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
def manager() -> ToolContextManager:
    return ToolContextManager()


async def _seed(
    manager: ToolContextManager,
    store: InMemoryStore,
    items: list[dict[str, Any]],
) -> None:
    await manager.save_list(
        user_id="u1",
        session_id="s1",
        domain="events_update_test",
        items=items,
        metadata={"turn_id": 0, "total_count": len(items), "timestamp": "2026-04-18T10:00:00Z"},
        store=store,
    )


@pytest.mark.asyncio
async def test_update_item_in_list_replaces_in_place_preserves_index(
    manager: ToolContextManager, store: InMemoryStore
) -> None:
    """Updating an existing item replaces it in place and preserves index."""
    await _seed(
        manager,
        store,
        items=[
            {"id": "a", "summary": "A", "end": "10:00"},
            {"id": "b", "summary": "B", "end": "11:00"},
            {"id": "c", "summary": "C", "end": "12:00"},
        ],
    )

    ok = await manager.update_item_in_list(
        user_id="u1",
        session_id="s1",
        domain="events_update_test",
        item_id="b",
        updated_item={"id": "b", "summary": "B", "end": "11:30"},
        store=store,
    )
    assert ok is True

    context = await manager.get_list(
        user_id="u1", session_id="s1", domain="events_update_test", store=store
    )
    assert context is not None
    assert [it["id"] for it in context.items] == ["a", "b", "c"]
    assert [it["index"] for it in context.items] == [1, 2, 3]
    assert context.items[1]["end"] == "11:30"
    assert context.items[0]["end"] == "10:00"
    assert context.items[2]["end"] == "12:00"


@pytest.mark.asyncio
async def test_update_item_in_list_no_op_when_item_absent(
    manager: ToolContextManager, store: InMemoryStore
) -> None:
    """If item_id is not in the list, return False and leave list unchanged."""
    await _seed(
        manager,
        store,
        items=[{"id": "a", "summary": "A"}, {"id": "b", "summary": "B"}],
    )

    ok = await manager.update_item_in_list(
        user_id="u1",
        session_id="s1",
        domain="events_update_test",
        item_id="ghost",
        updated_item={"id": "ghost", "summary": "Ghost"},
        store=store,
    )
    assert ok is False

    context = await manager.get_list(
        user_id="u1", session_id="s1", domain="events_update_test", store=store
    )
    assert [it["id"] for it in context.items] == ["a", "b"]


@pytest.mark.asyncio
async def test_update_item_in_list_preserves_current_item(
    manager: ToolContextManager, store: InMemoryStore
) -> None:
    """update_item_in_list touches only LIST, never CURRENT."""
    await _seed(
        manager,
        store,
        items=[{"id": "a", "summary": "A"}, {"id": "b", "summary": "B"}],
    )
    await manager.set_current_item(
        user_id="u1",
        session_id="s1",
        domain="events_update_test",
        item={"id": "a", "summary": "A", "index": 1},
        set_by="auto",
        turn_id=1,
        store=store,
    )

    await manager.update_item_in_list(
        user_id="u1",
        session_id="s1",
        domain="events_update_test",
        item_id="b",
        updated_item={"id": "b", "summary": "B-new"},
        store=store,
    )

    current = await manager.get_current_item(
        user_id="u1", session_id="s1", domain="events_update_test", store=store
    )
    # current still points to "a", untouched
    assert current is not None
    assert current["id"] == "a"


@pytest.mark.asyncio
async def test_update_item_in_list_empty_list_returns_false(
    manager: ToolContextManager, store: InMemoryStore
) -> None:
    """No seeded list → returns False without raising."""
    ok = await manager.update_item_in_list(
        user_id="u1",
        session_id="s1",
        domain="events_update_test",
        item_id="x",
        updated_item={"id": "x"},
        store=store,
    )
    assert ok is False
