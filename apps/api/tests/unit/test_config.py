"""
Unit tests for application configuration.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.core.config import Settings, get_settings


@pytest.mark.unit
class TestSettings:
    """Test application settings and configuration."""

    def test_settings_from_env(self):
        """Test settings loaded from environment variables."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
            },
        ):
            settings = Settings()

            assert settings.secret_key == "test-secret-key-minimum-32-characters-long"
            assert settings.fernet_key == "test-fernet-key-32-bytes-base64=="
            assert "postgresql+asyncpg" in str(settings.database_url)
            assert "redis" in str(settings.redis_url)

    def test_settings_defaults(self):
        """Test settings default values."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                # Required LLM model fields (Phase 6 multi-provider support)
                "CONTACTS_AGENT_LLM_MODEL": "gpt-4.1-mini-mini",
                "HITL_CLASSIFIER_LLM_MODEL": "gpt-4.1-mini-mini",
                "HITL_QUESTION_GENERATOR_LLM_MODEL": "gpt-4.1-mini-mini",
                "HITL_PLAN_APPROVAL_QUESTION_LLM_MODEL": "gpt-4.1-mini-mini",
                "PLANNER_LLM_MODEL": "gpt-4.1-mini",
                "EMAILS_AGENT_LLM_MODEL": "gpt-4.1-mini-mini",
            },
            clear=True,  # Clear all existing env vars to test true defaults
        ):
            settings = Settings(_env_file=None)  # Disable .env file loading for this test

            assert settings.environment == "development"
            assert settings.debug is False
            assert settings.log_level == "INFO"
            assert settings.api_host == "0.0.0.0"
            assert settings.api_port == 8000
            assert settings.api_prefix == "/api/v1"
            assert settings.algorithm == "HS256"

    def test_settings_validation_secret_key_too_short(self):
        """Test that secret key must be at least 32 characters."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "short",  # Too short
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
            },
        ):
            with pytest.raises(ValidationError) as exc_info:
                Settings()

            assert "secret_key" in str(exc_info.value)

    def test_settings_validation_required_fields(self):
        """Test that required fields raise validation error if missing."""
        with patch.dict(os.environ, {}, clear=True):  # Clear all env vars
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)  # Disable .env file loading

            errors = exc_info.value.errors()
            error_fields = {error["loc"][0] for error in errors}

            assert "secret_key" in error_fields
            assert "fernet_key" in error_fields
            assert "database_url" in error_fields
            assert "redis_url" in error_fields

    def test_cors_origins_from_string(self):
        """Test CORS origins parsed from comma-separated string."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                "CORS_ORIGINS": "http://localhost:3000,http://localhost:3001,https://example.com",
            },
        ):
            settings = Settings()

            assert isinstance(settings.cors_origins, list)
            assert len(settings.cors_origins) == 3
            assert "http://localhost:3000" in settings.cors_origins
            assert "http://localhost:3001" in settings.cors_origins
            assert "https://example.com" in settings.cors_origins

    def test_cors_origins_from_list(self):
        """Test CORS origins from list."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
            },
        ):
            settings = Settings()
            assert isinstance(settings.cors_origins, list)

    def test_is_production_property(self):
        """Test is_production property."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                "ENVIRONMENT": "production",
            },
        ):
            settings = Settings()
            assert settings.is_production is True

        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                "ENVIRONMENT": "development",
            },
        ):
            settings = Settings()
            assert settings.is_production is False

    def test_is_development_property(self):
        """Test is_development property."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                "ENVIRONMENT": "development",
            },
        ):
            settings = Settings()
            assert settings.is_development is True

        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                "ENVIRONMENT": "production",
            },
        ):
            settings = Settings()
            assert settings.is_development is False

    def test_database_url_sync_property(self):
        """Test database_url_sync property removes asyncpg driver."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
            },
        ):
            settings = Settings()

            assert "+asyncpg" in str(settings.database_url)
            assert "+asyncpg" not in settings.database_url_sync
            assert "postgresql+psycopg://" in settings.database_url_sync

    def test_get_settings_cached(self):
        """Test get_settings returns cached instance."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
            },
        ):
            settings1 = get_settings()
            settings2 = get_settings()

            # Should be same instance (cached)
            assert settings1 is settings2

    def test_oauth_settings(self):
        """Test OAuth settings."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                "GOOGLE_CLIENT_ID": "test-google-client-id",
                "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
            },
        ):
            settings = Settings()

            assert settings.google_client_id == "test-google-client-id"
            assert settings.google_client_secret == "test-google-client-secret"
            assert settings.google_redirect_uri == "http://localhost:8000/auth/google/callback"

    def test_rate_limiting_settings(self):
        """Test rate limiting settings."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                "RATE_LIMIT_PER_MINUTE": "120",
                "RATE_LIMIT_BURST": "20",
            },
        ):
            settings = Settings()

            assert settings.rate_limit_per_minute == 120
            assert settings.rate_limit_burst == 20

    def test_telemetry_settings(self):
        """Test OpenTelemetry settings."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
                "FERNET_KEY": "test-fernet-key-32-bytes-base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://jaeger:4317",
                "OTEL_SERVICE_NAME": "lia-api-test",
            },
        ):
            settings = Settings()

            assert settings.otel_exporter_otlp_endpoint == "http://jaeger:4317"
            assert settings.otel_service_name == "lia-api-test"
