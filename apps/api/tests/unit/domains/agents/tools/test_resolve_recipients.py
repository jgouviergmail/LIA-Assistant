"""
Unit tests for resolve_recipients_to_emails() comma-separated name resolution.

Tests coverage:
- Single name resolved correctly
- Multiple comma-separated names resolved individually
- Already valid emails pass through unchanged
- Mixed emails and names handled correctly
- Empty/None input returns None
- Partial resolution failure keeps original name

Target: resolve_recipients_to_emails in
    domains/agents/tools/runtime_helpers.py
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.tools.runtime_helpers import resolve_recipients_to_emails

# =============================================================================
# Fixtures
# =============================================================================


def _mock_runtime() -> MagicMock:
    """Create a mock ToolRuntime."""
    runtime = MagicMock()
    runtime.config = {
        "configurable": {
            "__deps": MagicMock(),
            "user_id": "test-user-uuid",
        }
    }
    return runtime


# =============================================================================
# Tests: String input (email tools)
# =============================================================================


class TestStringInputResolution:
    """Test comma-separated string input for email tools (to, cc, bcc)."""

    @pytest.mark.asyncio
    async def test_single_name_resolved(self) -> None:
        """Single name should be resolved to 'Name <email>' format."""
        runtime = _mock_runtime()

        with patch(
            "src.domains.agents.tools.runtime_helpers.resolve_contact_to_email",
            new_callable=AsyncMock,
            return_value="jane.smith@example.com",
        ):
            result = await resolve_recipients_to_emails(runtime, "Jane Smith", "to")

        assert result == "Jane Smith <jane.smith@example.com>"

    @pytest.mark.asyncio
    async def test_two_names_resolved_individually(self) -> None:
        """Two comma-separated names should be resolved individually."""
        runtime = _mock_runtime()

        async def mock_resolve(_runtime, name):
            mapping = {
                "Jane Smith": "jane.smith@example.com",
                "John Smith": "john.smith@example.com",
            }
            return mapping.get(name)

        with patch(
            "src.domains.agents.tools.runtime_helpers.resolve_contact_to_email",
            side_effect=mock_resolve,
        ):
            result = await resolve_recipients_to_emails(runtime, "Jane Smith, John Smith", "to")

        assert result == "Jane Smith <jane.smith@example.com>, John Smith <john.smith@example.com>"

    @pytest.mark.asyncio
    async def test_three_names_resolved_individually(self) -> None:
        """Three comma-separated names should all be resolved."""
        runtime = _mock_runtime()

        async def mock_resolve(_runtime, name):
            mapping = {
                "Alice": "alice@example.com",
                "Bob": "bob@example.com",
                "Charlie": "charlie@example.com",
            }
            return mapping.get(name)

        with patch(
            "src.domains.agents.tools.runtime_helpers.resolve_contact_to_email",
            side_effect=mock_resolve,
        ):
            result = await resolve_recipients_to_emails(runtime, "Alice, Bob, Charlie", "to")

        assert "Alice <alice@example.com>" in result
        assert "Bob <bob@example.com>" in result
        assert "Charlie <charlie@example.com>" in result

    @pytest.mark.asyncio
    async def test_valid_email_passes_through(self) -> None:
        """Already valid email should pass through without resolution."""
        runtime = _mock_runtime()

        result = await resolve_recipients_to_emails(runtime, "user@example.com", "to")

        assert result == "user@example.com"

    @pytest.mark.asyncio
    async def test_multiple_valid_emails_pass_through(self) -> None:
        """Multiple valid emails should pass through."""
        runtime = _mock_runtime()

        result = await resolve_recipients_to_emails(
            runtime, "user1@example.com, user2@example.com", "to"
        )

        assert result == "user1@example.com, user2@example.com"

    @pytest.mark.asyncio
    async def test_partial_resolution_keeps_original(self) -> None:
        """Unresolved names should be kept as-is."""
        runtime = _mock_runtime()

        async def mock_resolve(_runtime, name):
            if name == "Jane Smith":
                return "jane.smith@example.com"
            return None  # Second name not found

        with patch(
            "src.domains.agents.tools.runtime_helpers.resolve_contact_to_email",
            side_effect=mock_resolve,
        ):
            result = await resolve_recipients_to_emails(runtime, "Jane Smith, Unknown Person", "to")

        assert "Jane Smith <jane.smith@example.com>" in result
        assert "Unknown Person" in result

    @pytest.mark.asyncio
    async def test_none_input_returns_none(self) -> None:
        """None input should return None."""
        runtime = _mock_runtime()
        result = await resolve_recipients_to_emails(runtime, None, "to")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_string_returns_none(self) -> None:
        """Empty string should return None."""
        runtime = _mock_runtime()
        result = await resolve_recipients_to_emails(runtime, "", "to")
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_in_names_stripped(self) -> None:
        """Whitespace around names should be stripped before resolution."""
        runtime = _mock_runtime()

        resolve_calls = []

        async def mock_resolve(_runtime, name):
            resolve_calls.append(name)
            return f"{name.replace(' ', '')}@example.com"

        with patch(
            "src.domains.agents.tools.runtime_helpers.resolve_contact_to_email",
            side_effect=mock_resolve,
        ):
            await resolve_recipients_to_emails(runtime, "  Alice  ,  Bob  ", "to")

        # Names should be stripped before resolution
        assert resolve_calls == ["Alice", "Bob"]


# =============================================================================
# Tests: List input (calendar tools)
# =============================================================================


class TestListInputResolution:
    """Test list input for calendar tools (attendees) - unchanged behavior."""

    @pytest.mark.asyncio
    async def test_list_resolves_each_item(self) -> None:
        """List input should resolve each name individually (existing behavior)."""
        runtime = _mock_runtime()

        async def mock_resolve(_runtime, name):
            return f"{name.lower().replace(' ', '')}@example.com"

        with patch(
            "src.domains.agents.tools.runtime_helpers.resolve_contact_to_email",
            side_effect=mock_resolve,
        ):
            result = await resolve_recipients_to_emails(runtime, ["Alice", "Bob"], "attendees")

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_valid_emails_pass_through(self) -> None:
        """Valid emails in list should pass through without resolution."""
        runtime = _mock_runtime()

        result = await resolve_recipients_to_emails(
            runtime, ["user@example.com", "other@example.com"], "attendees"
        )

        assert result == ["user@example.com", "other@example.com"]


# =============================================================================
# Tests: No runtime
# =============================================================================


class TestNoRuntime:
    """Test behavior without runtime (can't resolve)."""

    @pytest.mark.asyncio
    async def test_no_runtime_returns_original(self) -> None:
        """Without runtime, should return original recipients."""
        result = await resolve_recipients_to_emails(None, "Jane Smith, John Smith", "to")
        assert result == "Jane Smith, John Smith"
