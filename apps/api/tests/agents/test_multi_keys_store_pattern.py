"""
Tests for Multi-Keys Store Pattern (Phase 3.2.9).

Validates the core fix for the context regression where get_contact_details
was overwriting search results, causing "affiche le 5ème" to fail.

Test Coverage:
    1. Classification logic (classify_save_mode)
    2. save_details LRU merge behavior
    3. save_list overwrite behavior
    4. E2E regression test: search → details → resolve reference
    5. Deduplication logic
    6. Eviction logic (max_items)
"""

from datetime import UTC, datetime

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context import (
    ContextSaveMode,
    ContextTypeDefinition,
    ContextTypeRegistry,
    ToolContextManager,
)


class TestClassificationLogic:
    """Test classify_save_mode() routing logic."""

    def test_classify_by_tool_name_search(self):
        """search_contacts_tool → LIST mode."""
        mode = ToolContextManager.classify_save_mode(
            tool_name="search_contacts_tool",
            result_count=10,
        )
        assert mode == ContextSaveMode.LIST

    def test_classify_by_tool_name_list(self):
        """list_contacts_tool → LIST mode."""
        mode = ToolContextManager.classify_save_mode(
            tool_name="list_contacts_tool",
            result_count=5,
        )
        assert mode == ContextSaveMode.LIST

    def test_classify_by_tool_name_get_details(self):
        """get_contact_details_tool → DETAILS mode."""
        mode = ToolContextManager.classify_save_mode(
            tool_name="get_contact_details_tool",
            result_count=2,
        )
        assert mode == ContextSaveMode.DETAILS

    def test_classify_by_tool_name_show(self):
        """show_contact_tool → DETAILS mode."""
        mode = ToolContextManager.classify_save_mode(
            tool_name="show_contact_tool",
            result_count=1,
        )
        assert mode == ContextSaveMode.DETAILS

    def test_classify_by_result_count_large(self):
        """Result count > 10 → LIST mode (when no keyword matches)."""
        mode = ToolContextManager.classify_save_mode(
            tool_name="load_contacts_tool",  # No search/list/get/fetch keyword
            result_count=50,
        )
        assert mode == ContextSaveMode.LIST

    def test_classify_by_result_count_small(self):
        """Result count <= 10 → DETAILS mode (default fallback)."""
        mode = ToolContextManager.classify_save_mode(
            tool_name="fetch_contacts_tool",  # No keyword
            result_count=3,
        )
        assert mode == ContextSaveMode.DETAILS

    def test_classify_explicit_mode_overrides(self):
        """Explicit mode from manifest has highest priority."""
        # Even though tool name says "search", explicit NONE wins
        mode = ToolContextManager.classify_save_mode(
            tool_name="search_contacts_tool",
            result_count=10,
            explicit_mode=ContextSaveMode.NONE,
        )
        assert mode == ContextSaveMode.NONE


