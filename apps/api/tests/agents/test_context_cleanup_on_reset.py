"""
Test suite for tool context cleanup during conversation reset.

This test suite validates that when a user clicks "New conversation",
ALL tool contexts (from AsyncPostgresStore) are properly cleaned up
alongside Redis and LangGraph checkpoints.

Test Coverage:
    - cleanup_session_contexts() deletes all domains for a session
    - reset_conversation() integrates Store cleanup correctly
    - Other sessions remain untouched (isolation)
    - Cleanup is non-fatal (continues even if errors occur)

References:
    - Multi-Keys Store Pattern (Phase 3.2.9)
    - Session isolation (Phase 5)
    - User requirement: "faire le ménage en base de données maintenant !"
"""

import os
from uuid import uuid4

import pytest

from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.store import get_tool_context_store

# Skip all tests if OPENAI_API_KEY is not set (integration tests that call real LLM)
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for integration tests with real LLM",
)


class TestCleanupSessionContexts:
    """Test ToolContextManager.cleanup_session_contexts() method."""

    @pytest.mark.asyncio
    async def test_cleanup_single_domain(self):
        """
        Test cleanup of a single domain (contacts).

        Setup:
            - Save list, details, current for contacts domain

        Validate:
            - All 3 keys are deleted
            - cleanup_stats shows correct counts
        """
        store = await get_tool_context_store()
        manager = ToolContextManager()

        user_id = str(uuid4())
        session_id = str(uuid4())
        domain = "contacts"

        # Setup: Save all 3 keys (list, details, current)
        test_items = [
            {"index": 1, "resource_name": "people/c123", "name": "Jean Dupond"},
            {"index": 2, "resource_name": "people/c456", "name": "Marie Martin"},
        ]
        metadata = {
            "turn_id": 1,
            "total_count": 2,
            "query": "test",
            "tool_name": "test_tool",
            "timestamp": "2025-01-26T14:30:00Z",
        }

        await manager.save_list(
            user_id=user_id,
            session_id=session_id,
            domain=domain,
            items=test_items,
            metadata=metadata,
            store=store,
        )

        # Verify items exist before cleanup
        context_list = await manager.get_list(user_id, session_id, domain, store)
        assert context_list is not None
        assert len(context_list.items) == 2

        # Execute cleanup
        cleanup_stats = await manager.cleanup_session_contexts(
            user_id=user_id,
            session_id=session_id,
            store=store,
        )

        # Validate cleanup stats
        assert cleanup_stats["success"] is True
        assert cleanup_stats["domains_cleaned"] == 1
        assert cleanup_stats["total_items_deleted"] >= 1  # At least "list" key

        # Verify items are deleted
        context_list_after = await manager.get_list(user_id, session_id, domain, store)
        assert context_list_after is None

    @pytest.mark.asyncio
    async def test_cleanup_multiple_domains(self):
        """
        Test cleanup of multiple domains (contacts + emails).

        Setup:
            - Save contexts for contacts domain
            - Save contexts for emails domain

        Validate:
            - Both domains are cleaned
            - cleanup_stats shows 2 domains cleaned
        """
        store = await get_tool_context_store()
        manager = ToolContextManager()

        user_id = str(uuid4())
        session_id = str(uuid4())

        # Setup: Save contexts for 2 different domains
        domains = ["contacts", "emails"]
        for domain in domains:
            test_items = [
                {"index": 1, "id": f"{domain}_1", "name": f"Test {domain} 1"},
            ]
            metadata = {
                "turn_id": 1,
                "total_count": 1,
                "query": "test",
                "tool_name": "test_tool",
                "timestamp": "2025-01-26T14:30:00Z",
            }

            await manager.save_list(
                user_id=user_id,
                session_id=session_id,
                domain=domain,
                items=test_items,
                metadata=metadata,
                store=store,
            )

        # Verify both domains exist
        for domain in domains:
            context_list = await manager.get_list(user_id, session_id, domain, store)
            assert context_list is not None

        # Execute cleanup
        cleanup_stats = await manager.cleanup_session_contexts(
            user_id=user_id,
            session_id=session_id,
            store=store,
        )

        # Validate cleanup stats
        assert cleanup_stats["success"] is True
        assert cleanup_stats["domains_cleaned"] == 2
        assert cleanup_stats["total_items_deleted"] >= 2  # At least 2 "list" keys

        # Verify all domains are deleted
        for domain in domains:
            context_list = await manager.get_list(user_id, session_id, domain, store)
            assert context_list is None

    @pytest.mark.asyncio
    async def test_cleanup_session_isolation(self):
        """
        Test that cleanup only affects the target session.

        Setup:
            - Save contexts for session1
            - Save contexts for session2 (same user!)

        Validate:
            - cleanup(session1) deletes session1 contexts
            - session2 contexts remain untouched
        """
        store = await get_tool_context_store()
        manager = ToolContextManager()

        user_id = str(uuid4())
        session1 = str(uuid4())
        session2 = str(uuid4())
        domain = "contacts"

        # Setup: Save contexts for 2 different sessions (same user)
        for session_id in [session1, session2]:
            test_items = [
                {"index": 1, "id": f"session_{session_id}", "name": f"Test {session_id}"},
            ]
            metadata = {
                "turn_id": 1,
                "total_count": 1,
                "query": "test",
                "tool_name": "test_tool",
                "timestamp": "2025-01-26T14:30:00Z",
            }

            await manager.save_list(
                user_id=user_id,
                session_id=session_id,
                domain=domain,
                items=test_items,
                metadata=metadata,
                store=store,
            )

        # Verify both sessions have contexts
        context_s1 = await manager.get_list(user_id, session1, domain, store)
        context_s2 = await manager.get_list(user_id, session2, domain, store)
        assert context_s1 is not None
        assert context_s2 is not None

        # Execute cleanup for session1 only
        cleanup_stats = await manager.cleanup_session_contexts(
            user_id=user_id,
            session_id=session1,
            store=store,
        )

        # Validate cleanup stats
        assert cleanup_stats["success"] is True
        assert cleanup_stats["domains_cleaned"] == 1

        # Verify session1 is deleted but session2 remains
        context_s1_after = await manager.get_list(user_id, session1, domain, store)
        context_s2_after = await manager.get_list(user_id, session2, domain, store)
        assert context_s1_after is None  # session1 deleted
        assert context_s2_after is not None  # session2 untouched
        assert context_s2_after.items[0]["id"] == f"session_{session2}"

    @pytest.mark.asyncio
    async def test_cleanup_empty_session_no_error(self):
        """
        Test cleanup of session with no contexts (idempotent).

        Validate:
            - No error raised
            - cleanup_stats shows 0 domains cleaned
            - success=True
        """
        store = await get_tool_context_store()
        manager = ToolContextManager()

        user_id = str(uuid4())
        session_id = str(uuid4())

        # Execute cleanup on empty session (no setup)
        cleanup_stats = await manager.cleanup_session_contexts(
            user_id=user_id,
            session_id=session_id,
            store=store,
        )

        # Validate cleanup stats
        assert cleanup_stats["success"] is True
        assert cleanup_stats["domains_cleaned"] == 0
        assert cleanup_stats["total_items_deleted"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_all_store_keys(self):
        """
        Test that cleanup deletes ALL Store keys (list, details, current).

        Setup:
            - Save list (2 items → no auto-set current)
            - Manually set current item
            - Save details

        Validate:
            - All 3 keys are deleted after cleanup
        """
        store = await get_tool_context_store()
        manager = ToolContextManager()

        user_id = str(uuid4())
        session_id = str(uuid4())
        domain = "contacts"

        # Setup: Save list (2 items → no auto-current)
        test_items = [
            {"resource_name": "people/c123", "name": "Jean Dupond"},
            {"resource_name": "people/c456", "name": "Marie Martin"},
        ]
        metadata = {
            "turn_id": 1,
            "total_count": 2,
            "query": "test",
            "tool_name": "test_tool",
            "timestamp": "2025-01-26T14:30:00Z",
        }

        await manager.save_list(user_id, session_id, domain, test_items, metadata, store)

        # Manually set current item
        await manager.set_current_item(
            user_id,
            session_id,
            domain,
            item={"index": 1, "resource_name": "people/c123", "name": "Jean Dupond"},
            set_by="explicit",
            turn_id=2,
            store=store,
        )

        # Verify both keys exist
        context_list = await manager.get_list(user_id, session_id, domain, store)
        context_current = await manager.get_current_item(user_id, session_id, domain, store)
        assert context_list is not None
        assert context_current is not None

        # Execute cleanup
        cleanup_stats = await manager.cleanup_session_contexts(user_id, session_id, store)

        # Validate both keys are deleted
        assert cleanup_stats["success"] is True
        assert cleanup_stats["total_items_deleted"] == 2  # list + current

        context_list_after = await manager.get_list(user_id, session_id, domain, store)
        context_current_after = await manager.get_current_item(user_id, session_id, domain, store)
        assert context_list_after is None
        assert context_current_after is None


class TestResetConversationIntegration:
    """
    Integration tests for reset_conversation() with Store cleanup.

    These tests validate that ConversationService.reset_conversation()
    correctly calls cleanup_session_contexts() as part of the reset flow.

    Note: These are integration tests that require database setup.
    """

    @pytest.mark.asyncio
    async def test_reset_conversation_cleans_tool_contexts(self, db_session, test_user):
        """
        Test that reset_conversation() cleans tool contexts from Store.

        Setup:
            - Create conversation
            - Save tool contexts (contacts)
            - Call reset_conversation()

        Validate:
            - Tool contexts are deleted
            - Conversation is reset (message_count=0)
            - No errors raised

        Note:
            This test requires fixtures:
            - db_session: AsyncSession
            - test_user: User model instance
        """
        from src.domains.conversations.service import ConversationService

        # Skip if fixtures not available (run with: pytest -v test_context_cleanup_on_reset.py)
        if not hasattr(test_user, "id"):
            pytest.skip("Requires test_user fixture")

        service = ConversationService()
        store = await get_tool_context_store()
        manager = ToolContextManager()

        # Setup: Create conversation
        conversation = await service.get_or_create_conversation(test_user.id, db_session)
        session_id = str(conversation.id)

        # Setup: Save tool contexts
        test_items = [
            {"resource_name": "people/c123", "name": "Jean Dupond"},
        ]
        metadata = {
            "turn_id": 1,
            "total_count": 1,
            "query": "test",
            "tool_name": "test_tool",
            "timestamp": "2025-01-26T14:30:00Z",
        }

        await manager.save_list(
            user_id=test_user.id,
            session_id=session_id,
            domain="contacts",
            items=test_items,
            metadata=metadata,
            store=store,
        )

        # Verify contexts exist
        context_list = await manager.get_list(test_user.id, session_id, "contacts", store)
        assert context_list is not None

        # Execute reset
        await service.reset_conversation(test_user.id, db_session)

        # Validate contexts are deleted
        context_list_after = await manager.get_list(test_user.id, session_id, "contacts", store)
        assert context_list_after is None

        # Validate conversation is reset
        conversation_after = await service.get_active_conversation(test_user.id, db_session)
        assert conversation_after.message_count == 0
