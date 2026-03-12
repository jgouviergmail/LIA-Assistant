"""
Unit tests for domain-based Context Manager.

Tests the new architecture with domain namespacing, auto-set current_item,
and multi-domain support.
"""

from datetime import UTC, datetime

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.context.schemas import ToolContextCurrentItem, ToolContextList


@pytest.fixture
def store():
    """Fixture providing fresh InMemoryStore for each test."""
    return InMemoryStore()


@pytest.fixture
def manager():
    """Fixture providing ToolContextManager instance."""
    return ToolContextManager()


@pytest.fixture
def setup_registry():
    """Setup test context types in registry."""
    # Clear registry before tests
    ContextTypeRegistry.clear()

    # Register test domains
    ContextTypeRegistry.register(
        ContextTypeDefinition(
            domain="contacts",
            agent_name="contacts_agent",
            primary_id_field="resource_name",
            display_name_field="name",
            reference_fields=["name", "emails"],
            icon="📇",
        )
    )

    ContextTypeRegistry.register(
        ContextTypeDefinition(
            domain="emails",
            agent_name="emails_agent",
            primary_id_field="message_id",
            display_name_field="subject",
            reference_fields=["subject", "from"],
            icon="📧",
        )
    )

    yield

    # Cleanup
    ContextTypeRegistry.clear()


@pytest.mark.asyncio
class TestDomainBasedManager:
    """Test suite for domain-based context manager."""

    async def test_save_list_single_item_auto_sets_current(self, manager, store, setup_registry):
        """
        GIVEN a list with 1 item
        WHEN save_list is called
        THEN current_item should be auto-set
        """
        user_id = "user123"
        session_id = "sess456"
        session_id = "sess456"
        session_id = "sess456"
        domain = "contacts"
        items = [{"resource_name": "people/c1", "name": "Jean Dupond"}]
        metadata = {
            "turn_id": 1,
            "query": "cherche jean",
            "tool_name": "search_contacts_tool",
        }

        await manager.save_list(user_id, session_id, domain, items, metadata, store)

        # Verify list was saved
        context_list = await manager.get_list(user_id, session_id, domain, store)
        assert context_list is not None
        assert len(context_list.items) == 1
        assert context_list.items[0]["index"] == 1
        assert context_list.items[0]["name"] == "Jean Dupond"

        # Verify current_item was auto-set
        current = await manager.get_current_item(user_id, session_id, domain, store)
        assert current is not None
        assert current["index"] == 1
        assert current["name"] == "Jean Dupond"

    async def test_save_list_multiple_items_clears_current(self, manager, store, setup_registry):
        """
        GIVEN a list with multiple items
        WHEN save_list is called
        THEN current_item should be cleared (ambiguous)
        """
        user_id = "user123"
        session_id = "sess456"
        domain = "contacts"
        items = [
            {"resource_name": "people/c1", "name": "Jean Dupond"},
            {"resource_name": "people/c2", "name": "Marie Martin"},
            {"resource_name": "people/c3", "name": "Paul Durand"},
        ]
        metadata = {"turn_id": 1, "query": "liste contacts"}

        await manager.save_list(user_id, session_id, domain, items, metadata, store)

        # Verify list was saved
        context_list = await manager.get_list(user_id, session_id, domain, store)
        assert context_list is not None
        assert len(context_list.items) == 3
        assert all(item.get("index") for item in context_list.items)

        # Verify current_item is cleared
        current = await manager.get_current_item(user_id, session_id, domain, store)
        assert current is None

    async def test_set_current_item_explicitly(self, manager, store, setup_registry):
        """
        GIVEN a list with multiple items
        WHEN set_current_item is called explicitly
        THEN current_item should be set to specified item
        """
        user_id = "user123"
        session_id = "sess456"
        session_id = "sess456"
        domain = "contacts"
        items = [
            {"resource_name": "people/c1", "name": "Jean Dupond"},
            {"resource_name": "people/c2", "name": "Marie Martin"},
        ]
        metadata = {"turn_id": 1}

        # Save list (clears current_item)
        await manager.save_list(user_id, session_id, domain, items, metadata, store)

        # Explicitly set current_item to 2nd item
        await manager.set_current_item(
            user_id=user_id,
            session_id=session_id,
            domain=domain,
            item={"index": 2, "resource_name": "people/c2", "name": "Marie Martin"},
            set_by="explicit",
            turn_id=1,
            store=store,
        )

        # Verify current_item is set
        current = await manager.get_current_item(user_id, session_id, domain, store)
        assert current is not None
        assert current["index"] == 2
        assert current["name"] == "Marie Martin"

    async def test_multi_domain_isolation(self, manager, store, setup_registry):
        """
        GIVEN two domains (contacts, emails)
        WHEN save_list is called for each
        THEN both should be isolated with separate current_items
        """
        user_id = "user123"
        session_id = "sess456"
        session_id = "sess456"

        # Save contacts
        contacts = [{"resource_name": "people/c1", "name": "Jean Dupond"}]
        await manager.save_list(user_id, session_id, "contacts", contacts, {"turn_id": 1}, store)

        # Save emails
        emails = [
            {"message_id": "msg1", "subject": "Email 1"},
            {"message_id": "msg2", "subject": "Email 2"},
        ]
        await manager.save_list(user_id, session_id, "emails", emails, {"turn_id": 2}, store)

        # Verify contacts
        contacts_list = await manager.get_list(user_id, session_id, "contacts", store)
        contacts_current = await manager.get_current_item(user_id, session_id, "contacts", store)
        assert len(contacts_list.items) == 1
        assert contacts_current is not None  # Auto-set (1 item)

        # Verify emails
        emails_list = await manager.get_list(user_id, session_id, "emails", store)
        emails_current = await manager.get_current_item(user_id, session_id, "emails", store)
        assert len(emails_list.items) == 2
        assert emails_current is None  # Cleared (multiple items)

    async def test_list_active_domains(self, manager, store, setup_registry):
        """
        GIVEN multiple domains with data
        WHEN list_active_domains is called
        THEN all active domains should be returned with metadata
        """
        user_id = "user123"
        session_id = "sess456"
        session_id = "sess456"

        # Save data for 2 domains
        await manager.save_list(
            user_id,
            session_id,
            "contacts",
            [{"resource_name": "people/c1", "name": "Jean"}],
            {"turn_id": 1, "query": "cherche jean"},
            store,
        )

        await manager.save_list(
            user_id,
            session_id,
            "emails",
            [
                {"message_id": "msg1", "subject": "Email 1"},
                {"message_id": "msg2", "subject": "Email 2"},
            ],
            {"turn_id": 2, "query": "liste emails"},
            store,
        )

        # List active domains
        active = await manager.list_active_domains(user_id, session_id, store)

        assert len(active) == 2
        assert any(d["domain"] == "contacts" for d in active)
        assert any(d["domain"] == "emails" for d in active)

        # Check contacts metadata
        contacts = next(d for d in active if d["domain"] == "contacts")
        assert contacts["items_count"] == 1
        assert contacts["current_item"] is not None  # Auto-set
        assert contacts["last_query"] == "cherche jean"

        # Check emails metadata
        emails = next(d for d in active if d["domain"] == "emails")
        assert emails["items_count"] == 2
        assert emails["current_item"] is None  # Cleared (multiple)
        assert emails["last_query"] == "liste emails"

    async def test_namespace_structure(self, manager, store, setup_registry):
        """
        GIVEN save_list call
        WHEN inspecting Store namespace
        THEN namespace should be (user_id, session_id, "context", domain)
        """
        user_id = "user123"
        session_id = "sess456"
        domain = "contacts"

        namespace = manager._build_namespace(user_id, session_id, domain)

        assert namespace == ("user123", "sess456", "context", "contacts")
        assert len(namespace) == 4

    async def test_empty_list_clears_all(self, manager, store, setup_registry):
        """
        GIVEN a domain with data
        WHEN save_list is called with empty list
        THEN both list and current_item should be cleared
        """
        user_id = "user123"
        session_id = "sess456"
        domain = "contacts"

        # Save initial data
        await manager.save_list(
            user_id,
            session_id,
            domain,
            [{"resource_name": "people/c1", "name": "Jean"}],
            {"turn_id": 1},
            store,
        )

        # Verify data exists
        assert await manager.get_list(user_id, session_id, domain, store) is not None
        assert await manager.get_current_item(user_id, session_id, domain, store) is not None

        # Save empty list
        await manager.save_list(user_id, session_id, domain, [], {"turn_id": 2}, store)

        # Verify data cleared
        assert await manager.get_list(user_id, session_id, domain, store) is None
        assert await manager.get_current_item(user_id, session_id, domain, store) is None