class TestSaveDetailsLRUMerge:
    """Test save_details() LRU merge and deduplication logic."""

    @pytest.fixture
    async def setup_context(self):
        """Setup test context with registry and store."""
        # Register test domain
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain="test_contacts",
                agent_name="test_agent",
                context_type="test_contacts",
                primary_id_field="resource_name",
                display_name_field="name",
                reference_fields=["name"],
            )
        )

        store = InMemoryStore()
        manager = ToolContextManager()

        yield {
            "store": store,
            "manager": manager,
            "domain": "test_contacts",
            "user_id": "test_user",
            "session_id": "test_session",
        }

        # Cleanup
        ContextTypeRegistry._registry.pop("test_contacts", None)

    @pytest.mark.asyncio
    async def test_save_details_first_call(self, setup_context):
        """First save_details creates new ToolContextDetails."""
        ctx = setup_context
        manager = ctx["manager"]
        store = ctx["store"]

        items = [
            {"resource_name": "people/c123", "name": "Jean"},
        ]
        metadata = {
            "turn_id": 1,
            "total_count": 1,
            "query": None,
            "tool_name": "get_contact_details_tool",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await manager.save_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            items=items,
            metadata=metadata,
            store=store,
        )

        # Verify saved to "details" key
        details = await manager.get_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            store=store,
        )

        assert details is not None
        assert len(details.items) == 1
        assert details.items[0]["resource_name"] == "people/c123"
        assert details.items[0]["index"] == 1

    @pytest.mark.asyncio
    async def test_save_details_merge_new_items(self, setup_context):
        """Second save_details merges with existing items."""
        ctx = setup_context
        manager = ctx["manager"]
        store = ctx["store"]

        # First call: Save 1 item
        await manager.save_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            items=[{"resource_name": "people/c123", "name": "Jean"}],
            metadata={
                "turn_id": 1,
                "total_count": 1,
                "query": None,
                "tool_name": "get_contact_details_tool",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store=store,
        )

        # Second call: Save 2 more items
        await manager.save_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            items=[
                {"resource_name": "people/c456", "name": "Marie"},
                {"resource_name": "people/c789", "name": "Paul"},
            ],
            metadata={
                "turn_id": 2,
                "total_count": 2,
                "query": None,
                "tool_name": "get_contact_details_tool",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store=store,
        )

        # Verify merged: 3 items total
        details = await manager.get_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            store=store,
        )

        assert details is not None
        assert len(details.items) == 3
        assert details.items[0]["resource_name"] == "people/c123"
        assert details.items[1]["resource_name"] == "people/c456"
        assert details.items[2]["resource_name"] == "people/c789"
        # Verify reindexing
        assert details.items[0]["index"] == 1
        assert details.items[1]["index"] == 2
        assert details.items[2]["index"] == 3

    @pytest.mark.asyncio
    async def test_save_details_deduplication(self, setup_context):
        """Duplicate items (same primary_id) are replaced, not added."""
        ctx = setup_context
        manager = ctx["manager"]
        store = ctx["store"]

        # First call: Save item with version 1
        await manager.save_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            items=[{"resource_name": "people/c123", "name": "Jean v1"}],
            metadata={
                "turn_id": 1,
                "total_count": 1,
                "query": None,
                "tool_name": "get_contact_details_tool",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store=store,
        )

        # Second call: Save SAME item with version 2
        await manager.save_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            items=[{"resource_name": "people/c123", "name": "Jean v2 (updated)"}],
            metadata={
                "turn_id": 2,
                "total_count": 1,
                "query": None,
                "tool_name": "get_contact_details_tool",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store=store,
        )

        # Verify: Only 1 item (deduplicated), with updated data
        details = await manager.get_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            store=store,
        )

        assert details is not None
        assert len(details.items) == 1
        assert details.items[0]["resource_name"] == "people/c123"
        assert details.items[0]["name"] == "Jean v2 (updated)"

    @pytest.mark.asyncio
    async def test_save_details_eviction_max_items(self, setup_context):
        """LRU eviction when exceeding max_items."""
        ctx = setup_context
        manager = ctx["manager"]
        store = ctx["store"]

        # Save 12 items (exceeds default max_items=10)
        items = [
            {"resource_name": f"people/c{i}", "name": f"Contact {i}"} for i in range(1, 13)  # 1-12
        ]

        await manager.save_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            items=items,
            metadata={
                "turn_id": 1,
                "total_count": 12,
                "query": None,
                "tool_name": "get_contact_details_tool",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store=store,
            max_items=10,
        )

        # Verify: Only last 10 items kept (evicted oldest 2)
        details = await manager.get_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            store=store,
        )

        assert details is not None
        assert len(details.items) == 10
        # First item should be "Contact 3" (items 1-2 evicted)
        assert details.items[0]["resource_name"] == "people/c3"
        assert details.items[-1]["resource_name"] == "people/c12"


