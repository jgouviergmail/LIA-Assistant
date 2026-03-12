"""
Unit tests for LLM Factory with Multi-Provider Support.

Tests the central factory for creating LLM instances with:
- Config resolution from LLM_DEFAULTS + LLMConfigOverrideCache
- Configuration override pattern (LLMAgentConfig + TypedDict backward compat)
- Metrics callback attachment
- Streaming configuration
- All LLM types

Config source of truth: LLM_DEFAULTS (code constants) → DB override (cache) → Effective config.
Settings are NOT used for LLM config resolution (only API keys).
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.llm_agent_config import LLMAgentConfig
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.factory import get_llm

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure no cache overrides interfere with tests."""
    from src.domains.llm_config.cache import LLMConfigOverrideCache

    LLMConfigOverrideCache.reset()
    yield
    LLMConfigOverrideCache.reset()


@pytest.fixture
def mock_llm():
    """Mock LLM instance."""
    llm = MagicMock(spec=BaseChatModel)
    llm.callbacks = []
    return llm


# ============================================================================
# Basic Factory Tests — Config from LLM_DEFAULTS
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_router_default_config(mock_adapter, mock_llm):
    """Test router LLM creation with LLM_DEFAULTS (no override)."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["router"]

    llm = get_llm("router")

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["provider"] == defaults.provider
    assert call_kwargs["model"] == defaults.model
    assert call_kwargs["temperature"] == defaults.temperature
    assert call_kwargs["max_tokens"] == defaults.max_tokens
    assert call_kwargs["streaming"] is False
    assert len(llm.callbacks) == 0
    assert llm == mock_llm


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_response_with_streaming(mock_adapter, mock_llm):
    """Test response LLM creation with streaming enabled."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["response"]

    get_llm("response")

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["streaming"] is True
    assert call_kwargs["provider"] == defaults.provider
    assert call_kwargs["model"] == defaults.model


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_contacts_agent(mock_adapter, mock_llm):
    """Test contacts_agent LLM creation from LLM_DEFAULTS."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["contacts_agent"]

    get_llm("contacts_agent")

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["provider"] == defaults.provider
    assert call_kwargs["model"] == defaults.model
    assert call_kwargs["streaming"] is False


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_planner(mock_adapter, mock_llm):
    """Test planner LLM creation from LLM_DEFAULTS."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["planner"]

    get_llm("planner")

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["provider"] == defaults.provider
    assert call_kwargs["model"] == defaults.model
    assert call_kwargs["temperature"] == defaults.temperature


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_hitl_classifier(mock_adapter, mock_llm):
    """Test hitl_classifier LLM creation from LLM_DEFAULTS."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["hitl_classifier"]

    get_llm("hitl_classifier")

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["provider"] == defaults.provider
    assert call_kwargs["model"] == defaults.model
    assert call_kwargs["streaming"] is False


# ============================================================================
# Configuration Override Tests
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_with_model_override(mock_adapter, mock_llm):
    """Test LLM creation with dict model override."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["router"]

    get_llm("router", config_override={"model": "gpt-4.1-mini"})

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4.1-mini"  # Overridden
    assert call_kwargs["temperature"] == defaults.temperature  # From LLM_DEFAULTS
    assert call_kwargs["max_tokens"] == defaults.max_tokens  # From LLM_DEFAULTS


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_with_temperature_override(mock_adapter, mock_llm):
    """Test LLM creation with temperature override."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["response"]

    get_llm("response", config_override={"temperature": 0.9})

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["temperature"] == 0.9  # Overridden
    assert call_kwargs["model"] == defaults.model  # From LLM_DEFAULTS


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_with_multiple_overrides(mock_adapter, mock_llm):
    """Test LLM creation with multiple parameter overrides."""
    mock_adapter.create_llm.return_value = mock_llm

    config_override = {
        "model": "gpt-4.1-mini",
        "temperature": 0.8,
        "max_tokens": 2000,
        "top_p": 0.95,
        "frequency_penalty": 0.5,
    }

    get_llm("contacts_agent", config_override=config_override)

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4.1-mini"
    assert call_kwargs["temperature"] == 0.8
    assert call_kwargs["max_tokens"] == 2000
    assert call_kwargs["top_p"] == 0.95
    assert call_kwargs["frequency_penalty"] == 0.5
    assert call_kwargs["presence_penalty"] == 0.0  # From LLM_DEFAULTS


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_with_partial_override(mock_adapter, mock_llm):
    """Test partial override (only temperature overridden)."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["planner"]

    get_llm("planner", config_override={"temperature": 0.2})

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["temperature"] == 0.2  # Overridden
    assert call_kwargs["model"] == defaults.model  # From LLM_DEFAULTS
    assert call_kwargs["max_tokens"] == defaults.max_tokens  # From LLM_DEFAULTS
    assert call_kwargs["top_p"] == defaults.top_p  # From LLM_DEFAULTS


