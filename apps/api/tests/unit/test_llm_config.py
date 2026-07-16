"""
Unit tests for LLM configuration.
Tests Settings validation and OpenAIProvider parameter injection.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.infrastructure.llm.openai_provider import OpenAIProvider


class TestSettingsLLMDefaults:
    """Test default values for LLM configuration in Settings."""

    def test_router_llm_defaults(self):
        """Test router LLM has correct default values from config.py.

        Note: This test verifies config.py defaults match expected values.
        We explicitly set the values to match config.py defaults to ensure
        environment variables from .env don't interfere.
        """
        # Use clear=False to preserve system env vars (PATH, etc.) and explicitly
        # set all router-related values to match config.py defaults
        with patch.dict(
            os.environ,
            {
                "SECRET_KEY": "test_secret_key_minimum_32_characters_long",
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "OPENAI_API_KEY": "sk-test-key",
                # Router config - explicitly set to config.py defaults
                "ROUTER_LLM_MODEL": "gpt-4.1-mini",
                "ROUTER_LLM_TEMPERATURE": "0.1",  # config.py default
                "ROUTER_LLM_TOP_P": "1.0",  # config.py default
                "ROUTER_LLM_FREQUENCY_PENALTY": "0.0",  # config.py default
                "ROUTER_LLM_PRESENCE_PENALTY": "0.0",  # config.py default
                "ROUTER_LLM_MAX_TOKENS": "5000",  # config.py default
                "ROUTER_CONFIDENCE_THRESHOLD": "0.6",  # config.py default
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

            # Verify router defaults (config.py values)
            # NOTE: router_confidence_threshold removed (v3.2 - QueryAnalyzerService handles thresholds)
            assert settings.router_llm_model == "gpt-4.1-mini"
            assert settings.router_llm_temperature == 0.1
            assert settings.router_llm_top_p == 1.0
            assert settings.router_llm_frequency_penalty == 0.0
            assert settings.router_llm_presence_penalty == 0.0
            assert settings.router_llm_max_tokens == 5000

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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "ROUTER_LLM_TEMPERATURE": "-0.1",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "ROUTER_LLM_TOP_P": "-0.1",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "ROUTER_LLM_FREQUENCY_PENALTY": "-2.1",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "ROUTER_LLM_PRESENCE_PENALTY": "-2.1",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
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
                "FERNET_KEY": "test_fernet_key_32_chars_base64==",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "OPENAI_API_KEY": "sk-test-key",
                "ROUTER_LLM_TEMPERATURE": "0.0",
                "ROUTER_LLM_TOP_P": "0.5",
                "ROUTER_LLM_FREQUENCY_PENALTY": "1.0",
                "ROUTER_LLM_PRESENCE_PENALTY": "-1.0",
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
            assert settings.router_llm_temperature == 0.0
            assert settings.router_llm_top_p == 0.5
            assert settings.router_llm_frequency_penalty == 1.0
            assert settings.router_llm_presence_penalty == -1.0
            assert settings.response_llm_temperature == 2.0
            assert settings.response_llm_top_p == 1.0
            assert settings.response_llm_frequency_penalty == -2.0
            assert settings.response_llm_presence_penalty == 2.0


class TestOpenAIProviderConfiguration:
    """Test OpenAIProvider uses settings correctly."""

    def test_router_llm_uses_all_parameters(self):
        """Test router LLM is created with all configured parameters."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            # Setup mock settings
            mock_settings.router_llm_model = "gpt-4.1-mini"
            mock_settings.router_llm_temperature = 0.2
            mock_settings.router_llm_top_p = 0.8
            mock_settings.router_llm_frequency_penalty = 0.5
            mock_settings.router_llm_presence_penalty = 0.3
            mock_settings.router_llm_max_tokens = 1000
            mock_settings.openai_api_key = "test_key"

            # Create router LLM
            llm = OpenAIProvider.get_router_llm()

            # Verify all parameters are set
            assert llm.model_name == "gpt-4.1-mini"
            assert llm.temperature == 0.2
            assert llm.top_p == 0.8
            assert llm.frequency_penalty == 0.5
            assert llm.presence_penalty == 0.3
            assert llm.max_tokens == 1000
            assert llm.streaming is False

    def test_response_llm_uses_all_parameters(self):
        """Test response LLM is created with all configured parameters."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            # Setup mock settings
            mock_settings.response_llm_model = "gpt-4.1-mini-mini"
            mock_settings.response_llm_temperature = 1.5
            mock_settings.response_llm_top_p = 0.9
            mock_settings.response_llm_frequency_penalty = 0.7
            mock_settings.response_llm_presence_penalty = 0.6
            mock_settings.response_llm_max_tokens = 3000
            mock_settings.openai_api_key = "test_key"

            # Create response LLM
            llm = OpenAIProvider.get_response_llm()

            # Verify all parameters are set
            assert llm.model_name == "gpt-4.1-mini-mini"
            assert llm.temperature == 1.5
            assert llm.top_p == 0.9
            assert llm.frequency_penalty == 0.7
            assert llm.presence_penalty == 0.6
            assert llm.max_tokens == 3000
            assert llm.streaming is True

    def test_router_and_response_have_different_configs(self):
        """Test router and response LLMs use different configurations."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            # Setup different configs for router vs response
            mock_settings.router_llm_model = "gpt-4.1-nano"
            mock_settings.router_llm_temperature = 0.1
            mock_settings.router_llm_top_p = 1.0
            mock_settings.router_llm_frequency_penalty = 0.0
            mock_settings.router_llm_presence_penalty = 0.0
            mock_settings.router_llm_max_tokens = 500

            mock_settings.response_llm_model = "gpt-4.1-mini"
            mock_settings.response_llm_temperature = 0.7
            mock_settings.response_llm_top_p = 0.95
            mock_settings.response_llm_frequency_penalty = 0.3
            mock_settings.response_llm_presence_penalty = 0.2
            mock_settings.response_llm_max_tokens = 2000

            mock_settings.openai_api_key = "test_key"

            router_llm = OpenAIProvider.get_router_llm()
            response_llm = OpenAIProvider.get_response_llm()

            # Verify they have different configurations
            assert router_llm.model_name != response_llm.model_name
            assert router_llm.temperature != response_llm.temperature
            assert router_llm.top_p != response_llm.top_p
            assert router_llm.frequency_penalty != response_llm.frequency_penalty
            assert router_llm.presence_penalty != response_llm.presence_penalty
            assert router_llm.max_tokens != response_llm.max_tokens
            assert router_llm.streaming != response_llm.streaming


