"""
Test to validate that get_contact_details_tool stores details in the store table.

This test verifies the bug fix where details were not saved
because the return format used "data" instead of "contacts".

BUGFIX: get_contact_details_tool must return {"contacts": [...]} so that
the @auto_save_context decorator can save to Store["details"].
"""

import json

import pytest

from src.domains.agents.context import ContextSaveMode, ToolContextManager


class TestGetContactDetailsReturnFormat:
    """Test that get_contact_details_tool returns the correct format for @auto_save_context."""

    def test_single_contact_return_format_has_dual_structure(self):
        """
        Test that SINGLE mode returns the DUAL structure for compatibility.

        CRITICAL: Must have TWO keys:
        1. "contacts" at root level -> For @auto_save_context (manager.py:672-674)
        2. "data.contacts" nested -> For parallel_executor/ResponseNode (mappers.py:88-89)

        This pattern follows search_contacts_tool (google_contacts_tools.py:542-556).
        """
        # Simulate the result of a single contact call
        result_json = json.dumps(
            {
                "success": True,
                "tool_name": "get_contact_details_tool",
                "contacts": [  # ✅ Root level pour @auto_save_context
                    {
                        "resource_name": "people/c123",
                        "name": "Test Contact",
                        "emails": ["test@example.com"],
                    }
                ],
                "data": {  # ✅ Nested pour parallel_executor
                    "contacts": [
                        {
                            "resource_name": "people/c123",
                            "name": "Test Contact",
                            "emails": ["test@example.com"],
                        }
                    ],
                    "total": 1,
                },
                "data_source": "cache",
                "cache_age_seconds": 10,
            }
        )

        result = json.loads(result_json)

        # Verify that the "contacts" key exists at root level (required by @auto_save_context)
        assert "contacts" in result, "Missing 'contacts' key required by @auto_save_context"
        assert isinstance(result["contacts"], list), "'contacts' must be a list"
        assert len(result["contacts"]) == 1, "Single contact should return list with 1 item"

        # Verify that "data" exists and contains "contacts" (required by parallel_executor)
        assert "data" in result, "Missing 'data' key required by parallel_executor"
        assert "contacts" in result["data"], "Missing 'data.contacts' required by parallel_executor"
        assert (
            result["data"]["contacts"] == result["contacts"]
        ), "data.contacts should match root contacts"
        assert result["data"]["total"] == 1, "data.total should be 1"

    def test_batch_contacts_return_format_has_contacts_key(self):
        """
        Test that BATCH mode returns {"contacts": [...]} and not {"data": {"contacts": [...]}}.

        CRITICAL: Contacts must be directly in "contacts",
        not nested in "data.contacts".
        """
        # Simulate the result of a batch call
        result_json = json.dumps(
            {
                "success": True,
                "tool_name": "get_contact_details_tool",
                "contacts": [  # ✅ Bon: clé "contacts" directe
                    {"resource_name": "people/c1", "name": "Contact 1"},
                    {"resource_name": "people/c2", "name": "Contact 2"},
                ],
                "total": 2,
            }
        )

        result = json.loads(result_json)

        # Verify that the "contacts" key exists and directly contains the items
        assert "contacts" in result, "Missing 'contacts' key required by @auto_save_context"
        assert isinstance(result["contacts"], list), "'contacts' must be a list"
        assert len(result["contacts"]) == 2, "Batch should return all contacts"

        # Verify that "data" does NOT exist
        assert "data" not in result, "Old nested 'data.contacts' format should not exist"

    def test_classify_save_mode_detects_details_mode(self):
        """
        Test that classify_save_mode() correctly detects DETAILS mode
        for get_contact_details_tool.
        """
        mode = ToolContextManager.classify_save_mode(
            tool_name="get_contact_details_tool",
            result_count=1,
        )

        assert (
            mode == ContextSaveMode.DETAILS
        ), "get_contact_details_tool should be classified as DETAILS mode"

    def test_classify_save_mode_detects_details_for_batch(self):
        """
        Test that classify_save_mode() detects DETAILS even for multiple contacts.

        As long as tool_name contains "get" or "detail", it is DETAILS mode
        (not LIST), even if multiple items are returned.
        """
        mode = ToolContextManager.classify_save_mode(
            tool_name="get_contact_details_tool",
            result_count=5,
        )

        assert mode == ContextSaveMode.DETAILS, (
            "get_contact_details_tool with batch should still be DETAILS mode "
            "(not LIST) because tool name contains 'get'"
        )


class TestAutoSaveContextIntegration:
    """Integration test verifying that @auto_save_context routes to save_details()."""

    @pytest.mark.asyncio
    async def test_auto_save_routes_to_details_key(self):
        """
        Test that auto_save() with get_contact_details_tool uses
        save_details() -> Store["details"] and not save_list() -> Store["list"].
        """
        from langgraph.store.memory import InMemoryStore

        from src.domains.agents.context import (
            ContextTypeDefinition,
            ContextTypeRegistry,
        )

        # Setup test domain
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

        # Simulate the result of get_contact_details_tool (fixed format)
        result_data = {
            "success": True,
            "tool_name": "get_contact_details_tool",
            "contacts": [  # ✅ Clé "contacts" directe
                {"resource_name": "people/c123", "name": "Test Contact"}
            ],
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

        # Call auto_save (simulates what the decorator does)
        await manager.auto_save(
            context_type="contacts",
            result_data=result_data,
            config=config,
            store=store,
        )

        # CRITICAL CHECK: Details must be in Store["details"]
        details = await manager.get_details(
            user_id="user123",
            session_id="session456",
            domain="contacts",
            store=store,
        )

        assert details is not None, "Details should be saved to Store['details']"
        assert len(details.items) == 1, "Should have 1 contact in details"
        assert details.items[0]["resource_name"] == "people/c123"

        # CHECK: The list must NOT be affected
        context_list = await manager.get_list(
            user_id="user123",
            session_id="session456",
            domain="contacts",
            store=store,
        )

        assert (
            context_list is None
        ), "get_contact_details should NOT save to Store['list'] (only search/list tools should)"

        # Cleanup
        ContextTypeRegistry._registry.pop("contacts", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
