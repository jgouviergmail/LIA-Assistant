"""
Tests for Response Node Security Fixes (2025-12-19).

Validates critical security corrections:
- P0.2/1.3: Bounded recursion (_extract_array_counts)
- P1.2/2.1: XSS prevention (photo URL whitelist)
- P0.3/2.3: Anti-hallucination (message filtering for rejections)
- P1.1/2.2: Registry filtering strict turn_type
- C1/1.1: O(1) indexed lookup for registry
"""

from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.constants import (
    TURN_TYPE_ACTION,
    TURN_TYPE_REFERENCE,
)
from src.domains.agents.nodes.response_node import (
    _filter_messages_for_rejection_context,
    _is_safe_photo_url,
)
from src.domains.agents.utils.registry_filtering import (
    build_registry_payload_index,
    filter_registry_by_current_turn,
)

# ============================================================================
# Tests: _is_safe_photo_url (XSS Prevention - Phase 2.1)
# ============================================================================


class TestIsSafePhotoUrl:
    """Tests for photo URL whitelist validation."""

    def test_blocks_javascript_scheme(self):
        """2.1: Block javascript: URLs (XSS vector)."""
        assert not _is_safe_photo_url("javascript:alert(1)")
        assert not _is_safe_photo_url("javascript:void(0)")

    def test_blocks_data_scheme(self):
        """2.1: Block data: URLs (XSS vector)."""
        assert not _is_safe_photo_url("data:text/html,<script>alert(1)</script>")
        assert not _is_safe_photo_url("data:image/svg+xml,<svg onload='alert(1)'/>")

    def test_blocks_vbscript_scheme(self):
        """2.1: Block vbscript: URLs (XSS vector)."""
        assert not _is_safe_photo_url("vbscript:msgbox(1)")

    def test_allows_google_domains(self):
        """2.1: Allow trusted Google domains."""
        assert _is_safe_photo_url("https://lh3.googleusercontent.com/photo123")
        assert _is_safe_photo_url("https://maps.googleapis.com/maps/api/place/photo")
        assert _is_safe_photo_url("https://places.googleapis.com/v1/places/photo")

    def test_allows_internal_api_paths(self):
        """2.1: Allow internal API proxy paths."""
        assert _is_safe_photo_url("/api/v1/connectors/google-places/photo/abc123")
        assert _is_safe_photo_url("/api/v1/connectors/google-drive/thumbnail/xyz")
        assert _is_safe_photo_url("/api/v1/connectors/test/image")

    def test_blocks_external_domains(self):
        """2.1: Block untrusted external domains."""
        assert not _is_safe_photo_url("https://evil.com/malicious.jpg")
        assert not _is_safe_photo_url("https://attacker.io/xss.svg")
        assert not _is_safe_photo_url("http://192.168.1.1/internal.jpg")

    def test_handles_none_and_empty(self):
        """2.1: Handle None and empty URLs safely."""
        assert not _is_safe_photo_url(None)
        assert not _is_safe_photo_url("")

    def test_blocks_relative_paths_not_starting_with_slash(self):
        """2.1: Block relative paths that don't start with /."""
        assert not _is_safe_photo_url("../../../etc/passwd")
        assert not _is_safe_photo_url("path/to/file")

    def test_allows_localhost_for_development(self):
        """2.1: Allow localhost for development."""
        assert _is_safe_photo_url("http://localhost/image.jpg")
        assert _is_safe_photo_url("http://127.0.0.1/image.jpg")


# ============================================================================
# Tests: _filter_messages_for_rejection_context (Anti-Hallucination - Phase 2.3)
# ============================================================================


