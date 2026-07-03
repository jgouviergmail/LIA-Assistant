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


# Current rate-limit vocabulary: category-based defaults (read/write/expensive)
# consumed by RATE_LIMIT_CATEGORIES in tools/decorators.py. The historical
# per-tool settings (rate_limit_contacts_*) were removed with that migration.
RATE_LIMIT_SETTING_NAMES = [
    "rate_limit_default_read_calls",
    "rate_limit_default_read_window",
    "rate_limit_default_write_calls",
    "rate_limit_default_write_window",
    "rate_limit_default_expensive_calls",
    "rate_limit_default_expensive_window",
]


def test_rate_limit_settings_exist():
    """Test that all category rate limit settings are defined in Settings."""
    for name in RATE_LIMIT_SETTING_NAMES:
        assert name in Settings.model_fields, f"Missing setting: {name}"


def test_rate_limit_settings_have_sensible_defaults():
    """Field DEFAULTS keep the read >= write >= expensive ordering.

    Asserted on Settings.model_fields (not an instance) so the test does not
    depend on the ambient environment (.env.test overrides values on purpose).
    """
    defaults = {name: Settings.model_fields[name].default for name in RATE_LIMIT_SETTING_NAMES}

    for name, value in defaults.items():
        assert value > 0, f"{name} default must be positive (got {value})"

    # Write operations are more restrictive than reads; expensive even more so
    assert defaults["rate_limit_default_write_calls"] <= defaults["rate_limit_default_read_calls"]
    assert (
        defaults["rate_limit_default_expensive_calls"] <= defaults["rate_limit_default_write_calls"]
    )


# ============================================================================
# PHASE 3.1: Rate Limit Enforcement Tests
# ============================================================================


def test_rate_limit_decorator_configuration():
    """RATE_LIMIT_CATEGORIES wires every category to live settings lambdas.

    The lambdas read from get_settings() at call time, allowing runtime
    configuration changes without redeploying decorated tools.
    """
    from src.domains.agents.tools.decorators import RATE_LIMIT_CATEGORIES

    assert set(RATE_LIMIT_CATEGORIES) == {"read", "write", "expensive"}

    for category, config in RATE_LIMIT_CATEGORIES.items():
        max_calls = config["max_calls"]()
        window_seconds = config["window_seconds"]()
        assert max_calls > 0, f"{category}: max_calls must be positive"
        assert window_seconds > 0, f"{category}: window_seconds must be positive"


def test_rate_limit_scope_is_user_level():
    """connector_tool applies user-level scope by default.

    User-level scope ensures each user has independent rate limits,
    preventing one user from exhausting the limit for everyone.
    """
    import inspect

    from src.domains.agents.tools.decorators import connector_tool

    signature = inspect.signature(connector_tool)
    assert signature.parameters["rate_limit_scope"].default == "user"


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
    """Integration test: every category setting exists with a positive value."""
    settings = Settings()

    for name in RATE_LIMIT_SETTING_NAMES:
        value = getattr(settings, name)
        assert value > 0, f"{name} must be positive (got {value})"


def test_rate_limit_uses_settings_dynamically():
    """Test that rate limit values can be overridden (not hardcoded)."""
    custom_settings = Settings(
        rate_limit_default_read_calls=5,  # Lower limit for testing
        rate_limit_default_read_window=60,
    )

    assert custom_settings.rate_limit_default_read_calls == 5
    assert custom_settings.rate_limit_default_read_window == 60

    # The lambda pattern in RATE_LIMIT_CATEGORIES ensures settings are read
    # dynamically at call time (covered by test_rate_limit_decorator_configuration)


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
    """Test that rate_limit_enabled setting exists and has correct default.

    Checked on the FIELD default (not an instance): .env.test deliberately
    sets RATE_LIMIT_ENABLED=false for the test environment, and an instance
    would absorb it.
    """
    assert "rate_limit_enabled" in Settings.model_fields
    # Default should be True for security
    assert Settings.model_fields["rate_limit_enabled"].default is True


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
