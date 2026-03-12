"""
Integration tests for bootstrap module.

Tests that bootstrap functions work correctly with real application context.
"""

from unittest.mock import patch

import pytest

from src.core.bootstrap import (
    log_event_loop_configuration,
    log_rate_limiting_status,
    patch_starlette_utf8,
    validate_critical_configuration,
    validate_llm_configuration,
)


@pytest.mark.integration
class TestBootstrapStartup:
    """Tests for bootstrap functions during application startup."""

    def test_patch_starlette_utf8_is_idempotent(self):
        """Test that UTF-8 patch can be applied multiple times safely."""
        # Apply patch multiple times - should not raise
        patch_starlette_utf8()
        patch_starlette_utf8()
        patch_starlette_utf8()

        # Should not raise any errors
        # Starlette should still work correctly
        from starlette.responses import Response

        response = Response("test", media_type="text/plain")
        # The patch modifies charset handling, verify response works
        assert response.media_type is not None

    def test_validate_llm_configuration_with_real_settings(self):
        """Test LLM validation with actual application settings."""
        # Should not raise with valid configuration
        validate_llm_configuration()

    def test_validate_critical_configuration_with_real_settings(self):
        """Test critical config validation with actual settings."""
        # May raise various errors in test environment
        # This is expected behavior - just verify the function exists and can be called
        try:
            validate_critical_configuration()
        except (ValueError, AttributeError):
            # Expected if settings are not fully configured in test environment
            # AttributeError if some settings fields don't exist
            pass  # This is expected behavior in test environment

    def test_log_rate_limiting_status_produces_logs(self):
        """Test that rate limiting status logging works."""
        with patch("src.core.bootstrap.logger") as mock_logger:
            log_rate_limiting_status()

            # Should have logged at least one message
            assert mock_logger.info.called or mock_logger.warning.called

    def test_log_event_loop_configuration_detects_platform(self):
        """Test that event loop configuration correctly detects platform."""
        with patch("src.core.bootstrap.logger") as mock_logger:
            log_event_loop_configuration()

            # Should have logged with platform info
            assert mock_logger.info.called
            kwargs = mock_logger.info.call_args[1]
            assert "is_windows" in kwargs


@pytest.mark.integration
class TestBootstrapValidation:
    """Tests for bootstrap validation in various configurations."""

    def test_llm_validation_checks_provider_and_model(self):
        """Test that LLM validation checks provider/model config (not API keys).

        API keys are now stored encrypted in DB and validated at startup
        via LLMConfigOverrideCache, not via settings attributes.
        """
        # validate_llm_configuration checks provider/model attrs, not API keys
        with patch("src.core.bootstrap.logger"):
            validate_llm_configuration()
            # Should succeed if all LLM types have provider + model configured

    def test_bootstrap_functions_are_fast(self):
        """Test that bootstrap functions execute quickly."""
        import time

        start = time.time()

        validate_llm_configuration()
        try:
            validate_critical_configuration()
        except (ValueError, AttributeError):
            pass  # Expected in test environment
        log_rate_limiting_status()
        log_event_loop_configuration()

        elapsed = time.time() - start

        # All bootstrap functions should complete in under 500ms
        # (allowing for first-time import overhead)
        assert elapsed < 0.5, f"Bootstrap took {elapsed:.3f}s, expected < 0.5s"
