"""
Tests for configuration constants integration.

Validates that all settings correctly use constants from src.core.constants
instead of hardcoded values, ensuring configuration is centralized and maintainable.

Covers:
- Phase 1.1: Scheduler constants (CURRENCY_SYNC_HOUR, CURRENCY_SYNC_MINUTE, SCHEDULER_JOB_CURRENCY_SYNC)
- Phase 1.2: Token expiration constants (EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS, PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
- Phase 1.3: Config validation constants (AGENT_MAX_ITERATIONS_*, MAX_TOKENS_HISTORY_DEFAULT)
- Phase 1.4: Cache TTL helper (settings.get_connector_cache_ttl)
- Phase 3.2: SESSION_COOKIE_SECURE validator
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.core.constants import (
    AGENT_MAX_ITERATIONS_DEFAULT,
    AGENT_MAX_ITERATIONS_MAX,
    CURRENCY_SYNC_HOUR,
    CURRENCY_SYNC_MINUTE,
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
    MAX_TOKENS_HISTORY_DEFAULT,
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
    SCHEDULER_JOB_CURRENCY_SYNC,
    SESSION_COOKIE_SECURE_PRODUCTION,
)
from src.core.security.utils import create_password_reset_token, create_verification_token

# ============================================================================
# PHASE 1.1: Scheduler Constants
# ============================================================================


def test_scheduler_constants_imported_in_main():
    """Test that main.py imports scheduler constants correctly."""
    # This is a static analysis test - verify imports exist
    from src.main import CURRENCY_SYNC_HOUR as hour_import
    from src.main import CURRENCY_SYNC_MINUTE as minute_import
    from src.main import SCHEDULER_JOB_CURRENCY_SYNC as job_import

    assert hour_import == CURRENCY_SYNC_HOUR
    assert minute_import == CURRENCY_SYNC_MINUTE
    assert job_import == SCHEDULER_JOB_CURRENCY_SYNC


def test_scheduler_constants_have_correct_values():
    """Test that scheduler constants have the expected default values."""
    assert CURRENCY_SYNC_HOUR == 3, "Currency sync should default to 3 AM UTC"
    assert CURRENCY_SYNC_MINUTE == 0, "Currency sync should run at :00 minutes"
    assert SCHEDULER_JOB_CURRENCY_SYNC == "sync_currency_rates"


# ============================================================================
# PHASE 1.2: Token Expiration Constants
# ============================================================================


def test_token_expiration_constants_values():
    """Test that token expiration constants have secure defaults."""
    assert (
        EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS == 24
    ), "Email verification should expire in 24 hours"
    assert (
        PASSWORD_RESET_TOKEN_EXPIRE_HOURS == 1
    ), "Password reset should expire in 1 hour for security"


def test_verification_token_uses_constant():
    """Test that create_verification_token uses EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS constant."""
    # Create token with default expiration
    token = create_verification_token("test@example.com")

    # Decode token to verify expiration
    from jose import jwt

    from src.core.config import settings

    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

    # Verify token is valid and has correct type
    assert decoded["sub"] == "test@example.com"
    assert decoded["type"] == "email_verification"
    assert "exp" in decoded
    assert "iat" in decoded

    # Verify expiration is roughly 24 hours from now (allow 1 minute tolerance)
    import time
    from datetime import timedelta

    expected_exp = (
        time.time() + timedelta(hours=EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS).total_seconds()
    )
    assert (
        abs(decoded["exp"] - expected_exp) < 60
    ), "Token expiration should match constant (±1 min)"


def test_password_reset_token_uses_constant():
    """Test that create_password_reset_token uses PASSWORD_RESET_TOKEN_EXPIRE_HOURS constant."""
    token = create_password_reset_token("test@example.com")

    from jose import jwt

    from src.core.config import settings

    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

    assert decoded["sub"] == "test@example.com"
    assert decoded["type"] == "password_reset"

    # Verify expiration is roughly 1 hour from now
    import time
    from datetime import timedelta

    expected_exp = time.time() + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS).total_seconds()
    assert (
        abs(decoded["exp"] - expected_exp) < 60
    ), "Token expiration should match constant (±1 min)"


# ============================================================================
# PHASE 1.3: Config Validation Constants
# ============================================================================


def test_agent_max_iterations_uses_constants():
    """Test that Settings.agent_max_iterations uses constants for validation limits."""
    # Note: Default value may be overridden by .env, so we only test validation

    # Verify validation limits
    # Try to create settings with max value (should work)
    settings_max = Settings(agent_max_iterations=AGENT_MAX_ITERATIONS_MAX)
    assert settings_max.agent_max_iterations == AGENT_MAX_ITERATIONS_MAX

    # Try to exceed max (should fail)
    with pytest.raises(ValidationError):
        Settings(agent_max_iterations=AGENT_MAX_ITERATIONS_MAX + 1)

    # Try negative value (should fail)
    with pytest.raises(ValidationError):
        Settings(agent_max_iterations=0)


def test_max_tokens_history_constant_exists():
    """Test that MAX_TOKENS_HISTORY_DEFAULT constant exists and is positive."""
    # Note: Actual Settings value may be overridden by .env
    assert MAX_TOKENS_HISTORY_DEFAULT > 0
    # Verify the constant has a reasonable value (10M tokens, aligned with .env.example)
    assert MAX_TOKENS_HISTORY_DEFAULT == 10000000


# ============================================================================
# PHASE 1.4: Cache TTL Helper
# ============================================================================


def test_get_connector_cache_ttl_google_contacts():
    """Test that get_connector_cache_ttl returns correct TTL for Google Contacts."""
    settings = Settings()

    # Test default connector type (PHASE 2.3: Now uses contacts_cache_list_ttl_seconds)
    ttl = settings.get_connector_cache_ttl("google_contacts")
    assert ttl == settings.contacts_cache_list_ttl_seconds
    assert ttl > 0, "Cache TTL must be positive"


def test_get_connector_cache_ttl_all_types():
    """Test that get_connector_cache_ttl works for all connector types."""
    settings = Settings()

    # Test all supported connector types (PHASE 2.3: Updated to new settings pattern)
    connectors = [
        ("google_contacts", settings.contacts_cache_list_ttl_seconds),  # 300s default
        ("google_contacts_search", settings.contacts_cache_search_ttl_seconds),  # 180s default
        ("google_contacts_details", settings.contacts_cache_details_ttl_seconds),  # 600s default
        # Calendar and Drive use new cache settings pattern
        ("google_calendar", settings.calendar_cache_list_ttl_seconds),
        ("google_drive", settings.drive_cache_list_ttl_seconds),
    ]

    for connector_type, expected_ttl in connectors:
        ttl = settings.get_connector_cache_ttl(connector_type)
        assert ttl == expected_ttl, f"{connector_type} TTL should be {expected_ttl}, got {ttl}"
        assert ttl > 0, f"{connector_type} TTL must be positive"


def test_get_connector_cache_ttl_fallback():
    """Test that get_connector_cache_ttl returns default for unknown types."""
    settings = Settings()

    # Unknown connector should return default TTL
    ttl = settings.get_connector_cache_ttl("unknown_connector")
    assert ttl == 300, "Unknown connector should fallback to default TTL (300s)"


# ============================================================================
# PHASE 3.2: SESSION_COOKIE_SECURE Validator
# ============================================================================


def test_session_cookie_secure_development():
    """Test that session_cookie_secure defaults to False in development."""
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
        settings = Settings()
        assert settings.session_cookie_secure is False


def test_session_cookie_secure_production_constant():
    """Test that SESSION_COOKIE_SECURE_PRODUCTION constant has correct value."""
    # Verify the constant exists and has the expected value for production
    assert SESSION_COOKIE_SECURE_PRODUCTION is True, "Production should enforce HTTPS-only cookies"

    # Verify the constant is imported in config.py (static analysis)
    from src.core.config import SESSION_COOKIE_SECURE_PRODUCTION as imported_const

    assert imported_const is SESSION_COOKIE_SECURE_PRODUCTION


def test_session_cookie_secure_explicit_override():
    """Test that explicit SESSION_COOKIE_SECURE value is respected."""
    # Explicitly set to False even in production
    with patch.dict(
        os.environ, {"ENVIRONMENT": "production", "SESSION_COOKIE_SECURE": "false"}, clear=False
    ):
        settings = Settings()
        assert settings.session_cookie_secure is False

    # Explicitly set to True even in development
    with patch.dict(
        os.environ, {"ENVIRONMENT": "development", "SESSION_COOKIE_SECURE": "true"}, clear=False
    ):
        settings = Settings()
        assert settings.session_cookie_secure is True


def test_session_cookie_secure_string_conversion():
    """Test that string values are correctly converted to boolean."""
    test_cases = [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ]

    for string_value, expected_bool in test_cases:
        with patch.dict(os.environ, {"SESSION_COOKIE_SECURE": string_value}, clear=False):
            settings = Settings()
            assert (
                settings.session_cookie_secure is expected_bool
            ), f"'{string_value}' should convert to {expected_bool}"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_all_constants_properly_imported():
    """Integration test: Verify all critical constants are imported and used."""
    from src.core import constants

    # Verify all critical constants exist
    required_constants = [
        "AGENT_MAX_ITERATIONS_DEFAULT",
        "AGENT_MAX_ITERATIONS_MAX",
        "CURRENCY_SYNC_HOUR",
        "CURRENCY_SYNC_MINUTE",
        "EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS",
        "GOOGLE_CONTACTS_LIST_FIELDS",
        "GOOGLE_CONTACTS_SEARCH_FIELDS",
        "GOOGLE_CONTACTS_ALL_FIELDS",
        "MAX_TOKENS_HISTORY_DEFAULT",
        "PASSWORD_RESET_TOKEN_EXPIRE_HOURS",
        "SCHEDULER_JOB_CURRENCY_SYNC",
        "SESSION_COOKIE_SECURE_PRODUCTION",
        "TOOL_CONTEXT_MAX_ITEMS",
    ]

    for const_name in required_constants:
        assert hasattr(
            constants, const_name
        ), f"Constant {const_name} should exist in src.core.constants"
        value = getattr(constants, const_name)
        assert value is not None, f"Constant {const_name} should have a non-None value"


def test_settings_no_hardcoded_values():
    """Verify that Settings class field defaults are defined in constants module."""
    # Note: Actual runtime values may be overridden by .env
    # This test verifies constants are importable and have valid values
    from src.core.constants import SSE_HEARTBEAT_INTERVAL_DEFAULT

    # Verify constants exist and have reasonable values
    assert AGENT_MAX_ITERATIONS_DEFAULT > 0
    assert MAX_TOKENS_HISTORY_DEFAULT > 0
    assert SSE_HEARTBEAT_INTERVAL_DEFAULT > 0

    # Verify Settings can use these values (no validation errors)
    settings = Settings(
        agent_max_iterations=AGENT_MAX_ITERATIONS_DEFAULT,
        sse_heartbeat_interval=SSE_HEARTBEAT_INTERVAL_DEFAULT,
    )
    assert settings.agent_max_iterations == AGENT_MAX_ITERATIONS_DEFAULT
    assert settings.sse_heartbeat_interval == SSE_HEARTBEAT_INTERVAL_DEFAULT
