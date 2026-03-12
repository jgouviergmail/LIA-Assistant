"""
Unit tests for ProviderAdapter.

Tests the universal LLM provider adapter with comprehensive coverage:
- Provider-specific instantiation (OpenAI, Anthropic, DeepSeek, Perplexity, Ollama)
- Credential injection and validation
- Provider/model compatibility validation
- Advanced configuration loading from JSON
- Error handling and edge cases

Best Practices (LangChain 1.0 / 2025):
- Use GenericFakeChatModel for mocking (avoids network calls)
- Test provider-specific quirks (e.g., DeepSeek reasoner without tools)
- Validate configuration merging logic
- Test error paths explicitly
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from src.infrastructure.llm.providers.adapter import ProviderAdapter

# Check if langchain-deepseek is available (optional dependency)
try:
    import langchain_deepseek  # noqa: F401

    HAS_DEEPSEEK = True
except ImportError:
    HAS_DEEPSEEK = False

# Skip marker for DeepSeek tests when module not available
skip_if_no_deepseek = pytest.mark.skipif(
    not HAS_DEEPSEEK, reason="langchain-deepseek not installed (optional dependency)"
)


# ============================================================================
# Fixtures
# ============================================================================
# Note: mock_settings_class fixture is imported from conftest.py


# ============================================================================
# OpenAI Provider Tests
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_openai_basic(mock_settings_module, mock_init_chat_model, mock_settings_class):
    """Test OpenAI LLM creation with basic parameters (Chat Completions path)."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    # Use gpt-4-turbo (not Responses API eligible) to test Chat Completions path
    llm = ProviderAdapter.create_llm(
        provider="openai",
        model="gpt-4-turbo",
        temperature=0.7,
        max_tokens=1000,
        streaming=False,
        llm_type="router",
    )

    # Verify init_chat_model was called with correct parameters
    mock_init_chat_model.assert_called_once()
    call_args = mock_init_chat_model.call_args

    assert call_args.kwargs["model"] == "gpt-4-turbo"
    assert call_args.kwargs["model_provider"] == "openai"
    assert call_args.kwargs["temperature"] == 0.7
    assert call_args.kwargs["max_tokens"] == 1000
    assert call_args.kwargs["streaming"] is False
    assert "openai_api_key" in call_args.kwargs
    assert call_args.kwargs["openai_api_key"] == "sk-test-openai-key"

    assert llm == mock_llm


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_openai_with_advanced_params(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test OpenAI LLM with advanced parameters (top_p, frequency_penalty, etc.)."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    # Use gpt-4-turbo (not Responses API eligible) to test Chat Completions path
    ProviderAdapter.create_llm(
        provider="openai",
        model="gpt-4-turbo",
        temperature=0.8,
        max_tokens=2000,
        streaming=True,
        llm_type="response",
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.3,
    )

    call_args = mock_init_chat_model.call_args
    assert call_args.kwargs["top_p"] == 0.9
    assert call_args.kwargs["frequency_penalty"] == 0.5
    assert call_args.kwargs["presence_penalty"] == 0.3


# ============================================================================
# Anthropic Provider Tests
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_anthropic_basic(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test Anthropic LLM creation with basic parameters."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.3,
        max_tokens=5000,
        streaming=True,
        llm_type="response",
    )

    call_args = mock_init_chat_model.call_args
    assert call_args.kwargs["model"] == "claude-sonnet-4-5"
    assert call_args.kwargs["model_provider"] == "anthropic"
    assert "anthropic_api_key" in call_args.kwargs
    assert call_args.kwargs["anthropic_api_key"] == "sk-test-anthropic-key"


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_anthropic_with_thinking_mode(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test Anthropic LLM with extended thinking mode via provider_config."""
    # Configure thinking mode in provider_config
    mock_settings_class.response_llm_provider_config = json.dumps(
        {"thinking": {"type": "enabled", "budget_tokens": 5000}}
    )
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=10000,
        streaming=False,
        llm_type="response",
    )

    call_args = mock_init_chat_model.call_args
    # Verify thinking mode was passed through
    assert "thinking" in call_args.kwargs
    assert call_args.kwargs["thinking"]["type"] == "enabled"
    assert call_args.kwargs["thinking"]["budget_tokens"] == 5000


# ============================================================================
# DeepSeek Provider Tests
# ============================================================================


@skip_if_no_deepseek
@patch("langchain_deepseek.ChatDeepSeek")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_deepseek_chat(mock_settings_module, mock_chat_deepseek, mock_settings_class):
    """Test DeepSeek chat model creation (supports tools)."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_chat_deepseek.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="deepseek",
        model="deepseek-chat",
        temperature=0.5,
        max_tokens=4000,
        streaming=False,
        llm_type="contacts_agent",
    )

    # Verify ChatDeepSeek was instantiated with correct parameters
    mock_chat_deepseek.assert_called_once()
    call_args = mock_chat_deepseek.call_args

    assert call_args.kwargs["model"] == "deepseek-chat"
    assert call_args.kwargs["temperature"] == 0.5
    assert call_args.kwargs["max_tokens"] == 4000
    assert call_args.kwargs["streaming"] is False
    # Note: ChatDeepSeek uses api_key, not deepseek_api_key
    assert call_args.kwargs["api_key"] == "sk-test-deepseek-key"


@skip_if_no_deepseek
@patch("langchain_deepseek.ChatDeepSeek")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_deepseek_reasoner_validation(
    mock_settings_module, mock_chat_deepseek, mock_settings_class
):
    """Test DeepSeek reasoner validation (cannot be used for contacts_agent due to no tool support)."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))

    with pytest.raises(ValueError, match="deepseek-reasoner does NOT support tools"):
        ProviderAdapter.create_llm(
            provider="deepseek",
            model="deepseek-reasoner",
            temperature=0.0,
            max_tokens=8000,
            streaming=False,
            llm_type="contacts_agent",  # Requires tool support
        )


@skip_if_no_deepseek
@patch("langchain_deepseek.ChatDeepSeek")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_deepseek_reasoner_allowed_for_planner(
    mock_settings_module, mock_chat_deepseek, mock_settings_class
):
    """Test DeepSeek reasoner is allowed for planner (no tools required)."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_chat_deepseek.return_value = mock_llm

    llm = ProviderAdapter.create_llm(
        provider="deepseek",
        model="deepseek-reasoner",
        temperature=0.0,
        max_tokens=16000,
        streaming=False,
        llm_type="planner",  # OK, planner doesn't need tools
    )

    assert llm == mock_llm


# ============================================================================
# Perplexity Provider Tests
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_perplexity_sonar(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test Perplexity Sonar model creation."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="perplexity",
        model="sonar-pro",
        temperature=0.6,
        max_tokens=3000,
        streaming=False,
        llm_type="router",
    )

    call_args = mock_init_chat_model.call_args
    assert call_args.kwargs["model"] == "sonar-pro"
    assert call_args.kwargs["model_provider"] == "openai"  # OpenAI-compatible
    assert "openai_api_key" in call_args.kwargs
    assert call_args.kwargs["openai_api_key"] == "pplx-test-key"
    assert "base_url" in call_args.kwargs
    assert "api.perplexity.ai" in call_args.kwargs["base_url"]


# ============================================================================
# Ollama Provider Tests
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_ollama_local(mock_settings_module, mock_init_chat_model, mock_settings_class):
    """Test Ollama local model creation."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="ollama",
        model="llama3.2",
        temperature=0.7,
        max_tokens=2000,
        streaming=True,
        llm_type="response",
    )

    call_args = mock_init_chat_model.call_args
    assert call_args.kwargs["model"] == "llama3.2"
    assert call_args.kwargs["model_provider"] == "openai"  # Ollama uses OpenAI-compatible API
    assert "base_url" in call_args.kwargs
    assert call_args.kwargs["base_url"] == "http://localhost:11434/v1"


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_ollama_custom_base_url(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test Ollama with custom base URL (remote deployment)."""
    mock_settings_class.ollama_base_url = "http://ollama-server:11434/v1"
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="ollama",
        model="mistral",
        temperature=0.5,
        max_tokens=4000,
        streaming=False,
        llm_type="hitl_classifier",
    )

    call_args = mock_init_chat_model.call_args
    assert call_args.kwargs["base_url"] == "http://ollama-server:11434/v1"


