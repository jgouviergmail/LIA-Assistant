"""
Tests for Context Resolution Filtering (BugFix 2025-12-19).

Validates the multi-level filtering strategy to prevent cross-domain contamination
when resolving ordinal references like "le deuxième".

Bug Fixed:
- User asks for "détail du deuxième email" after searching emails
- System returned details of the second CONTACT instead of second EMAIL
- Root cause: Fallback to ALL registry items when filtering by turn failed

Solution:
- Multi-level filtering strategy (registry_updates → turn_id → domain → empty)
- Added turn_id to RegistryItemMeta for robust filtering
- Domain-based fallback using agent_results detection
"""

import pytest

from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.services.context_resolution_service import (
    ContextResolutionService,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def context_service():
    """Create a ContextResolutionService instance for testing."""
    return ContextResolutionService()


@pytest.fixture
def registry_with_mixed_domains() -> dict:
    """Create a registry with items from multiple domains (contacts + emails)."""
    return {
        "contact_abc123": RegistryItem(
            id="contact_abc123",
            type=RegistryItemType.CONTACT,
            payload={
                "resourceName": "people/c123",
                "names": [{"displayName": "Jean Dupont"}],
            },
            meta=RegistryItemMeta(
                source="google_contacts",
                domain="contacts",
                turn_id=1,
            ),
        ),
        "contact_def456": RegistryItem(
            id="contact_def456",
            type=RegistryItemType.CONTACT,
            payload={
                "resourceName": "people/c456",
                "names": [{"displayName": "Marie Martin"}],
            },
            meta=RegistryItemMeta(
                source="google_contacts",
                domain="contacts",
                turn_id=1,
            ),
        ),
        "email_ghi789": RegistryItem(
            id="email_ghi789",
            type=RegistryItemType.EMAIL,
            payload={
                "id": "msg123",
                "subject": "Réunion demain",
                "snippet": "Bonjour...",
            },
            meta=RegistryItemMeta(
                source="gmail",
                domain="emails",
                turn_id=2,
            ),
        ),
        "email_jkl012": RegistryItem(
            id="email_jkl012",
            type=RegistryItemType.EMAIL,
            payload={
                "id": "msg456",
                "subject": "Projet X",
                "snippet": "Concernant le projet...",
            },
            meta=RegistryItemMeta(
                source="gmail",
                domain="emails",
                turn_id=2,
            ),
        ),
    }


@pytest.fixture
def state_with_registry(registry_with_mixed_domains):
    """Create a state dict with the mixed domain registry."""
    return {"registry": registry_with_mixed_domains}


@pytest.fixture
def agent_results_with_registry_updates():
    """Create agent_results with registry_updates for turn 2 (emails)."""
    return {
        "1:plan_executor": {
            "registry_updates": {
                "contact_abc123": {"type": "CONTACT"},
                "contact_def456": {"type": "CONTACT"},
            },
            "domain": "contacts",
        },
        "2:plan_executor": {
            "registry_updates": {
                "email_ghi789": {"type": "EMAIL"},
                "email_jkl012": {"type": "EMAIL"},
            },
            "domain": "emails",
        },
    }


# ============================================================================
# Tests: Strategy 1 - Filter by registry_updates
# ============================================================================


class TestFilterByRegistryUpdates:
    """Tests for filtering by registry_updates from agent_results."""

    def test_filters_by_registry_updates_for_turn(
        self, context_service, state_with_registry, agent_results_with_registry_updates
    ):
        """1.1: Filter by registry_updates when available."""
        items = context_service._extract_items_from_registry(
            state=state_with_registry,
            run_id="test-run-001",
            last_action_turn=2,
            agent_results=agent_results_with_registry_updates,
        )

        # Should return only emails (from turn 2)
        assert len(items) == 2
        for item in items:
            assert item.get("_item_type") == "EMAIL"

    def test_returns_contacts_for_turn_1(
        self, context_service, state_with_registry, agent_results_with_registry_updates
    ):
        """1.2: Filter by registry_updates returns contacts for turn 1."""
        items = context_service._extract_items_from_registry(
            state=state_with_registry,
            run_id="test-run-002",
            last_action_turn=1,
            agent_results=agent_results_with_registry_updates,
        )

        # Should return only contacts (from turn 1)
        assert len(items) == 2
        for item in items:
            assert item.get("_item_type") == "CONTACT"


# ============================================================================
# Tests: Strategy 2 - Filter by turn_id in RegistryItem.meta
# ============================================================================


class TestFilterByTurnIdMeta:
    """Tests for filtering by turn_id in RegistryItem.meta."""

    def test_filters_by_turn_id_meta_when_no_registry_updates(
        self, context_service, state_with_registry
    ):
        """2.1: Fall back to turn_id meta when registry_updates is empty."""
        # Agent results without registry_updates
        agent_results = {
            "2:plan_executor": {
                "data": {"success": True},
                "tool_name": "get_email_details_tool",
            }
        }

        items = context_service._extract_items_from_registry(
            state=state_with_registry,
            run_id="test-run-003",
            last_action_turn=2,
            agent_results=agent_results,
        )

        # Should return only emails (turn_id=2 in meta)
        assert len(items) == 2
        for item in items:
            assert item.get("_item_type") == "EMAIL"


# ============================================================================
# Tests: Strategy 3 - Filter by domain from agent_results
# ============================================================================


class TestFilterByDomain:
    """Tests for filtering by domain when turn_id filtering fails."""

    def test_filters_by_domain_from_tool_name(self, context_service):
        """3.1: Detect domain from tool_name in agent_results."""
        # Registry without turn_id in meta
        registry = {
            "contact_no_turn": RegistryItem(
                id="contact_no_turn",
                type=RegistryItemType.CONTACT,
                payload={"resourceName": "people/c999"},
                meta=RegistryItemMeta(
                    source="google_contacts",
                    domain="contacts",
                    turn_id=None,  # No turn_id
                ),
            ),
            "email_no_turn": RegistryItem(
                id="email_no_turn",
                type=RegistryItemType.EMAIL,
                payload={"id": "msg999"},
                meta=RegistryItemMeta(
                    source="gmail",
                    domain="emails",
                    turn_id=None,  # No turn_id
                ),
            ),
        }

        agent_results = {
            "3:plan_executor": {
                "data": {"success": True},
                "tool_name": "search_emails_tool",
            }
        }

        items = context_service._extract_items_from_registry(
            state={"registry": registry},
            run_id="test-run-004",
            last_action_turn=3,
            agent_results=agent_results,
        )

        # Should return only emails (detected from tool_name)
        assert len(items) == 1
        assert items[0].get("_item_type") == "EMAIL"

    def test_filters_by_domain_from_data_keys(self, context_service):
        """3.2: Detect domain from data keys in agent_results."""
        registry = {
            "contact_no_turn": RegistryItem(
                id="contact_no_turn",
                type=RegistryItemType.CONTACT,
                payload={"resourceName": "people/c999"},
                meta=RegistryItemMeta(
                    source="google_contacts",
                    domain="contacts",
                    turn_id=None,
                ),
            ),
            "email_no_turn": RegistryItem(
                id="email_no_turn",
                type=RegistryItemType.EMAIL,
                payload={"id": "msg999"},
                meta=RegistryItemMeta(
                    source="gmail",
                    domain="emails",
                    turn_id=None,
                ),
            ),
        }

        agent_results = {
            "4:plan_executor": {
                "data": {
                    "contacts": [{"name": "Test"}],  # contacts key present
                    "success": True,
                }
            }
        }

        items = context_service._extract_items_from_registry(
            state={"registry": registry},
            run_id="test-run-005",
            last_action_turn=4,
            agent_results=agent_results,
        )

        # Should return only contacts (detected from "contacts" key)
        assert len(items) == 1
        assert items[0].get("_item_type") == "CONTACT"


# ============================================================================
# Tests: Strategy 4 - Safe Fallback (Return Empty)
# ============================================================================


class TestSafeFallback:
    """Tests for safe fallback returning empty list."""

    def test_returns_empty_when_all_filters_fail(self, context_service):
        """4.1: Return empty list when all filtering strategies fail."""
        # Registry without turn_id and with unknown domain
        registry = {
            "unknown_item": RegistryItem(
                id="unknown_item",
                type=RegistryItemType.NOTE,  # Not a standard domain
                payload={"content": "Some note"},
                meta=RegistryItemMeta(
                    source="manual",
                    domain="notes",  # Not in domain detection
                    turn_id=None,
                ),
            ),
        }

        # Agent results without domain hints
        agent_results = {
            "5:plan_executor": {
                "data": {"success": True},
                # No tool_name, no domain key
            }
        }

        items = context_service._extract_items_from_registry(
            state={"registry": registry},
            run_id="test-run-006",
            last_action_turn=5,
            agent_results=agent_results,
        )

        # Should return empty list (safe fallback)
        assert items == []

    def test_never_returns_all_items(self, context_service, state_with_registry):
        """4.2: CRITICAL - Never return all items to prevent cross-domain contamination."""
        # Agent results for turn 99 (doesn't exist in registry)
        agent_results = {
            "99:plan_executor": {
                "data": {"success": True},
            }
        }

        items = context_service._extract_items_from_registry(
            state=state_with_registry,
            run_id="test-run-007",
            last_action_turn=99,
            agent_results=agent_results,
        )

        # CRITICAL: Should return empty, NOT all 4 items
        # This prevents "le deuxième email" from returning a contact
        assert items == []
        assert len(items) != 4  # Explicitly check we don't return all items


# ============================================================================
# Tests: Helper Functions
# ============================================================================


class TestDomainDetection:
    """Tests for domain detection helper functions."""

    def test_detect_domain_from_tool_name(self, context_service):
        """Helper: Detect domain from tool_name patterns."""
        agent_results = {"1:plan_executor": {"tool_name": "search_contacts_tool"}}
        domain = context_service._detect_domain_from_agent_results(
            agent_results, turn_id=1, run_id="test"
        )
        assert domain == "contacts"

        agent_results = {"1:plan_executor": {"tool_name": "get_email_details_tool"}}
        domain = context_service._detect_domain_from_agent_results(
            agent_results, turn_id=1, run_id="test"
        )
        assert domain == "emails"

        agent_results = {"1:plan_executor": {"tool_name": "search_places_tool"}}
        domain = context_service._detect_domain_from_agent_results(
            agent_results, turn_id=1, run_id="test"
        )
        assert domain == "places"

    def test_derive_domain_from_type(self, context_service):
        """Helper: Derive domain from RegistryItemType."""
        assert context_service._derive_domain_from_type("EMAIL") == "emails"
        assert context_service._derive_domain_from_type("CONTACT") == "contacts"
        assert context_service._derive_domain_from_type("EVENT") == "calendar"
        assert context_service._derive_domain_from_type("PLACE") == "places"
        assert context_service._derive_domain_from_type("UNKNOWN") is None


# ============================================================================
# Integration Test: Full Scenario
# ============================================================================


class TestCrossdomainScenario:
    """Integration test for the cross-domain bug scenario."""

    def test_le_deuxieme_email_after_contact_search(
        self, context_service, registry_with_mixed_domains
    ):
        """
        INTEGRATION: "le deuxième" after email search should return email, not contact.

        Scenario:
        1. Turn 1: User searches contacts -> registry has 2 contacts
        2. Turn 2: User searches emails -> registry has 2 contacts + 2 emails
        3. Turn 3: User asks "détail du deuxième" (reference query)
           - last_action_turn_id = 2 (email search)
           - Expected: Return 2nd EMAIL, not 2nd item overall

        BugFix: Without proper filtering, "le deuxième" would return the 2nd item
        in the registry (which could be a contact), causing the planner to call
        get_contact_details instead of get_email_details.
        """
        state = {"registry": registry_with_mixed_domains}

        # Agent results show turn 2 was an email search
        agent_results = {
            "1:plan_executor": {
                "registry_updates": {
                    "contact_abc123": {},
                    "contact_def456": {},
                },
                "domain": "contacts",
            },
            "2:plan_executor": {
                "registry_updates": {
                    "email_ghi789": {},
                    "email_jkl012": {},
                },
                "domain": "emails",
            },
        }

        # User asks "détail du deuxième" - last action was email search (turn 2)
        items = context_service._extract_items_from_registry(
            state=state,
            run_id="integration-test-001",
            last_action_turn=2,
            agent_results=agent_results,
        )

        # CRITICAL: Should return ONLY emails (from turn 2), not contacts
        assert len(items) == 2
        for item in items:
            assert item.get("_item_type") == "EMAIL"
            assert "contact" not in item.get("_registry_id", "").lower()

        # The 2nd item should be the 2nd EMAIL (email_jkl012)
        second_email = items[1]
        assert second_email["_registry_id"] == "email_jkl012"
        assert second_email["subject"] == "Projet X"