# ============================================================================
# Callbacks Tests (Phase 2.1.1 - Dynamic callbacks, not static)
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_no_static_callbacks_attached(mock_adapter, mock_llm):
    """Test that NO static callbacks are attached (Phase 2.1.1 fix)."""
    mock_adapter.create_llm.return_value = mock_llm

    llm = get_llm("router")

    assert len(llm.callbacks) == 0


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_empty_callbacks_for_all_llm_types(mock_adapter, mock_llm):
    """Test that all LLM types have empty callbacks list (Phase 2.1.1 fix)."""
    mock_adapter.create_llm.return_value = mock_llm

    llm_types = ["router", "response", "contacts_agent", "planner", "hitl_classifier"]

    for llm_type in llm_types:
        mock_llm.callbacks = []
        llm = get_llm(llm_type)
        assert len(llm.callbacks) == 0, f"Static callbacks should not be attached for {llm_type}"


# ============================================================================
# Streaming Configuration Tests
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_streaming_only_for_response(mock_adapter, mock_llm):
    """Test that only response LLM has streaming enabled."""
    mock_adapter.create_llm.return_value = mock_llm

    llm_types = ["router", "response", "contacts_agent", "planner", "hitl_classifier"]

    for llm_type in llm_types:
        get_llm(llm_type)
        call_kwargs = mock_adapter.create_llm.call_args.kwargs

        if llm_type == "response":
            assert call_kwargs["streaming"] is True, "Response should have streaming=True"
        else:
            assert call_kwargs["streaming"] is False, f"{llm_type} should have streaming=False"


# ============================================================================
# Provider Selection Tests — via LLMAgentConfig override
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_provider_selection_per_llm_type(mock_adapter, mock_llm):
    """Test that each LLM type uses its LLM_DEFAULTS provider."""
    mock_adapter.create_llm.return_value = mock_llm

    for llm_type in ["router", "response", "contacts_agent", "planner", "hitl_classifier"]:
        get_llm(llm_type)
        call_kwargs = mock_adapter.create_llm.call_args.kwargs
        expected = LLM_DEFAULTS[llm_type].provider
        assert call_kwargs["provider"] == expected, f"{llm_type} should use {expected} provider"


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_provider_override_via_config(mock_adapter, mock_llm):
    """Test provider can be overridden via LLMAgentConfig."""
    mock_adapter.create_llm.return_value = mock_llm

    override = LLMAgentConfig(
        provider="anthropic",
        model="claude-sonnet-4-5",
        temperature=0.7,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=10000,
    )

    get_llm("response", config_override=override)

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["provider"] == "anthropic"
    assert call_kwargs["model"] == "claude-sonnet-4-5"


# ============================================================================
# Configuration Merging Logic Tests
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_config_merge_preserves_all_parameters(mock_adapter, mock_llm):
    """Test that config merging preserves all LLM parameters."""
    mock_adapter.create_llm.return_value = mock_llm

    get_llm("router")

    call_kwargs = mock_adapter.create_llm.call_args.kwargs

    required_params = [
        "model",
        "temperature",
        "max_tokens",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
    ]
    for param in required_params:
        assert param in call_kwargs, f"Parameter {param} missing in create_llm call"


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_config_override_does_not_affect_other_params(mock_adapter, mock_llm):
    """Test that overriding one parameter doesn't affect others."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["router"]

    get_llm("router", config_override={"model": "gpt-4.1-mini"})

    call_kwargs = mock_adapter.create_llm.call_args.kwargs

    assert call_kwargs["model"] == "gpt-4.1-mini"  # Overridden
    assert call_kwargs["temperature"] == defaults.temperature  # From LLM_DEFAULTS
    assert call_kwargs["max_tokens"] == defaults.max_tokens  # From LLM_DEFAULTS
    assert call_kwargs["top_p"] == defaults.top_p  # From LLM_DEFAULTS
    assert call_kwargs["frequency_penalty"] == defaults.frequency_penalty
    assert call_kwargs["presence_penalty"] == defaults.presence_penalty


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_with_empty_override(mock_adapter, mock_llm):
    """Test LLM creation with empty config_override dict."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["router"]

    get_llm("router", config_override={})

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["model"] == defaults.model
    assert call_kwargs["temperature"] == defaults.temperature


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_provider_adapter_error_bubbles_up(mock_adapter):
    """Test that ProviderAdapter errors bubble up to caller."""
    mock_adapter.create_llm.side_effect = ValueError("Invalid provider configuration")

    with pytest.raises(ValueError, match="Invalid provider configuration"):
        get_llm("router")