class TestSchemas:
    """Test suite for new schemas."""

    def test_tool_context_list_schema(self):
        """Test ToolContextList schema validation."""
        from src.domains.agents.context.schemas import ContextMetadata

        list_data = ToolContextList(
            domain="contacts",
            items=[
                {"index": 1, "name": "Jean"},
                {"index": 2, "name": "Marie"},
            ],
            metadata=ContextMetadata(
                turn_id=1,
                total_count=2,
                timestamp=datetime.now(UTC).isoformat(),
            ),
        )

        assert list_data.domain == "contacts"
        assert len(list_data.items) == 2
        assert list_data.get_item_by_index(2)["name"] == "Marie"

    def test_tool_context_current_item_schema(self):
        """Test ToolContextCurrentItem schema validation."""
        current = ToolContextCurrentItem(
            domain="contacts",
            item={"index": 1, "name": "Jean", "resource_name": "people/c1"},
            set_at=datetime.now(UTC).isoformat(),
            set_by="auto",
            turn_id=1,
        )

        assert current.domain == "contacts"
        assert current.item["name"] == "Jean"
        assert current.set_by == "auto"


class TestRegistryDomainSupport:
    """Test registry domain support."""

    def test_domain_field_auto_sets_context_type(self):
        """Test that context_type is auto-set from domain."""
        ContextTypeRegistry.clear()

        definition = ContextTypeDefinition(
            domain="contacts",
            agent_name="contacts_agent",
            primary_id_field="resource_name",
            display_name_field="name",
            reference_fields=["name"],
        )

        assert definition.context_type == "contacts"

    def test_get_by_domain(self):
        """Test get_by_domain method."""
        ContextTypeRegistry.clear()

        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain="contacts",
                agent_name="contacts_agent",
                primary_id_field="resource_name",
                display_name_field="name",
                reference_fields=["name"],
            )
        )

        definition = ContextTypeRegistry.get_by_domain("contacts")
        assert definition.domain == "contacts"
        assert definition.agent_name == "contacts_agent"
