"""
Unit tests for LLM configuration (Settings validation).

The OpenAIProvider classes that used to live here exercised a module no
production path called (ADR-220 Lot 5): 259 lines of dead code whose tests
simulated coverage. Live override merging is covered by test_factory.py.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.core.config import Settings

#: Structurally valid synthetic key (32 bytes, URL-safe base64) — the
#: Settings validator now enforces the real Fernet shape (install contract).
TEST_FERNET_KEY = "dW5pdC10ZXN0LWZlcm5ldC1rZXktMDEyMzQ1Njc4OWE="


class TestSettingsLLMDefaults:
    """Test default values for LLM configuration in Settings."""

    def test_response_llm_defaults(self):
        """Test response LLM has correct default values from config.py.

        Note: This test verifies config.py defaults match expected values.
        We explicitly set the values to match config.py defaults to ensure
        environment variables from .env don't interfere.
        """
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "OPENAI_API_KEY": "sk-test-key",
                # Response config - explicitly set to config.py defaults
                "RESPONSE_LLM_MODEL": "gpt-4.1-mini",
                "RESPONSE_LLM_TEMPERATURE": "0.5",  # config.py default
                "RESPONSE_LLM_TOP_P": "0.95",  # config.py default
                "RESPONSE_LLM_FREQUENCY_PENALTY": "0.5",  # config.py default
                "RESPONSE_LLM_PRESENCE_PENALTY": "0.3",  # config.py default
                "RESPONSE_LLM_MAX_TOKENS": "10000",  # config.py default
                # Required LLM models (Phase 3 HITL additions)
                "HITL_CLASSIFIER_LLM_MODEL": "gpt-4.1-mini",
                "HITL_QUESTION_GENERATOR_LLM_MODEL": "gpt-4.1-mini",
                "HITL_PLAN_APPROVAL_QUESTION_LLM_MODEL": "gpt-4.1-mini",
                "PLANNER_LLM_MODEL": "gpt-4.1-mini",
                "SEMANTIC_VALIDATOR_LLM_MODEL": "gpt-4.1-mini",
            },
            clear=False,  # Preserve system env vars to avoid import issues
        ):
            settings = Settings(_env_file=None)  # Disable .env loading for clean test

            # Verify response defaults (config.py values)
            assert settings.response_llm_model == "gpt-4.1-mini"
            assert settings.response_llm_temperature == 0.5
            assert settings.response_llm_top_p == 0.95
            assert settings.response_llm_frequency_penalty == 0.5
            assert settings.response_llm_presence_penalty == 0.3
            assert settings.response_llm_max_tokens == 10000


class TestSettingsLLMValidation:
    """Test Pydantic validation for LLM configuration."""

    def test_temperature_validation_min(self):
        """Test temperature cannot be less than 0.0."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "RESPONSE_LLM_TEMPERATURE": "-0.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_temperature_validation_max(self):
        """Test temperature cannot exceed 2.0."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "RESPONSE_LLM_TEMPERATURE": "2.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_top_p_validation_min(self):
        """Test top_p cannot be less than 0.0."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "RESPONSE_LLM_TOP_P": "-0.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_top_p_validation_max(self):
        """Test top_p cannot exceed 1.0."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "RESPONSE_LLM_TOP_P": "1.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_frequency_penalty_validation_min(self):
        """Test frequency_penalty cannot be less than -2.0."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "RESPONSE_LLM_FREQUENCY_PENALTY": "-2.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_frequency_penalty_validation_max(self):
        """Test frequency_penalty cannot exceed 2.0."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "RESPONSE_LLM_FREQUENCY_PENALTY": "2.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_presence_penalty_validation_min(self):
        """Test presence_penalty cannot be less than -2.0."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "RESPONSE_LLM_PRESENCE_PENALTY": "-2.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_presence_penalty_validation_max(self):
        """Test presence_penalty cannot exceed 2.0."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "RESPONSE_LLM_PRESENCE_PENALTY": "2.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_valid_custom_values(self):
        """Test valid custom LLM parameter values."""
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": TEST_FERNET_KEY,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "OPENAI_API_KEY": "sk-test-key",
                "RESPONSE_LLM_TEMPERATURE": "2.0",
                "RESPONSE_LLM_TOP_P": "1.0",
                "RESPONSE_LLM_FREQUENCY_PENALTY": "-2.0",
                "RESPONSE_LLM_PRESENCE_PENALTY": "2.0",
                # Required LLM models (Phase 3 HITL additions)
                "HITL_CLASSIFIER_LLM_MODEL": "gpt-4.1-mini",
                "HITL_QUESTION_GENERATOR_LLM_MODEL": "gpt-4.1-mini",
                "HITL_PLAN_APPROVAL_QUESTION_LLM_MODEL": "gpt-4.1-mini",
                "PLANNER_LLM_MODEL": "gpt-4.1-mini",
                "SEMANTIC_VALIDATOR_LLM_MODEL": "gpt-4.1-mini",
            },
            clear=False,  # Preserve system env vars to avoid import issues
        ):
            settings = Settings(_env_file=None)

            # Verify custom values are accepted
            assert settings.response_llm_temperature == 2.0
            assert settings.response_llm_top_p == 1.0
            assert settings.response_llm_frequency_penalty == -2.0
            assert settings.response_llm_presence_penalty == 2.0
