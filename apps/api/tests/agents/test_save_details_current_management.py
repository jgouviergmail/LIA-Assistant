"""
Tests for save_details() current_item management.

Validates the fix for save_details() to properly manage current_item
with the same rules as save_list():
- Single item → Auto-set current
- Multiple items → Clear current
- Empty items → Clear current

This ensures consistent UX regardless of tool type (list vs details).
"""

from datetime import UTC, datetime

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context import (
    ContextTypeDefinition,
    ContextTypeRegistry,
    ToolContextManager,
)


@pytest.fixture
async def setup_test_context():
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


class TestSaveDetailsSingleItemAutoSetCurrent:
    """Test that save_details() auto-sets current_item when saving 1 item."""

    @pytest.mark.asyncio
    async def test_save_details_single_item_sets_current_auto(self, setup_test_context):
        """When save_details() is called with 1 item, it should auto-set current."""
        ctx = setup_test_context
        manager = ctx["manager"]
        store = ctx["store"]

        items = [{"resource_name": "people/c123", "name": "Jean"}]
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

        # ✅ VERIFY: current_item should be auto-set
        current = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )

        assert current is not None, "current_item should be auto-set for single detail"
        assert current["resource_name"] == "people/c123"
        assert current["name"] == "Jean"
        assert current["index"] == 1

    @pytest.mark.asyncio
    async def test_save_details_single_item_has_set_by_auto(self, setup_test_context):
        """Verify that auto-set current_item has set_by='auto'."""
        ctx = setup_test_context
        manager = ctx["manager"]
        store = ctx["store"]

        items = [{"resource_name": "people/c999", "name": "Test"}]
        metadata = {
            "turn_id": 5,
            "total_count": 1,
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

        # Fetch raw item from store to check set_by
        namespace = manager._build_namespace(ctx["user_id"], ctx["session_id"], ctx["domain"])
        raw_item = await store.aget(namespace, "current")

        assert raw_item is not None
        assert raw_item.value["set_by"] == "auto", "set_by should be 'auto'"
        assert raw_item.value["turn_id"] == 5


class TestSaveDetailsMultipleItemsClearCurrent:
    """Test that save_details() clears current_item when saving >1 items."""

    @pytest.mark.asyncio
    async def test_save_details_multiple_items_clears_current(self, setup_test_context):
        """When save_details() is called with >1 items, it should clear current."""
        ctx = setup_test_context
        manager = ctx["manager"]
        store = ctx["store"]

        # Setup: Pre-set a current_item
        await manager.set_current_item(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            item={"resource_name": "people/c999", "name": "Old", "index": 99},
            set_by="explicit",
            turn_id=0,
            store=store,
        )

        # Verify pre-condition
        current_before = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )
        assert current_before is not None, "Pre-condition: current should be set"

        # Call save_details with multiple items
        items = [
            {"resource_name": "people/c123", "name": "Jean"},
            {"resource_name": "people/c456", "name": "Marie"},
        ]
        metadata = {
            "turn_id": 1,
            "total_count": 2,
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

        # ✅ VERIFY: current_item should be cleared (ambiguous)
        current_after = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )

        assert current_after is None, "current_item should be cleared when multiple details"

    @pytest.mark.asyncio
    async def test_save_details_three_items_clears_current(self, setup_test_context):
        """Test with 3 items to ensure rule applies to any count > 1."""
        ctx = setup_test_context
        manager = ctx["manager"]
        store = ctx["store"]

        # Pre-set current
        await manager.set_current_item(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            item={"resource_name": "people/c000", "name": "Old", "index": 1},
            set_by="auto",
            turn_id=0,
            store=store,
        )

        # Save 3 items
        items = [
            {"resource_name": "people/c1", "name": "Person 1"},
            {"resource_name": "people/c2", "name": "Person 2"},
            {"resource_name": "people/c3", "name": "Person 3"},
        ]
        metadata = {
            "turn_id": 2,
            "total_count": 3,
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

        current = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )

        assert current is None, "current should be cleared for 3+ items"