# ============================================================================
# Configuration Loading Tests
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_load_provider_config_json(mock_settings_module, mock_init_chat_model, mock_settings_class):
    """Test loading advanced provider config from JSON string."""
    # Configure advanced Ollama parameters
    mock_settings_class.planner_llm_provider_config = json.dumps(
        {
            "num_predict": 2048,
            "top_k": 40,
            "repeat_penalty": 1.1,
        }
    )
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="ollama",
        model="qwen2.5",
        temperature=0.0,
        max_tokens=8000,
        streaming=False,
        llm_type="planner",
    )

    call_args = mock_init_chat_model.call_args
    # Verify advanced config was merged
    assert call_args.kwargs["num_predict"] == 2048
    assert call_args.kwargs["top_k"] == 40
    assert call_args.kwargs["repeat_penalty"] == 1.1


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
@patch("src.infrastructure.llm.providers.adapter.logger")
def test_load_provider_config_invalid_json(
    mock_logger, mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test handling of invalid JSON in provider_config (logs warning, continues with empty config)."""
    mock_settings_class.router_llm_provider_config = "{invalid json"
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    # Should not raise - gracefully handles invalid JSON
    llm = ProviderAdapter.create_llm(
        provider="openai",
        model="gpt-4.1-mini-mini",
        temperature=0.1,
        max_tokens=500,
        streaming=False,
        llm_type="router",
    )

    # Verify warning was logged
    mock_logger.warning.assert_called_once()
    assert "invalid_provider_config_json" in str(mock_logger.warning.call_args)
    assert llm is not None


# ============================================================================
# Validation Tests
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.ProviderAdapter._create_deepseek_llm")
@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_validate_provider_model_compatibility(
    mock_settings_module, mock_init_chat_model, mock_create_deepseek, mock_settings_class
):
    """Test provider/model compatibility validation."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))

    # Test 1: DeepSeek reasoner without tools should fail for contacts_agent
    with pytest.raises(ValueError, match="deepseek-reasoner does NOT support tools"):
        ProviderAdapter.create_llm(
            provider="deepseek",
            model="deepseek-reasoner",
            temperature=0.0,
            max_tokens=8000,
            streaming=False,
            llm_type="contacts_agent",
        )

    # Test 2: DeepSeek chat should work for contacts_agent (supports tools)
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_create_deepseek.return_value = mock_llm

    llm = ProviderAdapter.create_llm(
        provider="deepseek",
        model="deepseek-chat",  # Supports tools
        temperature=0.0,
        max_tokens=8000,
        streaming=False,
        llm_type="contacts_agent",
    )
    assert llm is not None
    mock_create_deepseek.assert_called_once()


# ============================================================================
# Error Handling Tests
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_missing_credentials(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test error handling when credentials are missing."""
    mock_settings_class.anthropic_api_key = ""  # Empty API key
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))

    # init_chat_model should raise an error (we let it bubble up)
    mock_init_chat_model.side_effect = ValueError("API key is required")

    with pytest.raises(ValueError, match="API key is required"):
        ProviderAdapter.create_llm(
            provider="anthropic",
            model="claude-sonnet-4-5",
            temperature=0.5,
            max_tokens=4000,
            streaming=False,
            llm_type="response",
        )


@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_invalid_provider(mock_settings_module, mock_settings_class):
    """Test error handling for invalid provider."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))

    with pytest.raises(ValueError, match="Unsupported provider"):
        ProviderAdapter.create_llm(
            provider="invalid_provider",  # type: ignore
            model="some-model",
            temperature=0.5,
            max_tokens=1000,
            streaming=False,
            llm_type="router",
        )


# ============================================================================
# Streaming Tests
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_streaming_enabled(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test LLM creation with streaming enabled (Chat Completions path)."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    # Use gpt-4-turbo (not Responses API eligible) to test Chat Completions path
    ProviderAdapter.create_llm(
        provider="openai",
        model="gpt-4-turbo",
        temperature=0.7,
        max_tokens=2000,
        streaming=True,  # Streaming enabled
        llm_type="response",
    )

    call_args = mock_init_chat_model.call_args
    assert call_args.kwargs["streaming"] is True


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_create_llm_streaming_disabled(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test LLM creation with streaming disabled."""
    # Configure the patched settings object with attributes from mock_settings_class
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.3,
        max_tokens=5000,
        streaming=False,  # Streaming disabled
        llm_type="planner",
    )

    call_args = mock_init_chat_model.call_args
    assert call_args.kwargs["streaming"] is False


# ============================================================================
# Reasoning Models Parameter Filtering Tests (2025-11-09)
# ============================================================================


@patch("src.infrastructure.llm.providers.adapter.is_responses_api_eligible", return_value=False)
@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_reasoning_model_parameter_filtering_gpt5(
    mock_settings_module, mock_init_chat_model, mock_responses_eligible, mock_settings_class
):
    """Test that unsupported parameters are filtered for GPT-5 reasoning models (Chat Completions fallback)."""
    # Configure the patched settings object
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="openai",
        model="gpt-5-mini",  # Reasoning model
        temperature=0.5,
        max_tokens=4096,
        streaming=False,
        llm_type="planner",
        top_p=0.9,  # Should be REMOVED
        frequency_penalty=0.5,  # Should be REMOVED
        presence_penalty=0.3,  # Should be REMOVED
    )

    call_args = mock_init_chat_model.call_args

    # Verify unsupported parameters were removed
    assert "top_p" not in call_args.kwargs
    assert "frequency_penalty" not in call_args.kwargs
    assert "presence_penalty" not in call_args.kwargs

    # Verify core parameters are still passed
    assert call_args.kwargs["model"] == "gpt-5-mini"
    assert call_args.kwargs["max_tokens"] == 4096


@patch("src.infrastructure.llm.providers.adapter.is_responses_api_eligible", return_value=False)
@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_reasoning_model_parameter_filtering_o_series(
    mock_settings_module, mock_init_chat_model, mock_responses_eligible, mock_settings_class
):
    """Test that unsupported parameters are filtered for o-series reasoning models (Chat Completions fallback)."""
    # Configure the patched settings object
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="openai",
        model="o3-mini",  # o-series reasoning model
        temperature=1.0,
        max_tokens=8192,
        streaming=False,
        llm_type="response",
        top_p=1.0,  # Should be REMOVED
        frequency_penalty=0.0,  # Should be REMOVED
        presence_penalty=0.0,  # Should be REMOVED
    )

    call_args = mock_init_chat_model.call_args

    # Verify unsupported parameters were removed
    assert "top_p" not in call_args.kwargs
    assert "frequency_penalty" not in call_args.kwargs
    assert "presence_penalty" not in call_args.kwargs


@patch("src.infrastructure.llm.providers.adapter.is_responses_api_eligible", return_value=False)
@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_reasoning_model_temperature_removal(
    mock_settings_module, mock_init_chat_model, mock_responses_eligible, mock_settings_class
):
    """Test that non-1.0 temperature is removed for reasoning models (Chat Completions fallback)."""
    # Configure the patched settings object
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="openai",
        model="gpt-5-nano",  # Reasoning model
        temperature=0.7,  # Non-1.0 temperature, should be REMOVED
        max_tokens=2048,
        streaming=False,
        llm_type="hitl_classifier",
    )

    call_args = mock_init_chat_model.call_args

    # Verify temperature was removed (OpenAI will use default of 1.0)
    assert "temperature" not in call_args.kwargs or call_args.kwargs.get("temperature") is None


@patch("src.infrastructure.llm.providers.adapter.is_responses_api_eligible", return_value=False)
@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_reasoning_model_temperature_1_preserved(
    mock_settings_module, mock_init_chat_model, mock_responses_eligible, mock_settings_class
):
    """Test that temperature=1.0 is preserved for reasoning models (Chat Completions fallback)."""
    # Configure the patched settings object
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="openai",
        model="o4-mini",  # Reasoning model
        temperature=1.0,  # Exactly 1.0, should be preserved
        max_tokens=4096,
        streaming=False,
        llm_type="planner",
    )

    call_args = mock_init_chat_model.call_args

    # Verify temperature=1.0 is preserved (it's the valid value)
    assert call_args.kwargs.get("temperature") == 1.0


@patch("src.infrastructure.llm.providers.adapter.is_responses_api_eligible", return_value=False)
@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_reasoning_effort_passed_for_reasoning_models(
    mock_settings_module, mock_init_chat_model, mock_responses_eligible, mock_settings_class
):
    """Test that reasoning_effort is passed through for reasoning models (Chat Completions fallback)."""
    # Configure the patched settings object
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="openai",
        model="gpt-5-nano",  # Reasoning model
        temperature=1.0,
        max_tokens=2048,
        streaming=False,
        llm_type="router",
        reasoning_effort="minimal",  # Should be preserved
    )

    call_args = mock_init_chat_model.call_args

    # Verify reasoning_effort was passed through
    assert call_args.kwargs.get("reasoning_effort") == "minimal"


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_standard_model_parameters_preserved(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test that standard (non-reasoning) models preserve all sampling parameters."""
    # Configure the patched settings object
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    # Use gpt-4-turbo (standard model, not Responses API eligible)
    ProviderAdapter.create_llm(
        provider="openai",
        model="gpt-4-turbo",  # Standard model, NOT a reasoning model
        temperature=0.7,
        max_tokens=4096,
        streaming=False,
        llm_type="response",
        top_p=0.9,  # Should be PRESERVED
        frequency_penalty=0.5,  # Should be PRESERVED
        presence_penalty=0.3,  # Should be PRESERVED
    )

    call_args = mock_init_chat_model.call_args

    # Verify ALL sampling parameters are preserved for standard models
    assert call_args.kwargs["temperature"] == 0.7
    assert call_args.kwargs["top_p"] == 0.9
    assert call_args.kwargs["frequency_penalty"] == 0.5
    assert call_args.kwargs["presence_penalty"] == 0.3


@patch("src.infrastructure.llm.providers.adapter.is_responses_api_eligible", return_value=False)
@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_reasoning_model_detection_case_insensitive(
    mock_settings_module, mock_init_chat_model, mock_responses_eligible, mock_settings_class
):
    """Test that reasoning model detection works with different case variations (Chat Completions fallback)."""
    # Configure the patched settings object
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    # Test with uppercase model name
    ProviderAdapter.create_llm(
        provider="openai",
        model="GPT-5-Mini",  # Uppercase variation
        temperature=0.5,
        max_tokens=2048,
        streaming=False,
        llm_type="planner",
        top_p=0.9,
    )

    call_args = mock_init_chat_model.call_args

    # Verify parameters were still filtered (case-insensitive detection)
    assert "top_p" not in call_args.kwargs


@patch("src.infrastructure.llm.providers.adapter.init_chat_model")
@patch("src.infrastructure.llm.providers.adapter.settings")
def test_anthropic_provider_filters_unsupported_params(
    mock_settings_module, mock_init_chat_model, mock_settings_class
):
    """Test that Anthropic filters unsupported parameters (frequency_penalty, presence_penalty)."""
    # Configure the patched settings object
    for attr in dir(mock_settings_class):
        if not attr.startswith("_"):
            setattr(mock_settings_module, attr, getattr(mock_settings_class, attr))
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_init_chat_model.return_value = mock_llm

    ProviderAdapter.create_llm(
        provider="anthropic",  # Anthropic provider
        model="claude-sonnet-4-5",
        temperature=0.7,
        max_tokens=8192,
        streaming=False,
        llm_type="response",
        top_p=0.9,  # Anthropic supports top_p
        frequency_penalty=0.5,  # NOT supported by Anthropic - should be FILTERED
        presence_penalty=0.3,  # NOT supported by Anthropic - should be FILTERED
    )

    call_args = mock_init_chat_model.call_args

    # Verify supported parameters are preserved
    assert call_args.kwargs["temperature"] == 0.7
    assert call_args.kwargs["top_p"] == 0.9

    # Verify unsupported parameters are FILTERED (Anthropic doesn't support these)
    assert "frequency_penalty" not in call_args.kwargs
    assert "presence_penalty" not in call_args.kwargs
