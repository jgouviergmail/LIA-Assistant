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
from tests.helpers.runtime_context import DEFAULT_TEST_USER_ID, installed_runtime_context

USER_ID = str(DEFAULT_TEST_USER_ID)


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
    """Thread plumbing only — the acting user now travels on the run context."""
    return {"configurable": {"thread_id": "thread-1"}, "metadata": {"turn_id": 42}}


@pytest.fixture(autouse=True)
def _run_context():
    """auto_save reads the acting user from the run context (ADR-231)."""
    with installed_runtime_context(user_id=DEFAULT_TEST_USER_ID, thread_id="thread-1"):
        yield


@pytest.mark.asyncio
async def test_current_mode_single_item_sets_current_leaves_list(manager, store, config_ok):
    """CURRENT mode with 1 item: current is set, list remains empty."""
    # Pre-populate list with items (to verify they're preserved)
    await manager.save_list(
        user_id=USER_ID,
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
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    assert len(context_list.items) == 2
    names = [item["name"] for item in context_list.items]
    assert names == ["Alice", "Bob"]

    # CURRENT is Charlie
    current = await manager.get_current_item(
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert current is not None
    assert current["resource_name"] == "people/c"
    assert current["name"] == "Charlie"


@pytest.mark.asyncio
async def test_current_mode_multiple_items_clears_current_leaves_list(manager, store, config_ok):
    """CURRENT mode with >1 items: current cleared, list preserved."""
    # Pre-populate list AND current
    await manager.save_list(
        user_id=USER_ID,
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
        user_id=USER_ID,
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
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    names = [item["name"] for item in context_list.items]
    assert names == ["Alice", "Bob"]

    # CURRENT is cleared
    current = await manager.get_current_item(
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert current is None


@pytest.mark.asyncio
async def test_list_mode_overwrites_list(manager, store, config_ok):
    """LIST mode overwrites the list and auto-manages current."""
    # Seed with existing list
    await manager.save_list(
        user_id=USER_ID,
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
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    names = [item["name"] for item in context_list.items]
    assert names == ["Charlie", "Daisy"]

    # CURRENT is cleared (N>1)
    current = await manager.get_current_item(
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert current is None


@pytest.mark.asyncio
async def test_none_mode_noop(manager, store, config_ok):
    """NONE mode does not touch list or current."""
    await manager.save_list(
        user_id=USER_ID,
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
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    assert len(context_list.items) == 1
    assert context_list.items[0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_auto_save_takes_the_acting_user_from_the_runtime_it_was_handed(
    manager, store, config_ok
):
    """A tool run OUTSIDE a graph — a live lookup during an owner call
    (ADR-290) — has no ambient run, only the typed ``ToolRuntime`` it was
    given. The decorator reads the acting user from that runtime and hands it
    down; measured on Docker dev 2026-09-16, the ambient-only read logged
    ``auto_save_failed_missing_user_id`` on every lookup."""
    from tests.helpers.runtime_context import no_runtime_context

    result_data = {
        "success": True,
        "contacts_current_tests": [{"resource_name": "people/z", "name": "Zoe"}],
        "tool_name": "get_contacts",
    }
    with no_runtime_context():
        await manager.auto_save(
            context_type="contacts_current_test",
            result_data=result_data,
            config=config_ok,
            store=store,
            explicit_mode=ContextSaveMode.LIST,
            user_id=USER_ID,
        )
    context_list = await manager.get_list(
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert context_list is not None
    assert [item["name"] for item in context_list.items] == ["Zoe"]


async def _shown_list(manager, store) -> None:
    await manager.save_list(
        user_id=USER_ID,
        session_id="thread-1",
        domain="contacts_current_test",
        items=[
            {"resource_name": "people/a", "name": "Alice"},
            {"resource_name": "people/b", "name": "Bob"},
        ],
        metadata={"turn_id": 10, "total_count": 2, "timestamp": "2026-04-18T12:00:00Z"},
        store=store,
    )


@pytest.mark.asyncio
async def test_a_lookup_another_step_consumes_never_replaces_the_shown_list(manager, store):
    """ADR-367: « reply to Marc » searched the mailbox for one message, consumed
    by the reply step — and that search REPLACED the list of five the person had
    just seen, so a later « the second one » pointed into a list nobody saw."""
    await _shown_list(manager, store)
    intermediate = {
        "configurable": {"thread_id": "thread-1"},
        "metadata": {"turn_id": 11, "intermediate_step": True},
    }

    await manager.auto_save(
        context_type="contacts_current_test",
        result_data={
            "success": True,
            "contacts_current_tests": [{"resource_name": "people/c", "name": "Charlie"}],
            "tool_name": "search_contacts_tool",
        },
        config=intermediate,
        store=store,
        explicit_mode=ContextSaveMode.LIST,
    )

    shown = await manager.get_list(
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert shown is not None and [item["name"] for item in shown.items] == ["Alice", "Bob"]
    # The one item the lookup found is the conversation's current item.
    current = await manager.get_current_item(
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert current is not None and current["name"] == "Charlie"


@pytest.mark.asyncio
async def test_a_shown_search_still_replaces_the_list_dated_by_its_turn(manager, store, config_ok):
    await _shown_list(manager, store)

    await manager.auto_save(
        context_type="contacts_current_test",
        result_data={
            "success": True,
            "contacts_current_tests": [
                {"resource_name": "people/c", "name": "Charlie"},
                {"resource_name": "people/d", "name": "Dana"},
            ],
            "tool_name": "search_contacts_tool",
        },
        config=config_ok,
        store=store,
        explicit_mode=ContextSaveMode.LIST,
    )

    shown = await manager.get_list(
        user_id=USER_ID, session_id="thread-1", domain="contacts_current_test", store=store
    )
    assert shown is not None and [item["name"] for item in shown.items] == ["Charlie", "Dana"]
    assert shown.metadata.turn_id == 42