class TestSaveDetailsEmptyItemsClearCurrent:
    """Test that save_details() clears current_item when saving 0 items."""

    @pytest.mark.asyncio
    async def test_save_details_empty_items_clears_current(self, setup_test_context):
        """When save_details() is called with 0 items, it should clear current."""
        ctx = setup_test_context
        manager = ctx["manager"]
        store = ctx["store"]

        # Setup: Pre-set a current_item
        await manager.set_current_item(
            user_id=ctx["user_id"],
            session_id=ctx["session_id"],
            domain=ctx["domain"],
            item={"resource_name": "people/c888", "name": "Existing", "index": 1},
            set_by="explicit",
            turn_id=0,
            store=store,
        )

        # Save empty items
        items = []
        metadata = {
            "turn_id": 3,
            "total_count": 0,
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

        # ✅ VERIFY: current_item should be cleared
        current = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )

        assert current is None, "current_item should be cleared when empty details"


class TestConsistencyBetweenSaveListAndSaveDetails:
    """Test that save_list() and save_details() follow same rules for current."""

    @pytest.mark.asyncio
    async def test_single_item_both_set_current(self, setup_test_context):
        """Verify save_list() and save_details() both set current for single item."""
        ctx = setup_test_context
        manager = ctx["manager"]
        store_list = InMemoryStore()
        store_details = InMemoryStore()

        items = [{"resource_name": "people/c123", "name": "Jean"}]
        metadata = {
            "turn_id": 1,
            "total_count": 1,
            "tool_name": "test",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Test save_list
        await manager.save_list(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            items,
            metadata,
            store_list,
        )
        current_list = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store_list
        )

        # Test save_details
        await manager.save_details(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            items,
            metadata,
            store_details,
            max_items=10,
        )
        current_details = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store_details
        )

        # ✅ VERIFY: Both should have set current_item
        assert current_list is not None, "save_list should set current for single item"
        assert current_details is not None, "save_details should set current for single item"
        assert current_list["resource_name"] == current_details["resource_name"]
        assert current_list["name"] == current_details["name"]

    @pytest.mark.asyncio
    async def test_multiple_items_both_clear_current(self, setup_test_context):
        """Verify save_list() and save_details() both clear current for multiple items."""
        ctx = setup_test_context
        manager = ctx["manager"]
        store_list = InMemoryStore()
        store_details = InMemoryStore()

        # Pre-set current in both stores
        await manager.set_current_item(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            {"resource_name": "people/c000", "name": "Old", "index": 1},
            "explicit",
            0,
            store_list,
        )
        await manager.set_current_item(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            {"resource_name": "people/c000", "name": "Old", "index": 1},
            "explicit",
            0,
            store_details,
        )

        items = [
            {"resource_name": "people/c1", "name": "Person 1"},
            {"resource_name": "people/c2", "name": "Person 2"},
        ]
        metadata = {
            "turn_id": 1,
            "total_count": 2,
            "tool_name": "test",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Test save_list
        await manager.save_list(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            items,
            metadata,
            store_list,
        )
        current_list = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store_list
        )

        # Test save_details
        await manager.save_details(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            items,
            metadata,
            store_details,
            max_items=10,
        )
        current_details = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store_details
        )

        # ✅ VERIFY: Both should have cleared current_item
        assert current_list is None, "save_list should clear current for multiple items"
        assert current_details is None, "save_details should clear current for multiple items"


