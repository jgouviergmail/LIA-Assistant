"""
Unit tests for bootstrap module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Created: 2025-11-20
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


class TestPatchStarletteUtf8:
    def test_patch_applies_successfully(self):
        patch_starlette_utf8()
        from starlette.config import Config

        assert hasattr(Config, "_read_file")
        assert callable(Config._read_file)

    def test_patched_read_file_with_none_filename(self):
        """Test _read_file_utf8 returns empty dict when filename is None (Line 44)."""
        patch_starlette_utf8()
        from starlette.config import Config

        config = Config()
        # Call _read_file with None
        result = config._read_file(None)

        # Line 44 executed: return {}
        assert result == {}

    def test_patched_read_file_handles_file_not_found(self, tmp_path):
        """Test _read_file_utf8 handles FileNotFoundError (Lines 64-65)."""
        patch_starlette_utf8()
        from starlette.config import Config

        config = Config()
        # Call _read_file with non-existent file
        non_existent = str(tmp_path / "does_not_exist.env")
        result = config._read_file(non_existent)

        # Lines 64-65 executed: except FileNotFoundError: return {}
        assert result == {}


class TestValidateLLMConfiguration:
    def test_valid_configuration_passes(self):
        """LLM_DEFAULTS contains all critical types — validation passes."""
        validate_llm_configuration()

    def test_missing_critical_type_raises_error(self):
        """Validation raises ValueError if a critical type is missing from LLM_DEFAULTS."""
        from src.domains.llm_config.constants import LLM_DEFAULTS

        # Keep only "router" — missing response, planner, contacts_agent, etc.
        incomplete_defaults = {"router": LLM_DEFAULTS["router"]}
        with patch("src.domains.llm_config.constants.LLM_DEFAULTS", incomplete_defaults):
            with pytest.raises(ValueError, match="Missing LLM_DEFAULTS"):
                validate_llm_configuration()


class TestValidateCriticalConfiguration:
    def test_valid_configuration_passes(self):
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.database_url = "postgresql://localhost/test"
            mock_settings.redis_url = "redis://localhost:6379"
            mock_settings.secret_key = "secure-secret-key-minimum-32-chars"
            mock_settings.fernet_key = "valid-fernet-key"
            mock_settings.google_client_id = "client-id"
            mock_settings.google_client_secret = "client-secret"
            validate_critical_configuration()

    def test_missing_database_url_raises_error(self):
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.database_url = None
            mock_settings.redis_url = "redis://localhost:6379"
            mock_settings.secret_key = "secure-key"
            mock_settings.fernet_key = "fernet-key"
            mock_settings.google_client_id = ""
            mock_settings.google_client_secret = ""
            with pytest.raises(ValueError) as exc_info:
                validate_critical_configuration()
            assert "DATABASE_URL" in str(exc_info.value)

    def test_missing_redis_url_raises_error(self):
        """Test missing Redis URL raises ValueError (Line 150)."""
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.database_url = "postgresql://localhost/test"
            mock_settings.redis_url = None  # Missing Redis URL
            mock_settings.secret_key = "secure-key"
            mock_settings.fernet_key = "fernet-key"
            mock_settings.google_client_id = ""
            mock_settings.google_client_secret = ""

            # Line 150 executed: missing_configs.append("REDIS_URL")
            with pytest.raises(ValueError) as exc_info:
                validate_critical_configuration()
            assert "REDIS_URL" in str(exc_info.value)

    def test_insecure_secret_key_raises_error(self):
        """Test insecure SECRET_KEY raises ValueError (Line 154)."""
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.database_url = "postgresql://localhost/test"
            mock_settings.redis_url = "redis://localhost:6379"
            mock_settings.secret_key = "change-me-in-production"  # Insecure default
            mock_settings.fernet_key = "fernet-key"
            mock_settings.google_client_id = ""
            mock_settings.google_client_secret = ""

            # Line 154 executed: missing_configs.append("SECRET_KEY (must be set to a secure value)")
            with pytest.raises(ValueError) as exc_info:
                validate_critical_configuration()
            assert "SECRET_KEY" in str(exc_info.value)

    def test_missing_fernet_key_raises_error(self):
        """Test missing FERNET_KEY raises ValueError (Line 157)."""
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.database_url = "postgresql://localhost/test"
            mock_settings.redis_url = "redis://localhost:6379"
            mock_settings.secret_key = "secure-key"
            mock_settings.fernet_key = None  # Missing Fernet key
            mock_settings.google_client_id = ""
            mock_settings.google_client_secret = ""

            # Line 157 executed: missing_configs.append("FERNET_KEY")
            with pytest.raises(ValueError) as exc_info:
                validate_critical_configuration()
            assert "FERNET_KEY" in str(exc_info.value)

    def test_partial_oauth_client_id_missing_raises_error(self):
        """Test partial OAuth config (missing client_id) raises ValueError (Lines 165-166)."""
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.database_url = "postgresql://localhost/test"
            mock_settings.redis_url = "redis://localhost:6379"
            mock_settings.secret_key = "secure-key"
            mock_settings.fernet_key = "fernet-key"
            mock_settings.google_client_id = ""  # Missing
            mock_settings.google_client_secret = "secret"  # Present

            # Lines 165-166 executed: missing_configs.append("GOOGLE_CLIENT_ID")
            with pytest.raises(ValueError) as exc_info:
                validate_critical_configuration()
            assert "GOOGLE_CLIENT_ID" in str(exc_info.value)

    def test_partial_oauth_client_secret_missing_raises_error(self):
        """Test partial OAuth config (missing client_secret) raises ValueError (Lines 167-168)."""
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.database_url = "postgresql://localhost/test"
            mock_settings.redis_url = "redis://localhost:6379"
            mock_settings.secret_key = "secure-key"
            mock_settings.fernet_key = "fernet-key"
            mock_settings.google_client_id = "client-id"  # Present
            mock_settings.google_client_secret = ""  # Missing

            # Lines 167-168 executed: missing_configs.append("GOOGLE_CLIENT_SECRET")
            with pytest.raises(ValueError) as exc_info:
                validate_critical_configuration()
            assert "GOOGLE_CLIENT_SECRET" in str(exc_info.value)


class TestLogRateLimitingStatus:
    def test_logs_enabled_status(self, caplog):
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.rate_limit_enabled = True
            mock_settings.rate_limit_per_minute = 60
            mock_settings.rate_limit_burst = 10
            with caplog.at_level("INFO"):
                log_rate_limiting_status()
            assert any("rate_limiting_enabled" in record.message for record in caplog.records)

    def test_logs_disabled_status(self, caplog):
        """Test rate limiting disabled logs warning (Line 198)."""
        with patch("src.core.bootstrap.settings") as mock_settings:
            mock_settings.rate_limit_enabled = False

            # Line 198 executed: logger.warning("rate_limiting_disabled")
            with caplog.at_level("WARNING"):
                log_rate_limiting_status()
            assert any("rate_limiting_disabled" in record.message for record in caplog.records)


class TestLogEventLoopConfiguration:
    def test_logs_event_loop_info(self, caplog):
        with caplog.at_level("INFO"):
            log_event_loop_configuration()
        assert any("event_loop_configured" in record.message for record in caplog.records)

    def test_logs_event_loop_with_runtime_error(self, caplog):
        """Test event loop logging handles RuntimeError (Line 217-220)."""
        import asyncio

        # Mock get_running_loop to raise RuntimeError (no running loop)
        original_get_running_loop = asyncio.get_running_loop

        def mock_get_running_loop():
            raise RuntimeError("no running event loop")

        asyncio.get_running_loop = mock_get_running_loop

        try:
            # Line 217-220 executed: except RuntimeError: loop_type = "NotRunning"
            with caplog.at_level("INFO"):
                log_event_loop_configuration()

            # Verify log contains "NotRunning" as loop_type
            assert any("event_loop_configured" in record.message for record in caplog.records)
            # Check that "NotRunning" is in the logged data
            log_messages = [record.message for record in caplog.records]
            assert any("NotRunning" in msg for msg in log_messages)
        finally:
            # Restore original function
            asyncio.get_running_loop = original_get_running_loop