class TestFilterMessagesForRejectionContext:
    """Tests for message filtering to prevent LLM hallucination on plan rejection."""

    def test_no_filter_when_no_rejection(self):
        """2.3: Return original messages when no rejection."""
        messages = [
            HumanMessage(content="Cherche mes contacts"),
            AIMessage(content="Voici 5 contacts trouvés: ..."),
        ]
        result = _filter_messages_for_rejection_context(messages, has_rejection=False)
        assert len(result) == 2

    def test_keeps_human_messages(self):
        """2.3: Always keep HumanMessage (user input)."""
        messages = [
            HumanMessage(content="Cherche mes contacts"),
            AIMessage(content="Voici 5 contacts trouvés: Jean, Pierre"),
            HumanMessage(content="Non annule"),
        ]
        result = _filter_messages_for_rejection_context(messages, has_rejection=True)
        # Should keep both HumanMessages
        human_msgs = [m for m in result if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 2

    def test_filters_ai_messages_with_results(self):
        """2.3: Filter AIMessage containing result data patterns."""
        messages = [
            HumanMessage(content="Cherche mes contacts"),
            AIMessage(content="Voici les résultats de votre recherche: ..."),
            HumanMessage(content="Non annule"),
        ]
        result = _filter_messages_for_rejection_context(messages, has_rejection=True)
        # AIMessage with "résultats" should be filtered
        ai_msgs = [m for m in result if isinstance(m, AIMessage)]
        assert len(ai_msgs) == 0

    def test_keeps_conversational_ai_messages(self):
        """2.3: Keep AIMessage that are conversational (no results)."""
        messages = [
            HumanMessage(content="Bonjour"),
            AIMessage(content="Bonjour! Comment puis-je vous aider?"),
            HumanMessage(content="Cherche mes contacts"),
        ]
        result = _filter_messages_for_rejection_context(messages, has_rejection=True)
        # Conversational AIMessage should be kept
        ai_msgs = [m for m in result if isinstance(m, AIMessage)]
        assert len(ai_msgs) == 1

    def test_filters_json_blocks(self):
        """2.3: Filter messages containing JSON code blocks."""
        messages = [
            HumanMessage(content="Cherche"),
            AIMessage(content='```json\n{"contacts": [...]}\n```'),
        ]
        result = _filter_messages_for_rejection_context(messages, has_rejection=True)
        ai_msgs = [m for m in result if isinstance(m, AIMessage)]
        assert len(ai_msgs) == 0


# ============================================================================
# Tests: build_registry_payload_index (O(1) Lookup - Phase 1.1)
# ============================================================================


class TestBuildRegistryPayloadIndex:
    """Tests for registry payload indexing (O(1) lookup optimization)."""

    def test_indexes_by_id(self):
        """1.1: Build index from payload.id to registry key."""
        registry = {
            "reg_123": {"payload": {"id": "place_abc", "name": "Restaurant"}},
            "reg_456": {"payload": {"id": "place_xyz", "name": "Cafe"}},
        }
        index = build_registry_payload_index(registry)
        assert index["place_abc"] == "reg_123"
        assert index["place_xyz"] == "reg_456"

    def test_indexes_by_resourceName(self):
        """1.1: Build index from payload.resourceName to registry key (contacts)."""
        registry = {
            "reg_123": {"payload": {"resourceName": "people/abc", "name": "Jean"}},
        }
        index = build_registry_payload_index(registry)
        assert index["people/abc"] == "reg_123"

    def test_handles_empty_registry(self):
        """1.1: Handle empty registry gracefully."""
        index = build_registry_payload_index({})
        assert index == {}

    def test_handles_missing_payload(self):
        """1.1: Handle items without payload."""
        registry = {
            "reg_123": {"type": "PLACE"},  # No payload
        }
        index = build_registry_payload_index(registry)
        assert index == {}


# ============================================================================
# Tests: filter_registry_by_current_turn (Strict Turn Type - Phase 2.2)
# ============================================================================


class TestFilterRegistryByCurrentTurnTurnType:
    """Tests for strict turn_type filtering (data leak prevention)."""

    def test_reference_turn_returns_empty_on_no_match(self):
        """2.2: REFERENCE turn returns {} if no match (prevents data leak)."""
        agent_results = {"1:planner": {"status": "success"}}  # No registry_updates
        registry = {"item_1": {"payload": {"id": "abc"}}}

        result = filter_registry_by_current_turn(
            agent_results=agent_results,
            current_turn_id=2,  # Different turn
            data_registry=registry,
            resolved_context=None,
            turn_type=TURN_TYPE_REFERENCE,  # Use constant (lowercase "reference")
        )
        # Should return empty dict for REFERENCE with no match
        assert result == {}

    def test_action_turn_returns_full_registry_on_no_match(self):
        """2.2: ACTION turn returns full registry if no match (backward compatible)."""
        agent_results = {"1:planner": {"status": "success"}}
        registry = {"item_1": {"payload": {"id": "abc"}}}

        result = filter_registry_by_current_turn(
            agent_results=agent_results,
            current_turn_id=2,
            data_registry=registry,
            resolved_context=None,
            turn_type=TURN_TYPE_ACTION,  # Use constant (lowercase "action")
        )
        # Should return full registry for ACTION (backward compatible)
        assert result == registry

    def test_filters_by_registry_updates(self):
        """2.2: Filter by registry_updates when available."""
        agent_results = {"1:planner": {"registry_updates": {"item_a": {"data": "test"}}}}
        registry = {
            "item_a": {"payload": {"id": "a"}},
            "item_b": {"payload": {"id": "b"}},
        }

        result = filter_registry_by_current_turn(
            agent_results=agent_results,
            current_turn_id=1,
            data_registry=registry,
            resolved_context=None,
            turn_type="ACTION",
        )
        assert "item_a" in result
        assert "item_b" not in result