def test_get_llm_invalid_llm_type():
    """Test error handling for invalid LLM type."""
    with pytest.raises(ValueError, match="Unknown agent_type 'invalid_type'"):
        get_llm("invalid_type")  # type: ignore


# ============================================================================
# Logging Tests
# ============================================================================


@patch("src.infrastructure.llm.factory.logger")
@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_logging_on_llm_creation(mock_adapter, mock_logger, mock_llm):
    """Test that LLM creation is logged."""
    mock_adapter.create_llm.return_value = mock_llm

    get_llm("router")

    assert mock_logger.info.called
    log_calls = mock_logger.info.call_args_list
    assert any("llm_created" in str(call) or "router" in str(call) for call in log_calls)


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_backward_compatibility_with_existing_code(mock_adapter, mock_llm):
    """Test that existing code calling get_llm() without provider param still works."""
    mock_adapter.create_llm.return_value = mock_llm

    llm = get_llm("router")

    assert llm == mock_llm
    assert mock_adapter.create_llm.called


# ============================================================================
# LLMAgentConfig Integration Tests (Phase X Refactoring)
# ============================================================================


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_with_none_config_uses_helper(mock_adapter, mock_llm):
    """Test that None config_override triggers get_llm_config_for_agent."""
    mock_adapter.create_llm.return_value = mock_llm

    with patch("src.infrastructure.llm.factory.get_llm_config_for_agent") as mock_helper:
        mock_helper.return_value = LLMAgentConfig(
            provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            max_tokens=5000,
        )

        get_llm("router")

        mock_helper.assert_called_once()


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_with_llm_agent_config_override(mock_adapter, mock_llm):
    """Test LLMAgentConfig override (new pattern)."""
    mock_adapter.create_llm.return_value = mock_llm

    override_config = LLMAgentConfig(
        provider="anthropic",
        model="claude-3-opus",
        temperature=0.8,
        top_p=0.95,
        frequency_penalty=0.2,
        presence_penalty=0.1,
        max_tokens=20000,
    )

    get_llm("response", config_override=override_config)

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["provider"] == "anthropic"
    assert call_kwargs["model"] == "claude-3-opus"
    assert call_kwargs["temperature"] == 0.8
    assert call_kwargs["max_tokens"] == 20000
    assert call_kwargs["top_p"] == 0.95
    assert call_kwargs["frequency_penalty"] == 0.2
    assert call_kwargs["presence_penalty"] == 0.1


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_with_typed_dict_override_backward_compat(mock_adapter, mock_llm):
    """Test TypedDict override (old pattern) still works."""
    mock_adapter.create_llm.return_value = mock_llm

    override_config = {
        "model": "gpt-4.1-mini",
        "temperature": 0.9,
        "max_tokens": 15000,
    }

    get_llm("router", config_override=override_config)

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4.1-mini"  # Overridden
    assert call_kwargs["temperature"] == 0.9  # Overridden
    assert call_kwargs["max_tokens"] == 15000  # Overridden
    assert call_kwargs["top_p"] == 1.0  # From LLM_DEFAULTS


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_provider_from_agent_config_not_settings(mock_adapter, mock_llm):
    """Test provider comes from LLMAgentConfig, not directly from settings."""
    mock_adapter.create_llm.return_value = mock_llm

    override_config = LLMAgentConfig(
        provider="anthropic",
        model="claude-3-opus",
        temperature=0.1,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=5000,
    )

    get_llm("router", config_override=override_config)

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["provider"] == "anthropic"


@patch("src.infrastructure.llm.factory.ProviderAdapter")
def test_get_llm_typed_dict_partial_override_backward_compat(mock_adapter, mock_llm):
    """Test TypedDict partial override preserves LLM_DEFAULTS."""
    mock_adapter.create_llm.return_value = mock_llm
    defaults = LLM_DEFAULTS["planner"]

    override_config = {"temperature": 0.95}

    get_llm("planner", config_override=override_config)

    call_kwargs = mock_adapter.create_llm.call_args.kwargs
    assert call_kwargs["temperature"] == 0.95  # Overridden
    assert call_kwargs["model"] == defaults.model  # From LLM_DEFAULTS
    assert call_kwargs["max_tokens"] == defaults.max_tokens  # From LLM_DEFAULTS
    assert call_kwargs["provider"] == defaults.provider  # From LLM_DEFAULTS