class TestE2EScenarios:
    """Test end-to-end scenarios with search → details flow."""

    @pytest.mark.asyncio
    async def test_search_then_single_detail_updates_current(self, setup_test_context):
        """
        E2E: User searches (multiple results) → Views single contact detail.
        Expected: current should be updated to the single detail item.
        """
        ctx = setup_test_context
        manager = ctx["manager"]
        store = ctx["store"]

        # Step 1: User searches → Multiple results
        search_results = [
            {"resource_name": "people/c1", "name": "Jean"},
            {"resource_name": "people/c2", "name": "Marie"},
            {"resource_name": "people/c3", "name": "Paul"},
        ]
        search_metadata = {
            "turn_id": 1,
            "tool_name": "search_contacts_tool",
            "query": "liste mes contacts",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await manager.save_list(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            search_results,
            search_metadata,
            store,
        )

        # Verify: current should be null (multiple results)
        current_after_search = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )
        assert current_after_search is None, "current should be null after multi-result search"

        # Step 2: User views details of single contact
        detail_items = [{"resource_name": "people/c2", "name": "Marie Martin"}]
        detail_metadata = {
            "turn_id": 2,
            "total_count": 1,
            "tool_name": "get_contact_details_tool",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await manager.save_details(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            detail_items,
            detail_metadata,
            store,
        )

        # ✅ VERIFY: current should now be set to Marie
        current_after_detail = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )

        assert current_after_detail is not None, "current should be set after viewing single detail"
        assert current_after_detail["resource_name"] == "people/c2"
        assert current_after_detail["name"] == "Marie Martin"

    @pytest.mark.asyncio
    async def test_search_then_batch_details_clears_current(self, setup_test_context):
        """
        E2E: User searches (single result) → Views batch details.
        Expected: current should be cleared (ambiguous batch).
        """
        ctx = setup_test_context
        manager = ctx["manager"]
        store = ctx["store"]

        # Step 1: User searches → Single result
        search_results = [{"resource_name": "people/c1", "name": "Jean"}]
        search_metadata = {
            "turn_id": 1,
            "tool_name": "search_contacts_tool",
            "query": "cherche Jean",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await manager.save_list(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            search_results,
            search_metadata,
            store,
        )

        # Verify: current should be set (single result)
        current_after_search = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )
        assert current_after_search is not None, "current should be set after single-result search"

        # Step 2: User views batch details
        detail_items = [
            {"resource_name": "people/c1", "name": "Jean Dupond"},
            {"resource_name": "people/c2", "name": "Jean Martin"},
        ]
        detail_metadata = {
            "turn_id": 2,
            "total_count": 2,
            "tool_name": "get_contact_details_tool",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await manager.save_details(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            detail_items,
            detail_metadata,
            store,
        )

        # ✅ VERIFY: current should be cleared (batch = ambiguous)
        current_after_batch = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )

        assert current_after_batch is None, "current should be cleared after batch details"


class TestDeduplicationWithCurrentManagement:
    """Test that LRU deduplication works correctly with current management."""

    @pytest.mark.asyncio
    async def test_deduplicated_single_item_maintains_current(self, setup_test_context):
        """
        When save_details merges and results in single item, current should be set.
        """
        ctx = setup_test_context
        manager = ctx["manager"]
        store = ctx["store"]

        # First save: 2 items
        items_first = [
            {"resource_name": "people/c1", "name": "Jean V1"},
            {"resource_name": "people/c2", "name": "Marie V1"},
        ]
        metadata_first = {
            "turn_id": 1,
            "total_count": 2,
            "tool_name": "get_contact_details_tool",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await manager.save_details(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            items_first,
            metadata_first,
            store,
        )

        # Current should be null (2 items)
        current_after_first = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )
        assert current_after_first is None, "current should be null with 2 items"

        # Second save: 1 NEW item (different from existing)
        # After merge: [people/c1, people/c2, people/c3] BUT max_items=1 evicts oldest
        # Result: Only people/c3 (most recent) remains
        items_second = [{"resource_name": "people/c3", "name": "Paul V1"}]
        metadata_second = {
            "turn_id": 2,
            "total_count": 1,
            "tool_name": "get_contact_details_tool",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await manager.save_details(
            ctx["user_id"],
            ctx["session_id"],
            ctx["domain"],
            items_second,
            metadata_second,
            store,
            max_items=1,  # Force eviction
        )

        # ✅ VERIFY: After eviction, single item remains → current should be set
        current_after_second = await manager.get_current_item(
            ctx["user_id"], ctx["session_id"], ctx["domain"], store
        )

        assert (
            current_after_second is not None
        ), "current should be set after eviction results in single item"
        # After eviction with max_items=1, only most recent (people/c3) remains
        assert current_after_second["resource_name"] == "people/c3"
        assert current_after_second["name"] == "Paul V1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
