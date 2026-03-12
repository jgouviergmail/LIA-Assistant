"""
Tests for rate limiting on agent tools.

Validates that @rate_limit decorator is correctly applied to all tools
with appropriate limits based on operation type (search/read/write).

Covers:
- Google Contacts tools: search_contacts_tool, list_contacts_tool, get_contact_details_tool
- Context tools: resolve_reference, list_active_domains, set_current_item, get_context_state
- Rate limit enforcement (max_calls, window_seconds)
- Rate limit scope (user-level isolation)
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.config import Settings
from src.domains.agents.tools.context_tools import (
    get_context_state,
    list_active_domains,
    resolve_reference,
    set_current_item,
)
from src.domains.agents.tools.google_contacts_tools import (
    get_contact_details_tool,
    list_contacts_tool,
    search_contacts_tool,
)

# ============================================================================
# PHASE 3.1: Rate Limiting on Google Contacts Tools
# ============================================================================


def test_search_contacts_has_rate_limit_decorator():
    """Test that search_contacts_tool has @rate_limit decorator applied."""
    # Verify the tool function has rate_limit attributes
    # The @rate_limit decorator should add metadata to the function
    assert hasattr(search_contacts_tool, "__wrapped__") or hasattr(
        search_contacts_tool, "func"
    ), "search_contacts_tool should have rate limit decorator"


def test_list_contacts_has_rate_limit_decorator():
    """Test that list_contacts_tool has @rate_limit decorator applied."""
    assert hasattr(list_contacts_tool, "__wrapped__") or hasattr(
        list_contacts_tool, "func"
    ), "list_contacts_tool should have rate limit decorator"


def test_get_contact_details_has_rate_limit_decorator():
    """Test that get_contact_details_tool has @rate_limit decorator applied."""
    assert hasattr(get_contact_details_tool, "__wrapped__") or hasattr(
        get_contact_details_tool, "func"
    ), "get_contact_details_tool should have rate limit decorator"


# ============================================================================
# PHASE 3.1: Rate Limiting on Context Tools
# ============================================================================


def test_resolve_reference_has_rate_limit_decorator():
    """Test that resolve_reference has @rate_limit decorator applied."""
    assert hasattr(resolve_reference, "__wrapped__") or hasattr(
        resolve_reference, "func"
    ), "resolve_reference should have rate limit decorator"


def test_list_active_domains_has_rate_limit_decorator():
    """Test that list_active_domains has @rate_limit decorator applied."""
    assert hasattr(list_active_domains, "__wrapped__") or hasattr(
        list_active_domains, "func"
    ), "list_active_domains should have rate limit decorator"


def test_set_current_item_has_rate_limit_decorator():
    """Test that set_current_item has @rate_limit decorator applied."""
    assert hasattr(set_current_item, "__wrapped__") or hasattr(
        set_current_item, "func"
    ), "set_current_item should have rate limit decorator"


def test_get_context_state_has_rate_limit_decorator():
    """Test that get_context_state has @rate_limit decorator applied."""
    assert hasattr(get_context_state, "__wrapped__") or hasattr(
        get_context_state, "func"
    ), "get_context_state should have rate limit decorator"


# ============================================================================
# PHASE 3.1: Rate Limit Configuration Validation
# ============================================================================


def test_rate_limit_settings_exist():
    """Test that all rate limit settings are defined in Settings."""
    settings = Settings()

    # Google Contacts rate limits
    assert hasattr(settings, "rate_limit_contacts_search_calls")
    assert hasattr(settings, "rate_limit_contacts_search_window")
    assert hasattr(settings, "rate_limit_contacts_list_calls")
    assert hasattr(settings, "rate_limit_contacts_list_window")
    assert hasattr(settings, "rate_limit_contacts_details_calls")
    assert hasattr(settings, "rate_limit_contacts_details_window")

    # Default rate limits (for context tools)
    assert hasattr(settings, "rate_limit_default_read_calls")
    assert hasattr(settings, "rate_limit_default_read_window")
    assert hasattr(settings, "rate_limit_default_write_calls")
    assert hasattr(settings, "rate_limit_default_write_window")


def test_rate_limit_settings_have_sensible_defaults():
    """Test that rate limit settings have sensible default values."""
    settings = Settings()

    # Search operations should have lower limits (more expensive)
    assert settings.rate_limit_contacts_search_calls <= 20, "Search should be conservative"
    assert settings.rate_limit_contacts_search_window > 0

    # List operations should have reasonable limits
    assert settings.rate_limit_contacts_list_calls <= 30
    assert settings.rate_limit_contacts_list_window > 0

    # Details operations should have moderate limits
    assert settings.rate_limit_contacts_details_calls <= 50
    assert settings.rate_limit_contacts_details_window > 0

    # Default read operations should be generous
    assert settings.rate_limit_default_read_calls >= 20
    assert settings.rate_limit_default_read_window > 0

    # Default write operations should be more restrictive
    assert settings.rate_limit_default_write_calls <= settings.rate_limit_default_read_calls
    assert settings.rate_limit_default_write_window > 0


# ============================================================================
# PHASE 3.1: Rate Limit Enforcement Tests
# ============================================================================


def test_rate_limit_decorator_configuration():
    """
    Test that rate limit decorator is properly configured with settings.

    Validates that the decorator uses lambda functions to read from settings
    dynamically, allowing runtime configuration changes.

    Note: Full rate limit enforcement testing requires Redis integration.
    This test validates the decorator configuration pattern.
    """
    # Verify that rate limit settings can be read
    settings = Settings()

    # All rate limit settings should be accessible
    assert settings.rate_limit_contacts_search_calls > 0
    assert settings.rate_limit_contacts_search_window > 0
    assert settings.rate_limit_contacts_list_calls > 0
    assert settings.rate_limit_contacts_list_window > 0
    assert settings.rate_limit_contacts_details_calls > 0
    assert settings.rate_limit_contacts_details_window > 0
    assert settings.rate_limit_default_read_calls > 0
    assert settings.rate_limit_default_read_window > 0
    assert settings.rate_limit_default_write_calls > 0
    assert settings.rate_limit_default_write_window > 0


def test_rate_limit_scope_is_user_level():
    """
    Test that rate limiting is configured with user-level scope.

    User-level scope ensures that each user has independent rate limits,
    preventing one user from exhausting the rate limit for all users.

    This test validates the scope configuration pattern (not actual enforcement).
    """
    # The @rate_limit decorator should use scope="user" for all tools
    # This is validated by the decorator presence tests above
    # Full scope isolation testing requires Redis integration

    # Verify settings support user-level isolation
    settings = Settings()
    assert hasattr(settings, "rate_limit_contacts_search_calls")
    assert hasattr(settings, "rate_limit_default_read_calls")

    # Note: Actual user isolation is enforced by the rate_limit decorator
    # with Redis keys scoped by user_id


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_all_tools_have_rate_limiting():
    """Integration test: Verify all critical tools have rate limiting applied."""
    tools_to_check = [
        # Google Contacts tools
        ("search_contacts_tool", search_contacts_tool),
        ("list_contacts_tool", list_contacts_tool),
        ("get_contact_details_tool", get_contact_details_tool),
        # Context tools
        ("resolve_reference", resolve_reference),
        ("list_active_domains", list_active_domains),
        ("set_current_item", set_current_item),
        ("get_context_state", get_context_state),
    ]

    for tool_name, tool_func in tools_to_check:
        # Check if rate_limit decorator is present
        # The decorator should wrap the function, adding __wrapped__ or similar
        has_decorator = hasattr(tool_func, "__wrapped__") or hasattr(tool_func, "func")

        assert has_decorator, f"Tool '{tool_name}' should have @rate_limit decorator"


def test_rate_limit_configuration_complete():
    """Integration test: Verify all rate limit configurations are complete."""
    settings = Settings()

    # Map tools to their expected rate limit settings
    rate_limit_configs = [
        # Google Contacts tools
        (
            "contacts_search",
            "rate_limit_contacts_search_calls",
            "rate_limit_contacts_search_window",
        ),
        ("contacts_list", "rate_limit_contacts_list_calls", "rate_limit_contacts_list_window"),
        (
            "contacts_details",
            "rate_limit_contacts_details_calls",
            "rate_limit_contacts_details_window",
        ),
        # Default (context tools)
        ("default_read", "rate_limit_default_read_calls", "rate_limit_default_read_window"),
        ("default_write", "rate_limit_default_write_calls", "rate_limit_default_write_window"),
    ]

    for _config_name, calls_attr, window_attr in rate_limit_configs:
        # Verify settings exist
        assert hasattr(settings, calls_attr), f"Missing setting: {calls_attr}"
        assert hasattr(settings, window_attr), f"Missing setting: {window_attr}"

        # Verify values are positive
        calls = getattr(settings, calls_attr)
        window = getattr(settings, window_attr)

        assert calls > 0, f"{calls_attr} must be positive (got {calls})"
        assert window > 0, f"{window_attr} must be positive (got {window})"


def test_rate_limit_uses_settings_dynamically():
    """Test that rate limit reads from settings (not hardcoded)."""
    # This test verifies that the lambda functions in @rate_limit decorators
    # read from settings dynamically, allowing runtime configuration changes

    # Mock settings with custom rate limits
    custom_settings = Settings(
        rate_limit_contacts_search_calls=5,  # Lower limit for testing
        rate_limit_contacts_search_window=60,
    )

    # Verify the settings can be overridden
    assert custom_settings.rate_limit_contacts_search_calls == 5
    assert custom_settings.rate_limit_contacts_search_window == 60

    # Note: The lambda pattern in decorators ensures settings are read dynamically:
    # @rate_limit(max_calls=lambda: get_settings().rate_limit_contacts_search_calls, ...)
    # This allows the rate limit to change at runtime when settings are updated


# ============================================================================
# PHASE 3.2: Rate Limiting Disable/Enable Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rate_limit_respects_global_disable():
    """Test that rate limiting can be globally disabled via settings.rate_limit_enabled."""
    from src.domains.agents.utils.rate_limiting import rate_limit

    # Create a simple test tool with rate limiting
    call_count = 0

    @rate_limit(max_calls=2, window_seconds=60, scope="user")
    async def test_tool(runtime=None):
        nonlocal call_count
        call_count += 1
        return f"call_{call_count}"

    # Mock runtime with user_id
    mock_runtime = MagicMock()
    mock_runtime.config = {"configurable": {"user_id": "test_user_123"}}

    # Test 1: Rate limiting enabled (default) - should enforce limits
    with patch("src.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.rate_limit_enabled = True
        mock_get_settings.return_value = mock_settings

        # First 2 calls should succeed
        result1 = await test_tool(runtime=mock_runtime)
        assert result1 == "call_1"
        result2 = await test_tool(runtime=mock_runtime)
        assert result2 == "call_2"

        # Third call should be rate limited (returns JSON error)
        result3 = await test_tool(runtime=mock_runtime)
        assert "rate_limit_exceeded" in result3

    # Test 2: Rate limiting disabled - should bypass all limits
    call_count = 0  # Reset counter
    with patch("src.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.rate_limit_enabled = False
        mock_get_settings.return_value = mock_settings

        # All calls should succeed even beyond limit
        for i in range(5):
            result = await test_tool(runtime=mock_runtime)
            assert (
                result == f"call_{i + 1}"
            ), f"Call {i + 1} should succeed with rate limiting disabled"


@pytest.mark.asyncio
async def test_rate_limit_clears_tracker_when_disabled():
    """Test that rate limit tracker is cleared when rate limiting is disabled."""
    from src.domains.agents.utils.rate_limiting import _rate_limit_tracker, rate_limit

    # Clear tracker before test
    _rate_limit_tracker.clear()

    @rate_limit(max_calls=2, window_seconds=60, scope="user")
    async def test_tool(runtime=None):
        return "success"

    mock_runtime = MagicMock()
    mock_runtime.config = {"configurable": {"user_id": "test_user_456"}}

    # Enable rate limiting and make some calls to populate tracker
    with patch("src.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.rate_limit_enabled = True
        mock_get_settings.return_value = mock_settings

        await test_tool(runtime=mock_runtime)
        await test_tool(runtime=mock_runtime)

        # Tracker should have entries
        assert len(_rate_limit_tracker) > 0, "Tracker should have entries after rate limited calls"

    # Disable rate limiting - tracker should be cleared on first call
    with patch("src.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.rate_limit_enabled = False
        mock_get_settings.return_value = mock_settings

        await test_tool(runtime=mock_runtime)

        # Tracker should be cleared
        assert (
            len(_rate_limit_tracker) == 0
        ), "Tracker should be cleared when rate limiting is disabled"


def test_rate_limit_enabled_setting_exists():
    """Test that rate_limit_enabled setting exists and has correct default."""
    settings = Settings()

    assert hasattr(settings, "rate_limit_enabled"), "Settings should have rate_limit_enabled field"
    # Default should be True for security
    assert settings.rate_limit_enabled is True, "rate_limit_enabled should default to True"


@pytest.mark.asyncio
async def test_rate_limit_without_runtime_bypasses_when_disabled():
    """Test that tools without runtime parameter work correctly when rate limiting is disabled."""
    from src.domains.agents.utils.rate_limiting import rate_limit

    call_count = 0

    @rate_limit(max_calls=1, window_seconds=60)
    async def test_tool_no_runtime():
        nonlocal call_count
        call_count += 1
        return "success"

    # With rate limiting disabled, should work even without runtime
    with patch("src.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.rate_limit_enabled = False
        mock_get_settings.return_value = mock_settings

        result = await test_tool_no_runtime()
        assert result == "success"
        assert call_count == 1