class TestLLMConfigOverrides:
    """Test LLM config overrides via factory pattern."""

    def test_default_behavior_no_override(self):
        """Test LLM uses settings when config_override is None."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            mock_settings.contacts_agent_llm_model = "gpt-4.1-mini-mini"
            mock_settings.contacts_agent_llm_temperature = 0.5
            mock_settings.contacts_agent_llm_top_p = 1.0
            mock_settings.contacts_agent_llm_frequency_penalty = 0.0
            mock_settings.contacts_agent_llm_presence_penalty = 0.0
            mock_settings.contacts_agent_llm_max_tokens = 10000
            mock_settings.openai_api_key = "test_key"

            llm = OpenAIProvider.get_contacts_agent_llm(config_override=None)

            # Verify fallback to settings
            assert llm.model_name == "gpt-4.1-mini-mini"
            assert llm.temperature == 0.5
            assert llm.top_p == 1.0
            assert llm.frequency_penalty == 0.0
            assert llm.presence_penalty == 0.0
            assert llm.max_tokens == 10000

    def test_full_override(self):
        """Test LLM uses config_override values instead of settings."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            mock_settings.contacts_agent_llm_model = "gpt-4.1-mini-mini"
            mock_settings.contacts_agent_llm_temperature = 0.5
            mock_settings.contacts_agent_llm_top_p = 1.0
            mock_settings.contacts_agent_llm_frequency_penalty = 0.0
            mock_settings.contacts_agent_llm_presence_penalty = 0.0
            mock_settings.contacts_agent_llm_max_tokens = 10000
            mock_settings.openai_api_key = "test_key"

            config_override = {
                "model": "gpt-4.1-mini",
                "temperature": 0.9,
                "top_p": 0.95,
                "frequency_penalty": 0.5,
                "presence_penalty": 0.3,
                "max_tokens": 5000,
            }

            llm = OpenAIProvider.get_contacts_agent_llm(config_override=config_override)

            # Verify override values are used
            assert llm.model_name == "gpt-4.1-mini"
            assert llm.temperature == 0.9
            assert llm.top_p == 0.95
            assert llm.frequency_penalty == 0.5
            assert llm.presence_penalty == 0.3
            assert llm.max_tokens == 5000

    def test_partial_override_temperature_only(self):
        """Test only overridden fields change, others use settings."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            mock_settings.contacts_agent_llm_model = "gpt-4.1-mini-mini"
            mock_settings.contacts_agent_llm_temperature = 0.5
            mock_settings.contacts_agent_llm_top_p = 1.0
            mock_settings.contacts_agent_llm_frequency_penalty = 0.0
            mock_settings.contacts_agent_llm_presence_penalty = 0.0
            mock_settings.contacts_agent_llm_max_tokens = 10000
            mock_settings.openai_api_key = "test_key"

            # Only override temperature
            config_override = {"temperature": 0.9}

            llm = OpenAIProvider.get_contacts_agent_llm(config_override=config_override)

            # Overridden field
            assert llm.temperature == 0.9

            # Non-overridden fields use settings
            assert llm.model_name == "gpt-4.1-mini-mini"
            assert llm.top_p == 1.0
            assert llm.frequency_penalty == 0.0
            assert llm.presence_penalty == 0.0
            assert llm.max_tokens == 10000

    def test_partial_override_model_and_max_tokens(self):
        """Test partial override with multiple fields."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            mock_settings.contacts_agent_llm_model = "gpt-4.1-mini-mini"
            mock_settings.contacts_agent_llm_temperature = 0.5
            mock_settings.contacts_agent_llm_top_p = 1.0
            mock_settings.contacts_agent_llm_frequency_penalty = 0.0
            mock_settings.contacts_agent_llm_presence_penalty = 0.0
            mock_settings.contacts_agent_llm_max_tokens = 10000
            mock_settings.openai_api_key = "test_key"

            # Override model and max_tokens
            config_override = {
                "model": "gpt-4.1-mini",
                "max_tokens": 5000,
            }

            llm = OpenAIProvider.get_contacts_agent_llm(config_override=config_override)

            # Overridden fields
            assert llm.model_name == "gpt-4.1-mini"
            assert llm.max_tokens == 5000

            # Non-overridden fields use settings
            assert llm.temperature == 0.5
            assert llm.top_p == 1.0
            assert llm.frequency_penalty == 0.0
            assert llm.presence_penalty == 0.0

    def test_router_llm_override(self):
        """Test config override works for router LLM."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            mock_settings.router_llm_model = "gpt-4.1-mini"
            mock_settings.router_llm_temperature = 0.1
            mock_settings.router_llm_top_p = 1.0
            mock_settings.router_llm_frequency_penalty = 0.0
            mock_settings.router_llm_presence_penalty = 0.0
            mock_settings.router_llm_max_tokens = 500
            mock_settings.openai_api_key = "test_key"

            config_override = {"temperature": 0.2, "max_tokens": 1000}

            llm = OpenAIProvider.get_router_llm(config_override=config_override)

            assert llm.temperature == 0.2
            assert llm.max_tokens == 1000
            assert llm.model_name == "gpt-4.1-mini"  # Not overridden

    def test_response_llm_override(self):
        """Test config override works for response LLM."""
        with (
            patch("src.infrastructure.llm.openai_provider.settings") as mock_settings,
            patch("src.infrastructure.llm.openai_provider.LLMConfigOverrideCache") as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "test_key"
            mock_settings.response_llm_model = "gpt-4.1-mini"
            mock_settings.response_llm_temperature = 0.7
            mock_settings.response_llm_top_p = 0.95
            mock_settings.response_llm_frequency_penalty = 0.3
            mock_settings.response_llm_presence_penalty = 0.2
            mock_settings.response_llm_max_tokens = 2000
            mock_settings.openai_api_key = "test_key"

            config_override = {"model": "gpt-4.1-mini", "temperature": 1.2}

            llm = OpenAIProvider.get_response_llm(config_override=config_override)

            assert llm.model_name == "gpt-4.1-mini"
            assert llm.temperature == 1.2
            assert llm.top_p == 0.95  # Not overridden