class TestRegressionE2E:
    """
    E2E test reproducing the exact regression scenario.

    Scenario:
        1. search_contacts("jean") → 10 results
        2. get_contact_details(5th, 7th) → 2 detailed contacts
        3. User asks "affiche le detail du 5ème"
        4. resolve_reference("5") should WORK (find 5th from original search)

    Before Fix:
        - Step 2 overwrote "list" → only 2 items
        - Step 4 failed: "only 2 items in list"

    After Fix (Multi-Keys Store Pattern):
        - Step 1: save_list → Store["list"] = 10 items
        - Step 2: save_details → Store["details"] = 2 items (SEPARATE KEY!)
        - Step 4: resolve_reference uses "list" (still has 10 items) → SUCCESS
    """

    @pytest.fixture
    async def setup_regression_test(self):
        """Setup contacts domain for regression test."""
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain="contacts",
                agent_name="contacts_agent",
                context_type="contacts",
                primary_id_field="resource_name",
                display_name_field="name",
                reference_fields=["name"],
            )
        )

        store = InMemoryStore()
        manager = ToolContextManager()

        yield {
            "store": store,
            "manager": manager,
            "user_id": "user123",
            "session_id": "session456",
        }

        # Cleanup
        ContextTypeRegistry._registry.pop("contacts", None)

    @pytest.mark.asyncio
    async def test_regression_search_then_details(self, setup_regression_test):
        """
        Regression test: search(10) → get_details(2) → resolve("5") MUST WORK.
        """
        ctx = setup_regression_test
        manager = ctx["manager"]
        store = ctx["store"]

        # Step 1: search_contacts("jean") → 10 results
        search_items = [
            {"resource_name": f"people/c{i}", "name": f"Contact {i}"}
            for i in range(1, 11)  # 10 contacts
        ]

        await manager.save_list(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain="contacts",
            items=search_items,
            metadata={
                "turn_id": 1,
                "total_count": 10,
                "query": "jean",
                "tool_name": "search_contacts_tool",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store=store,
        )

        # Step 2: get_contact_details(5th, 7th) → 2 detailed contacts
        details_items = [
            {"resource_name": "people/c5", "name": "Contact 5 (detailed)"},
            {"resource_name": "people/c7", "name": "Contact 7 (detailed)"},
        ]

        await manager.save_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain="contacts",
            items=details_items,
            metadata={
                "turn_id": 2,
                "total_count": 2,
                "query": None,
                "tool_name": "get_contact_details_tool",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store=store,
        )

        # Step 3: Verify "list" still has 10 items (NOT overwritten!)
        context_list = await manager.get_list(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain="contacts",
            store=store,
        )

        assert context_list is not None
        assert len(context_list.items) == 10, "REGRESSION: list was overwritten by details!"
        assert context_list.items[4]["resource_name"] == "people/c5"  # 5th item (index 5)

        # Step 4: Verify "details" has 2 items (stored separately)
        details = await manager.get_details(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain="contacts",
            store=store,
        )

        assert details is not None
        assert len(details.items) == 2
        assert details.items[0]["resource_name"] == "people/c5"
        assert details.items[1]["resource_name"] == "people/c7"

        # Step 5: resolve_reference("5") should find 5th item from "list"
        # (This would fail before the fix because list only had 2 items)
        from src.domains.agents.context.resolver import ReferenceResolver

        definition = ContextTypeRegistry.get_definition("contacts")
        resolver = ReferenceResolver(definition)

        result = resolver.resolve("5", context_list.items)

        assert result.success is True, f"Failed to resolve '5': {result.message}"
        assert result.item["resource_name"] == "people/c5"
        assert result.match_type == "index"
        assert result.confidence == 1.0


class TestAutoSaveRouting:
    """Test auto_save() routing to save_list vs save_details."""

    @pytest.fixture
    async def setup_auto_save_test(self):
        """Setup for auto_save routing tests."""
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain="contacts",
                agent_name="contacts_agent",
                context_type="contacts",
                primary_id_field="resource_name",
                display_name_field="name",
                reference_fields=["name"],
            )
        )

        store = InMemoryStore()
        manager = ToolContextManager()

        yield {
            "store": store,
            "manager": manager,
        }

        # Cleanup
        ContextTypeRegistry._registry.pop("contacts", None)

    @pytest.mark.asyncio
    async def test_auto_save_routes_to_list(self, setup_auto_save_test):
        """auto_save with search_contacts_tool → save_list (Store["list"])."""
        ctx = setup_auto_save_test
        manager = ctx["manager"]
        store = ctx["store"]

        result_data = {
            "success": True,
            "contacts": [
                {"resource_name": f"people/c{i}", "name": f"Contact {i}"} for i in range(1, 6)
            ],
            "tool_name": "search_contacts_tool",
            "query": "test",
        }

        config = {
            "configurable": {
                "user_id": "user123",
                "thread_id": "session456",
            },
            "metadata": {
                "turn_id": 1,
            },
        }

        await manager.auto_save(
            context_type="contacts",
            result_data=result_data,
            config=config,
            store=store,
        )

        # Verify saved to "list" key
        context_list = await manager.get_list(
            user_id="user123",
            session_id="session456",
            domain="contacts",
            store=store,
        )

        assert context_list is not None
        assert len(context_list.items) == 5

        # Verify NOT saved to "details" key
        details = await manager.get_details(
            user_id="user123",
            session_id="session456",
            domain="contacts",
            store=store,
        )
        assert details is None

    @pytest.mark.asyncio
    async def test_auto_save_routes_to_details(self, setup_auto_save_test):
        """auto_save with get_contact_details_tool → save_details (Store["details"])."""
        ctx = setup_auto_save_test
        manager = ctx["manager"]
        store = ctx["store"]

        # First, save a search list
        await manager.save_list(
            user_id="user123",
            session_id="session456",
            domain="contacts",
            items=[{"resource_name": f"people/c{i}", "name": f"Contact {i}"} for i in range(1, 11)],
            metadata={
                "turn_id": 1,
                "total_count": 10,
                "query": "test",
                "tool_name": "search_contacts_tool",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store=store,
        )

        # Then auto_save details
        result_data = {
            "success": True,
            "contacts": [
                {"resource_name": "people/c5", "name": "Contact 5 (detailed)"},
            ],
            "tool_name": "get_contact_details_tool",
            "query": None,
        }

        config = {
            "configurable": {
                "user_id": "user123",
                "thread_id": "session456",
            },
            "metadata": {
                "turn_id": 2,
            },
        }

        await manager.auto_save(
            context_type="contacts",
            result_data=result_data,
            config=config,
            store=store,
        )

        # Verify "list" still has 10 items (NOT overwritten!)
        context_list = await manager.get_list(
            user_id="user123",
            session_id="session456",
            domain="contacts",
            store=store,
        )
        assert context_list is not None
        assert len(context_list.items) == 10

        # Verify "details" has 1 item (saved to separate key)
        details = await manager.get_details(
            user_id="user123",
            session_id="session456",
            domain="contacts",
            store=store,
        )
        assert details is not None
        assert len(details.items) == 1
        assert details.items[0]["resource_name"] == "people/c5"
