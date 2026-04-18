"""Tests for ContextSaveMode.CURRENT auto_save routing.

Validates the two-keys design (2026-04):
- CURRENT with 1 item → set_current_item, LIST untouched
- CURRENT with >1 items → clear current_item, LIST untouched
- CURRENT with 0 items → no-op
"""

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context import (
    ContextSaveMode,
    ContextTypeDefinition,
    ContextTypeRegistry,
    ToolContextManager,
)


@pytest.fixture(autouse=True)
def _register_test_domain():
    """Register a test domain for auto_save routing tests."""
    if "contacts_current_test" not in ContextTypeRegistry._registry:
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain="contacts_current_test",
                agent_name="test_agent",
                context_type="contacts_current_test",
                primary_id_field="resource_name",
                display_name_field="name",
                reference_fields=["name"],
            )
        )
    yield


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def manager():
    return ToolContextManager()


@pytest.fixture
def config_ok():
    return {
        "configurable": {"user_id": "user-1", "thread_id": "thread-1"},
        "metadata": {"turn_id": 42},
    }


@pytest.mark.asyncio
async def test_current_mode_single_item_sets_current_leaves_list(manager, store, config_ok):
    """CURRENT mode with 1 item: current is set, list remains empty."""
    # Pre-populate list with items (to verify they're preserved)
    await manager.save_list(
        user_id="user-1",
        session_id="thread-1",
        domain="contacts_current_test",
        items=[
            {"resource_name": "people/a", "name": "Alice"},
            {"resource_name": "people/b", "name": "Bob"},
        ],
        metadata={"turn_id": 10, "total_count": 2, "timestamp": "2026-04-18T12:00:00Z"},
        store=store,
    )

    # CURRENT mode with 1 item
    result_data = {
        "success": True,
        "contacts_current_tests": [{"resource_name": "people/c", "name": "Charlie"}],
        "tool_name": "get_contact_details",
    }

    await manager.auto_save(
        context_type="contacts_current_test",
        result_data=result_data,
        config=config_ok,
        store=store,
        explicit_mode=ContextSaveMode.CURRENT,
    )

    # LIST is preserved (still Alice + Bob)
    context_list = await manager.get_list(
        user_id="user-1", session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    assert len(context_list.items) == 2
    names = [item["name"] for item in context_list.items]
    assert names == ["Alice", "Bob"]

    # CURRENT is Charlie
    current = await manager.get_current_item(
        user_id="user-1", session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert current is not None
    assert current["resource_name"] == "people/c"
    assert current["name"] == "Charlie"


@pytest.mark.asyncio
async def test_current_mode_multiple_items_clears_current_leaves_list(manager, store, config_ok):
    """CURRENT mode with >1 items: current cleared, list preserved."""
    # Pre-populate list AND current
    await manager.save_list(
        user_id="user-1",
        session_id="thread-1",
        domain="contacts_current_test",
        items=[
            {"resource_name": "people/a", "name": "Alice"},
            {"resource_name": "people/b", "name": "Bob"},
        ],
        metadata={"turn_id": 10, "total_count": 2, "timestamp": "2026-04-18T12:00:00Z"},
        store=store,
    )
    await manager.set_current_item(
        user_id="user-1",
        session_id="thread-1",
        domain="contacts_current_test",
        item={"resource_name": "people/a", "name": "Alice", "index": 1},
        set_by="auto",
        turn_id=10,
        store=store,
    )

    # CURRENT mode with 2 items
    result_data = {
        "success": True,
        "contacts_current_tests": [
            {"resource_name": "people/c", "name": "Charlie"},
            {"resource_name": "people/d", "name": "Daisy"},
        ],
        "tool_name": "get_contact_details",
    }

    await manager.auto_save(
        context_type="contacts_current_test",
        result_data=result_data,
        config=config_ok,
        store=store,
        explicit_mode=ContextSaveMode.CURRENT,
    )

    # LIST is preserved (still Alice + Bob)
    context_list = await manager.get_list(
        user_id="user-1", session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    names = [item["name"] for item in context_list.items]
    assert names == ["Alice", "Bob"]

    # CURRENT is cleared
    current = await manager.get_current_item(
        user_id="user-1", session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert current is None


@pytest.mark.asyncio
async def test_list_mode_overwrites_list(manager, store, config_ok):
    """LIST mode overwrites the list and auto-manages current."""
    # Seed with existing list
    await manager.save_list(
        user_id="user-1",
        session_id="thread-1",
        domain="contacts_current_test",
        items=[{"resource_name": "people/a", "name": "Alice"}],
        metadata={"turn_id": 10, "total_count": 1, "timestamp": "2026-04-18T12:00:00Z"},
        store=store,
    )

    # LIST mode with 2 new items
    result_data = {
        "success": True,
        "contacts_current_tests": [
            {"resource_name": "people/c", "name": "Charlie"},
            {"resource_name": "people/d", "name": "Daisy"},
        ],
        "tool_name": "search_contacts",
    }

    await manager.auto_save(
        context_type="contacts_current_test",
        result_data=result_data,
        config=config_ok,
        store=store,
        explicit_mode=ContextSaveMode.LIST,
    )

    # LIST is overwritten
    context_list = await manager.get_list(
        user_id="user-1", session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    names = [item["name"] for item in context_list.items]
    assert names == ["Charlie", "Daisy"]

    # CURRENT is cleared (N>1)
    current = await manager.get_current_item(
        user_id="user-1", session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert current is None


@pytest.mark.asyncio
async def test_none_mode_noop(manager, store, config_ok):
    """NONE mode does not touch list or current."""
    await manager.save_list(
        user_id="user-1",
        session_id="thread-1",
        domain="contacts_current_test",
        items=[{"resource_name": "people/a", "name": "Alice"}],
        metadata={"turn_id": 10, "total_count": 1, "timestamp": "2026-04-18T12:00:00Z"},
        store=store,
    )

    result_data = {
        "success": True,
        "contacts_current_tests": [{"resource_name": "people/c", "name": "Charlie"}],
        "tool_name": "internal_tool",
    }

    await manager.auto_save(
        context_type="contacts_current_test",
        result_data=result_data,
        config=config_ok,
        store=store,
        explicit_mode=ContextSaveMode.NONE,
    )

    context_list = await manager.get_list(
        user_id="user-1", session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    assert len(context_list.items) == 1
    assert context_list.items[0]["name"] == "Alice"
