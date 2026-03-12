"""
Unit tests for HitlResponseClassifier Multi-Provider Support.

Tests the multi-provider refactoring of HitlResponseClassifier:
- Factory integration (get_llm)
- Provider selection from settings
- Backward compatibility with parameter-based instantiation
- JSON mode configuration
- Configuration override pattern

Best Practices (LangChain 1.0 / 2025):
- Mock get_llm to avoid actual LLM instantiation
- Test backward compatibility thoroughly
- Validate that refactoring doesn't break existing tests
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_settings():
    """Mock settings for HITL classifier."""

    class MockSettings:
        # Provider credentials (from conftest pattern)
        openai_api_key = "sk-test-openai-key"
        anthropic_api_key = "sk-test-anthropic-key"
        deepseek_api_key = "sk-test-deepseek-key"
        perplexity_api_key = "pplx-test-key"
        ollama_base_url = "http://localhost:11434/v1"

        # Provider-specific config fields (JSON strings)
        hitl_classifier_llm_provider_config = "{}"

        # HITL Classifier configuration
        hitl_classifier_llm_provider = "openai"
        hitl_classifier_llm_model = "gpt-4.1-mini-mini"
        hitl_classifier_llm_temperature = 0.1
        hitl_classifier_llm_top_p = 1.0
        hitl_classifier_llm_frequency_penalty = 0.0
        hitl_classifier_llm_presence_penalty = 0.0
        hitl_classifier_llm_max_tokens = 2000

    return MockSettings()


@pytest.fixture
def mock_llm():
    """Mock LLM instance."""
    llm = MagicMock(spec=BaseChatModel)
    llm.model_kwargs = {}
    llm.callbacks = []
    return llm


# ============================================================================
# Factory Integration Tests
# ============================================================================


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_uses_factory(mock_get_settings, mock_get_llm, mock_settings, mock_llm):
    """Test that classifier uses get_llm factory instead of direct instantiation."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    classifier = HitlResponseClassifier()

    # Verify get_llm was called with correct LLM type
    mock_get_llm.assert_called_once_with(
        llm_type="hitl_classifier",
        config_override=None,
    )

    # Verify LLM was assigned
    assert classifier.llm == mock_llm


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_with_no_params_uses_settings(
    mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that classifier with no parameters uses settings defaults."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    HitlResponseClassifier()

    # Verify factory was called with no config_override
    call_args = mock_get_llm.call_args
    assert call_args.kwargs["config_override"] is None


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_with_model_param_backward_compatible(
    mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that specifying model parameter still works (backward compatible)."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    HitlResponseClassifier(model="gpt-4.1-mini")

    # Verify config_override was passed with model
    call_args = mock_get_llm.call_args
    assert call_args.kwargs["config_override"] == {"model": "gpt-4.1-mini"}


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_with_temperature_param(
    mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that specifying temperature parameter works."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    HitlResponseClassifier(temperature=0.5)

    call_args = mock_get_llm.call_args
    assert call_args.kwargs["config_override"] == {"temperature": 0.5}


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_with_multiple_params(mock_get_settings, mock_get_llm, mock_settings, mock_llm):
    """Test that specifying multiple parameters works."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    HitlResponseClassifier(
        model="gpt-4.1-mini-mini",
        temperature=0.2,
        top_p=0.95,
        frequency_penalty=0.3,
        presence_penalty=0.1,
    )

    call_args = mock_get_llm.call_args
    expected_override = {
        "model": "gpt-4.1-mini-mini",
        "temperature": 0.2,
        "top_p": 0.95,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.1,
    }
    assert call_args.kwargs["config_override"] == expected_override


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_with_partial_params(mock_get_settings, mock_get_llm, mock_settings, mock_llm):
    """Test that specifying some parameters works (partial override)."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    HitlResponseClassifier(model="gpt-4.1-mini", temperature=0.3)

    call_args = mock_get_llm.call_args
    # Only specified parameters should be in override
    assert call_args.kwargs["config_override"] == {
        "model": "gpt-4.1-mini",
        "temperature": 0.3,
    }


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_none_params_ignored(mock_get_settings, mock_get_llm, mock_settings, mock_llm):
    """Test that None parameters are not included in config_override."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    # Explicitly pass None (should be ignored)
    HitlResponseClassifier(
        model=None,
        temperature=0.5,  # Only this should be in override
        top_p=None,
    )

    call_args = mock_get_llm.call_args
    # Only non-None parameter should be in override
    assert call_args.kwargs["config_override"] == {"temperature": 0.5}


# ============================================================================
# JSON Mode Configuration Tests
# ============================================================================


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_uses_structured_output(
    mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that classifier uses with_structured_output for provider-agnostic JSON.

    Since the refactor, the classifier no longer sets OpenAI-specific response_format.
    Instead, it uses with_structured_output(ClassificationResult) which works across
    all LLM providers (OpenAI, Anthropic, DeepSeek, etc.).
    """
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    classifier = HitlResponseClassifier()

    # Verify no provider-specific model_kwargs were set
    assert not hasattr(mock_llm, "model_kwargs") or mock_llm.model_kwargs == {}

    # Verify classifier was created with factory LLM
    assert classifier.llm == mock_llm


# ============================================================================
# Provider Selection Tests
# ============================================================================


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_respects_provider_from_settings(
    mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that classifier uses provider from settings."""
    mock_settings.hitl_classifier_llm_provider = "anthropic"
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    HitlResponseClassifier()

    # Factory should be called (provider is read inside factory, not by classifier)
    mock_get_llm.assert_called_once()


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_works_with_ollama_provider(
    mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that classifier works with Ollama provider."""
    mock_settings.hitl_classifier_llm_provider = "ollama"
    mock_settings.hitl_classifier_llm_model = "llama3.2"
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    classifier = HitlResponseClassifier()

    # Should work without errors
    assert classifier.llm == mock_llm


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_works_with_deepseek_provider(
    mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that classifier works with DeepSeek provider."""
    mock_settings.hitl_classifier_llm_provider = "deepseek"
    mock_settings.hitl_classifier_llm_model = "deepseek-chat"
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    classifier = HitlResponseClassifier()

    assert classifier.llm == mock_llm


# ============================================================================
# Logging Tests
# ============================================================================


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
@patch("src.domains.agents.services.hitl_classifier.logger")
def test_classifier_logs_initialization(
    mock_logger, mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that classifier logs initialization with provider and model."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    HitlResponseClassifier()

    # Verify info log was called
    mock_logger.info.assert_called_once()
    log_call = mock_logger.info.call_args

    # Check log contains relevant information
    assert log_call[0][0] == "hitl_classifier_initialized"
    assert "provider" in log_call[1]
    assert "model" in log_call[1]
    assert log_call[1]["provider"] == "openai"
    assert log_call[1]["model"] == "gpt-5-nano"


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
@patch("src.domains.agents.services.hitl_classifier.logger")
def test_classifier_logs_override_status(
    mock_logger, mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that classifier logs whether config override was used."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    # Test with override
    HitlResponseClassifier(model="gpt-4.1-mini")

    log_call = mock_logger.info.call_args
    assert log_call[1]["has_override"] is True

    # Test without override
    mock_logger.reset_mock()
    HitlResponseClassifier()

    log_call2 = mock_logger.info.call_args
    assert log_call2[1]["has_override"] is False


# ============================================================================
# Edge Cases Tests
# ============================================================================


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_with_zero_temperature(mock_get_settings, mock_get_llm, mock_settings, mock_llm):
    """Test that zero temperature (deterministic) works."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    HitlResponseClassifier(temperature=0.0)

    call_args = mock_get_llm.call_args
    assert call_args.kwargs["config_override"] == {"temperature": 0.0}


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_classifier_get_llm_error_bubbles_up(mock_get_settings, mock_get_llm, mock_settings):
    """Test that get_llm errors bubble up to caller."""
    mock_get_settings.return_value = mock_settings
    mock_get_llm.side_effect = ValueError("Invalid configuration")

    with pytest.raises(ValueError, match="Invalid configuration"):
        HitlResponseClassifier()


# ============================================================================
# Migration Validation Tests
# ============================================================================


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_old_instantiation_pattern_still_works(
    mock_get_settings, mock_get_llm, mock_settings, mock_llm
):
    """Test that old instantiation pattern (from service.py:294) still works."""
    # Old pattern from src/domains/agents/api/service.py:294
    # HitlResponseClassifier(
    #     model=settings.hitl_classifier_model,
    #     temperature=settings.hitl_classifier_temperature,
    #     top_p=settings.hitl_classifier_top_p,
    #     frequency_penalty=settings.hitl_classifier_frequency_penalty,
    #     presence_penalty=settings.hitl_classifier_presence_penalty,
    # )

    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    classifier = HitlResponseClassifier(
        model="gpt-4.1-mini-mini",
        temperature=0.1,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
    )

    # Should work without errors
    assert classifier.llm == mock_llm

    # Verify all parameters were passed in config_override
    call_args = mock_get_llm.call_args
    assert call_args.kwargs["config_override"] == {
        "model": "gpt-4.1-mini-mini",
        "temperature": 0.1,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    }


@patch("src.domains.agents.services.hitl_classifier.get_llm")
@patch("src.core.config.get_settings")
def test_new_instantiation_pattern_works(mock_get_settings, mock_get_llm, mock_settings, mock_llm):
    """Test that new instantiation pattern (no params) works."""
    # New pattern (recommended)
    # HitlResponseClassifier()  # Uses settings defaults

    mock_get_settings.return_value = mock_settings
    mock_get_llm.return_value = mock_llm

    classifier = HitlResponseClassifier()

    # Should work without errors
    assert classifier.llm == mock_llm

    # Verify no config_override was passed
    call_args = mock_get_llm.call_args
    assert call_args.kwargs["config_override"] is None
