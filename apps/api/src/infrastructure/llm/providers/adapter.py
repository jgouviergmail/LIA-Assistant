"""
Universal LLM Provider Adapter.

Provides a unified interface for creating LLM instances across multiple providers
(OpenAI, Anthropic, DeepSeek, Perplexity, Ollama) using LangChain 1.0's init_chat_model.

Architecture:
- Uses LangChain's init_chat_model() for provider-agnostic instantiation
- Handles provider-specific credential injection
- Supports advanced provider-specific configuration via JSON config strings
- Validates provider/model compatibility (e.g., deepseek-reasoner doesn't support tools)
"""

import json
import re
from typing import Any, Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.config import settings
from src.core.constants import REASONING_MODELS_PATTERN
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_PROVIDERS
from src.infrastructure.llm.providers.responses_adapter import (
    ResponsesLLM,
    is_responses_api_eligible,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

ProviderType = Literal["openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini", "qwen"]


_ENV_FALLBACK: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "gemini": "GOOGLE_GEMINI_API_KEY",
    "ollama": "OLLAMA_BASE_URL",
    "qwen": "QWEN_API_KEY",
}


def _require_api_key(provider: str) -> str:
    """Get API key: DB cache first, then .env fallback.

    Resolution order:
    1. DB cache (Admin UI, encrypted at rest)
    2. Environment variable fallback (.env)
    3. Graceful degradation: return placeholder to allow startup without keys

    Args:
        provider: Provider identifier (e.g., "openai", "anthropic").

    Returns:
        Decrypted API key string, or "NOT_CONFIGURED" placeholder if no key is found.
        The placeholder allows the application to start without API keys configured.
        LLM calls will fail at runtime with a clear error until keys are configured
        via Settings > Administration > LLM Configuration.
    """
    import os

    # 1. DB cache (Admin UI)
    key = LLMConfigOverrideCache.get_api_key(provider)
    if key:
        return key

    # 2. .env fallback
    env_var = _ENV_FALLBACK.get(provider)
    if env_var:
        env_key = os.environ.get(env_var, "")
        if env_key and not env_key.startswith("CHANGE_ME"):
            return env_key

    # 3. Graceful degradation: allow startup without API keys
    # Users can configure keys post-launch via Settings > Administration > LLM Configuration
    display_name = LLM_PROVIDERS.get(provider, provider)
    env_hint = _ENV_FALLBACK.get(provider, "UNKNOWN")
    logger.warning(
        "api_key_not_configured",
        provider=display_name,
        env_var=env_hint,
        hint="Configure via Settings > Administration > LLM Configuration or set environment variable",
    )
    return "NOT_CONFIGURED"


class ProviderAdapter:
    """
    Universal adapter for creating LLM instances across multiple providers.

    Supports:
    - OpenAI: Standard provider with full feature support
    - Anthropic: Claude models with thinking mode support
    - DeepSeek: Cost-effective provider (deepseek-chat supports tools, deepseek-reasoner doesn't)
    - Perplexity: Search-augmented models via OpenAI-compatible API
    - Ollama: Local deployment via OpenAI-compatible API
    - Gemini: Google AI models (gemini-2.0-flash, gemini-1.5-pro, etc.)
    - Qwen: Alibaba Cloud models via DashScope OpenAI-compatible API
    """

    @staticmethod
    def create_llm(
        provider: ProviderType,
        model: str,
        temperature: float,
        max_tokens: int,
        streaming: bool,
        llm_type: str,
        **kwargs: Any,
    ) -> BaseChatModel:
        """
        Create LLM instance with provider-specific configuration.

        Args:
            provider: Provider type (openai, anthropic, deepseek, perplexity, ollama)
            model: Model identifier (e.g., "gpt-4.1-nano", "claude-sonnet-4-5")
            temperature: Temperature parameter (0.0-2.0)
            max_tokens: Maximum tokens to generate
            streaming: Enable streaming responses
            llm_type: LLM type for context (router, response, contacts_agent, planner)
            **kwargs: Additional provider-specific parameters (top_p, frequency_penalty, etc.)

        Returns:
            BaseChatModel: Configured LLM instance

        Raises:
            ValueError: If provider/model combination is invalid or unsupported
            Exception: If LLM instantiation fails (API key issues, network errors, etc.)

        Example:
            >>> llm = ProviderAdapter.create_llm(
            ...     provider="anthropic",
            ...     model="claude-sonnet-4-5",
            ...     temperature=0.5,
            ...     max_tokens=4096,
            ...     streaming=True,
            ...     llm_type="response"
            ... )
        """
        logger.info(
            "creating_llm",
            provider=provider,
            model=model,
            llm_type=llm_type,
            temperature=temperature,
            streaming=streaming,
        )

        # Load advanced provider config (JSON string from LLMAgentConfig)
        provider_config_json = kwargs.pop("provider_config", None) or "{}"
        provider_config = ProviderAdapter._parse_provider_config(provider_config_json, llm_type)
        kwargs.update(provider_config)

        # Validate provider/model compatibility
        ProviderAdapter._validate_provider_model(provider, model, llm_type)

        # DeepSeek: Uses official langchain-deepseek integration
        if provider == "deepseek":
            return ProviderAdapter._create_deepseek_llm(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **kwargs,
            )

        # Gemini: Uses official langchain-google-genai integration
        if provider == "gemini":
            return ProviderAdapter._create_gemini_llm(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **kwargs,
            )

        # OpenAI Responses API: Use for eligible models (40-80% cache improvement)
        # Direct application - no feature flag, automatic fallback to Chat Completions
        if provider == "openai" and is_responses_api_eligible(model):
            return ProviderAdapter._create_openai_responses_llm(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **kwargs,
            )

        # Prepare provider-specific configuration
        # Phase 6: Pass streaming flag for stream_options injection (OpenAI)
        # Phase X: Pass model for reasoning model detection and parameter filtering
        provider_for_init, additional_kwargs, temperature_override = (
            ProviderAdapter._prepare_provider_config(
                provider=provider,
                model=model,
                temperature=temperature,
                streaming=streaming,
                **kwargs,
            )
        )

        # Use temperature override if reasoning model filtering modified it
        # Sentinel value "__OMIT__" means omit the parameter entirely
        if temperature_override == "__OMIT__":
            final_temperature = None
        elif temperature_override is not None:
            final_temperature = temperature_override
        else:
            final_temperature = temperature

        # Cap max_tokens based on provider limits
        # OpenAI models have varying limits: gpt-4.1-mini=16384, gpt-4.1=32768, etc.
        # Use conservative limit of 16384 for mini models, 32768 for others
        if provider == "openai":
            is_mini_model = "mini" in model.lower() or "nano" in model.lower()
            openai_max_tokens_limit = 16384 if is_mini_model else 32768
            if max_tokens > openai_max_tokens_limit:
                logger.warning(
                    "openai_max_tokens_capped",
                    requested=max_tokens,
                    capped_to=openai_max_tokens_limit,
                    model=model,
                    msg=f"max_tokens={max_tokens} exceeds OpenAI limit for {model}, capped to {openai_max_tokens_limit}",
                )
                max_tokens = openai_max_tokens_limit

        # Create LLM using init_chat_model (LangChain 1.0+)
        try:
            llm = init_chat_model(
                model=model,
                model_provider=provider_for_init,
                temperature=final_temperature,
                max_tokens=max_tokens,
                streaming=streaming,
                **additional_kwargs,
            )

            logger.info(
                "llm_created_successfully",
                provider=provider,
                model=model,
                llm_type=llm_type,
            )

            return llm

        except Exception as e:
            logger.error(
                "llm_creation_failed",
                provider=provider,
                model=model,
                llm_type=llm_type,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise

    @staticmethod
    def _create_openai_responses_llm(
        model: str, temperature: float, max_tokens: int, streaming: bool, **kwargs: Any
    ) -> BaseChatModel:
        """
        Create OpenAI LLM using Responses API for enhanced caching.

        The Responses API provides 40-80% better cache utilization compared
        to Chat Completions. Automatic fallback to Chat Completions if the
        Responses API is unavailable (404 errors, regional restrictions).

        Args:
            model: OpenAI model name (gpt-4.1-mini, gpt-5, etc.)
            temperature: Temperature parameter
            max_tokens: Maximum tokens to generate
            streaming: Enable streaming
            **kwargs: Additional parameters (top_p, etc.)

        Returns:
            ResponsesLLM: LangChain-compatible LLM using Responses API
        """
        # Extract reasoning_effort (handled natively by ResponsesLLM)
        reasoning_effort = kwargs.pop("reasoning_effort", None)

        # Extract top_p if provided
        top_p = kwargs.pop("top_p", 1.0)

        # Explicitly pop frequency_penalty and presence_penalty — ResponsesLLM does not
        # accept these fields, so they would be silently discarded via **kwargs.
        # Pop them explicitly to make the contract clear and log non-default values.
        freq_penalty = kwargs.pop("frequency_penalty", None)
        pres_penalty = kwargs.pop("presence_penalty", None)
        if freq_penalty and freq_penalty != 0:
            logger.debug(
                "responses_llm_frequency_penalty_dropped",
                model=model,
                frequency_penalty=freq_penalty,
                msg=f"frequency_penalty={freq_penalty} not supported by ResponsesLLM, dropped",
            )
        if pres_penalty and pres_penalty != 0:
            logger.debug(
                "responses_llm_presence_penalty_dropped",
                model=model,
                presence_penalty=pres_penalty,
                msg=f"presence_penalty={pres_penalty} not supported by ResponsesLLM, dropped",
            )

        logger.info(
            "creating_openai_responses_llm",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            reasoning_effort=reasoning_effort,
            msg="Using OpenAI Responses API for enhanced caching",
        )

        return ResponsesLLM(
            model=model,
            api_key=_require_api_key("openai"),
            organization_id=settings.openai_organization_id,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            store=True,  # Enable caching
            fallback_enabled=True,  # Automatic fallback to Chat Completions
            streaming=streaming,
            reasoning_effort=reasoning_effort,
        )

    @staticmethod
    def _create_deepseek_llm(
        model: str, temperature: float, max_tokens: int, streaming: bool, **kwargs: Any
    ) -> BaseChatModel:
        """
        Create DeepSeek LLM using official langchain-deepseek integration.

        Prompt caching: DeepSeek uses automatic server-side FP8 KV cache (no API flag needed).

        DeepSeek has two models:
        - deepseek-chat (V3): Supports tools, structured output, fast inference
        - deepseek-reasoner (R1): Reasoning model, no tools/structured output support

        Args:
            model: DeepSeek model name ("deepseek-chat" or "deepseek-reasoner")
            temperature: Temperature parameter
            max_tokens: Maximum tokens to generate
            streaming: Enable streaming
            **kwargs: Additional parameters

        Returns:
            ChatDeepSeek: Configured DeepSeek LLM instance

        Raises:
            ImportError: If langchain-deepseek is not installed
        """
        try:
            from langchain_deepseek import ChatDeepSeek  # type: ignore[import-not-found]
        except ImportError as e:
            logger.error(
                "deepseek_import_failed",
                error=str(e),
                msg="Install langchain-deepseek: pip install langchain-deepseek",
            )
            raise ImportError(
                "langchain-deepseek is not installed. "
                "Install it with: pip install langchain-deepseek"
            ) from e

        # Remove parameters not supported by DeepSeek
        kwargs.pop("reasoning_effort", None)  # OpenAI-specific

        # deepseek-reasoner (R1): no sampling parameters supported by the API
        is_reasoner = "reasoner" in model
        if is_reasoner:
            for param in ("top_p", "frequency_penalty", "presence_penalty"):
                kwargs.pop(param, None)
            logger.info(
                "deepseek_reasoner_params_filtered",
                model=model,
                msg="deepseek-reasoner does not support sampling parameters (temperature, top_p, penalties): omitted",
            )

        # DeepSeek V3.2 max_tokens limit: 8192 for deepseek-chat, 64000 for deepseek-reasoner
        deepseek_max_tokens_limit = 64000 if is_reasoner else 8192
        if max_tokens > deepseek_max_tokens_limit:
            logger.warning(
                "deepseek_max_tokens_capped",
                requested=max_tokens,
                capped_to=deepseek_max_tokens_limit,
                model=model,
                msg=f"max_tokens={max_tokens} exceeds DeepSeek limit, capped to {deepseek_max_tokens_limit}",
            )
            max_tokens = deepseek_max_tokens_limit

        if is_reasoner:
            # Temperature not supported for deepseek-reasoner — omit entirely
            return ChatDeepSeek(
                model=model,
                max_tokens=max_tokens,
                streaming=streaming,
                api_key=_require_api_key("deepseek"),
                **kwargs,
            )

        return ChatDeepSeek(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            api_key=_require_api_key("deepseek"),
            **kwargs,
        )

    @staticmethod
    def _create_gemini_llm(
        model: str, temperature: float, max_tokens: int, streaming: bool, **kwargs: Any
    ) -> BaseChatModel:
        """
        Create Gemini LLM using official langchain-google-genai integration.

        Prompt caching: Gemini uses automatic "implicit caching" for prompts >= 32k tokens.
        Explicit Context Caching requires creating CachedContent resources (not applicable here).

        Gemini models (2025):
        - Gemini 3 Series (Preview):
          - gemini-3-pro-preview: Advanced reasoning (preview)

        - Gemini 2.5 Series:
          - gemini-2.5-pro: State-of-the-art, coding & complex reasoning ($1.25/$10 per 1M tokens)
          - gemini-2.5-flash: Fast, large-scale processing, agentic use ($0.30/$2.50 per 1M tokens)
          - gemini-2.5-flash-lite: Cost-effective high-throughput ($0.10/$0.40 per 1M tokens)

        - Gemini 2.0 Series:
          - gemini-2.0-flash: Next-gen features, 1M context ($0.10/$0.40 per 1M tokens)
          - gemini-2.0-flash-lite: Optimized for cost/latency ($0.075/$0.30 per 1M tokens)

        Note: Gemini 1.5 series deprecated as of April 2025.

        Args:
            model: Gemini model name (e.g., "gemini-2.5-flash", "gemini-2.0-flash")
            temperature: Temperature parameter (0.0-2.0)
            max_tokens: Maximum tokens to generate
            streaming: Enable streaming
            **kwargs: Additional parameters

        Returns:
            ChatGoogleGenerativeAI: Configured Gemini LLM instance

        Raises:
            ImportError: If langchain-google-genai is not installed
        """
        try:
            from langchain_google_genai import (  # type: ignore[import-not-found]
                ChatGoogleGenerativeAI,
            )
        except ImportError as e:
            logger.error(
                "gemini_import_failed",
                error=str(e),
                msg="Install langchain-google-genai: pip install langchain-google-genai",
            )
            raise ImportError(
                "langchain-google-genai is not installed. "
                "Install it with: pip install langchain-google-genai"
            ) from e

        # Remove parameters not supported by Gemini
        kwargs.pop("frequency_penalty", None)  # Not supported
        kwargs.pop("presence_penalty", None)  # Not supported

        # Map reasoning_effort to Gemini's native 'thinking_level' parameter
        # Only Gemini 2.5-flash, 2.5-pro, and 3+ support thinking
        # Gemini 2.0-flash, 2.0-flash-lite, 2.5-flash-lite do NOT
        reasoning_effort = kwargs.pop("reasoning_effort", None)
        supports_thinking = (
            bool(re.match(r"^gemini-(2\.5-(flash|pro)|[3-9])", model, re.IGNORECASE))
            and "lite" not in model.lower()
        )
        if reasoning_effort and reasoning_effort not in ("none", "minimal") and supports_thinking:
            thinking_level_mapping = {
                "low": "low",
                "medium": "low",  # Gemini has no "medium", map to "low"
                "high": "high",
            }
            thinking_level = thinking_level_mapping.get(reasoning_effort)
            if thinking_level:
                kwargs["thinking_level"] = thinking_level
                logger.info(
                    "gemini_thinking_level_configured",
                    reasoning_effort=reasoning_effort,
                    mapped_to=thinking_level,
                    msg=f"Mapped reasoning_effort={reasoning_effort} to Gemini thinking_level={thinking_level}",
                )
        elif (
            reasoning_effort
            and reasoning_effort not in ("none", "minimal")
            and not supports_thinking
        ):
            logger.warning(
                "gemini_thinking_not_supported",
                model=model,
                reasoning_effort=reasoning_effort,
                msg=f"Model {model} does not support thinking — reasoning_effort ignored",
            )

        # Extract top_p (Gemini supports it natively via ChatGoogleGenerativeAI)
        top_p = kwargs.pop("top_p", None)

        # Only pass top_p if explicitly set (None is not handled by some providers)
        optional_kwargs: dict[str, Any] = {}
        if top_p is not None:
            optional_kwargs["top_p"] = top_p

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_output_tokens=max_tokens,
            streaming=streaming,
            google_api_key=_require_api_key("gemini"),
            **optional_kwargs,
            **kwargs,
        )

    @staticmethod
    def _prepare_provider_config(
        provider: ProviderType,
        model: str,
        temperature: float,
        streaming: bool = False,
        **kwargs: Any,
    ) -> tuple[str, dict[str, Any], float | str | None]:
        """
        Prepare provider-specific configuration for init_chat_model.

        Handles:
        - API key injection per provider
        - Base URL override for Ollama/Perplexity
        - Provider name mapping (Ollama/Perplexity use OpenAI SDK)
        - Phase 6: Token metadata during streaming (OpenAI stream_options)
        - Phase X: Reasoning model parameter filtering (OpenAI GPT-5/o-series)

        Args:
            provider: Provider type
            model: Model identifier (needed for reasoning model detection)
            temperature: Temperature value (needed for reasoning model validation)
            streaming: Whether streaming is enabled
            **kwargs: Additional parameters to merge

        Returns:
            Tuple of (provider_name_for_init, merged_kwargs, temperature_override)
            temperature_override:
                - None: no change, use original temperature
                - float: use this temperature value
                - "__OMIT__": omit temperature parameter (for reasoning models)
        """
        additional_kwargs = kwargs.copy()
        temperature_override = None  # Track if we need to override temperature

        # Ollama: OpenAI-compatible API with custom base_url
        # Prompt caching: N/A (local inference, no server-side caching)
        if provider == "ollama":
            additional_kwargs["base_url"] = _require_api_key("ollama")
            additional_kwargs["openai_api_key"] = "ollama"  # Dummy key (not used by Ollama)
            provider_for_init = "openai"

        # Perplexity: OpenAI-compatible API with custom base_url
        # Prompt caching: N/A (Perplexity does not expose a caching API)
        elif provider == "perplexity":
            additional_kwargs["base_url"] = "https://api.perplexity.ai"
            additional_kwargs["openai_api_key"] = _require_api_key("perplexity")
            provider_for_init = "openai"

        # Qwen (Alibaba Cloud): OpenAI-compatible API via DashScope
        # Prompt caching: Implicit cache is automatic (≥256 tokens, no flag needed).
        # Explicit cache (follow-up): cache_control in content blocks, ≥1024 tokens.
        elif provider == "qwen":
            additional_kwargs["base_url"] = "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
            additional_kwargs["openai_api_key"] = _require_api_key("qwen")
            provider_for_init = "openai"

            # Build model_kwargs: extra_body (thinking) + stream_options (metrics)
            model_kwargs: dict[str, Any] = {}

            # Streaming: enable token usage metadata (same as OpenAI block)
            if streaming:
                model_kwargs["stream_options"] = {"include_usage": True}

            # Map reasoning_effort → Qwen enable_thinking + thinking_budget (via extra_body)
            reasoning_effort = additional_kwargs.pop("reasoning_effort", None)
            extra_body: dict[str, Any] = {}
            if reasoning_effort and reasoning_effort != "none":
                extra_body["enable_thinking"] = True
                budget_mapping = {"low": 4096, "minimal": 2048, "medium": 16384}
                if reasoning_effort in budget_mapping:
                    extra_body["thinking_budget"] = budget_mapping[reasoning_effort]
                # "high"/"xhigh" → no budget limit (model default = max ~81920)
                logger.info(
                    "qwen_thinking_configured",
                    reasoning_effort=reasoning_effort,
                    thinking_budget=budget_mapping.get(reasoning_effort, "max"),
                    msg=f"Mapped reasoning_effort={reasoning_effort} to Qwen thinking mode",
                )
            elif reasoning_effort == "none":
                extra_body["enable_thinking"] = False
            # If no reasoning_effort set, use model's default (thinking=True for qwen3.5-*)

            if extra_body:
                model_kwargs["extra_body"] = extra_body
            if model_kwargs:
                additional_kwargs["model_kwargs"] = model_kwargs

            # Qwen does NOT support frequency_penalty
            additional_kwargs.pop("frequency_penalty", None)

        # OpenAI: Standard provider (fallback path — eligible models use Responses API above)
        # Prompt caching: Handled by Responses API (store=True) for eligible models;
        # this fallback path uses Chat Completions which has automatic server-side caching
        elif provider == "openai":
            additional_kwargs["openai_api_key"] = _require_api_key("openai")

            # Inject OpenAI Organization ID if configured (required for GPT-5 streaming)
            # Use default_headers to inject OpenAI-Organization header
            if settings.openai_organization_id:
                additional_kwargs["default_headers"] = {
                    "OpenAI-Organization": settings.openai_organization_id
                }
                logger.info(
                    "openai_organization_configured",
                    organization_id=settings.openai_organization_id[:8]
                    + "***",  # Redact for security
                    msg="Using OpenAI-Organization header for GPT-5/verified org access",
                )

            provider_for_init = "openai"

            # Phase 6 - LLM Observability: Enable token metadata during streaming
            if streaming:
                additional_kwargs["model_kwargs"] = {"stream_options": {"include_usage": True}}

            # Reasoning Models Filter: Remove unsupported parameters
            # GPT-5, o1, o3, o4-mini models do NOT support sampling parameters
            # Case-insensitive match for model names
            is_reasoning_model = bool(re.match(REASONING_MODELS_PATTERN, model, re.IGNORECASE))

            # gpt-5.1/5.2+ with effort=none behave as standard models (sampling params allowed)
            reasoning_effort_val = additional_kwargs.get("reasoning_effort")
            is_gpt51_plus_none = (
                is_reasoning_model
                and bool(re.match(r"^gpt-5\.[1-9]", model, re.IGNORECASE))
                and reasoning_effort_val == "none"
            )

            if is_reasoning_model and not is_gpt51_plus_none:
                # Remove unsupported sampling parameters for reasoning models
                unsupported_params = ["top_p", "frequency_penalty", "presence_penalty"]
                removed_params = []

                for param in unsupported_params:
                    if param in additional_kwargs:
                        removed_params.append(f"{param}={additional_kwargs.pop(param)}")

                if removed_params:
                    logger.info(
                        "reasoning_model_params_filtered",
                        model=model,
                        removed=removed_params,
                        msg=(
                            f"Reasoning model {model} does not support sampling parameters: "
                            f"{', '.join(removed_params)}. "
                            "These were automatically removed to prevent API errors."
                        ),
                    )

                # Temperature validation: must be 1 or omitted for reasoning models
                if temperature is not None and temperature != 1.0:
                    logger.warning(
                        "reasoning_model_temperature_fixed",
                        model=model,
                        requested_temperature=temperature,
                        msg=(
                            f"Reasoning model {model} requires temperature=1 or omitted. "
                            f"Requested temperature={temperature} will be omitted."
                        ),
                    )
                    # Use sentinel to signal temperature should be omitted
                    temperature_override = "__OMIT__"

            # Reasoning Effort: ONLY pass for reasoning models (o-series, GPT-5)
            # Standard models (gpt-4, gpt-4.1-mini, gpt-4.1, etc.) do NOT support this parameter
            reasoning_effort = additional_kwargs.get("reasoning_effort")
            if reasoning_effort:
                if is_reasoning_model:
                    logger.info(
                        "reasoning_effort_configured",
                        model=model,
                        reasoning_effort=reasoning_effort,
                        msg=f"Configured reasoning_effort={reasoning_effort} for reasoning model {model}",
                    )
                else:
                    # Remove reasoning_effort for non-reasoning models
                    additional_kwargs.pop("reasoning_effort", None)
                    logger.warning(
                        "reasoning_effort_filtered_non_reasoning_model",
                        model=model,
                        reasoning_effort=reasoning_effort,
                        msg=(
                            f"reasoning_effort={reasoning_effort} is NOT supported by {model}. "
                            "This parameter is ONLY for o-series and GPT-5 reasoning models. "
                            "Removed to prevent API error."
                        ),
                    )

        # Anthropic: Standard provider with prompt caching enabled
        elif provider == "anthropic":
            additional_kwargs["anthropic_api_key"] = _require_api_key("anthropic")
            provider_for_init = "anthropic"

            # Anthropic prompt caching is GA (Generally Available) since late 2024.
            # No beta header required — caching is automatic for prompts >= 1024 tokens.
            # The cache_control kwarg can be passed at invoke time for fine-grained control.
            # Ref: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching

            # Map reasoning_effort to Anthropic's native 'effort' parameter
            # Only claude-3-7-sonnet+ and claude-4.x support extended thinking
            # claude-3-5-sonnet does NOT support effort — skip to avoid API errors
            reasoning_effort = additional_kwargs.pop("reasoning_effort", None)
            supports_thinking = not re.match(r"^claude-3-5", model, re.IGNORECASE)
            if reasoning_effort and reasoning_effort != "none" and supports_thinking:
                # Map our values to Anthropic's supported values
                effort_mapping = {
                    "minimal": "low",
                    "low": "low",
                    "medium": "medium",
                    "high": "high",
                }
                anthropic_effort = effort_mapping.get(reasoning_effort)
                if anthropic_effort:
                    additional_kwargs["effort"] = anthropic_effort
                    logger.info(
                        "anthropic_effort_configured",
                        reasoning_effort=reasoning_effort,
                        mapped_to=anthropic_effort,
                        msg=f"Mapped reasoning_effort={reasoning_effort} to Anthropic effort={anthropic_effort}",
                    )
            elif reasoning_effort and not supports_thinking:
                logger.warning(
                    "anthropic_effort_not_supported",
                    model=model,
                    reasoning_effort=reasoning_effort,
                    msg=f"Model {model} does not support extended thinking — effort parameter ignored",
                )

            # Remove parameters not supported by Anthropic
            additional_kwargs.pop("frequency_penalty", None)  # Not supported
            additional_kwargs.pop("presence_penalty", None)  # Not supported
            # Claude 4.5+ rejects temperature + top_p together — drop top_p
            additional_kwargs.pop("top_p", None)

            # Anthropic temperature range is 0.0-1.0 (not 0.0-2.0 like OpenAI)
            if temperature is not None and temperature > 1.0:
                logger.warning(
                    "anthropic_temperature_capped",
                    requested=temperature,
                    capped_to=1.0,
                    msg=f"Anthropic temperature max is 1.0, capped from {temperature}",
                )
                temperature_override = 1.0

            logger.debug(
                "anthropic_prompt_caching_enabled",
                llm_type=kwargs.get("llm_type", "unknown"),
                msg="Anthropic prompt caching enabled (GA, automatic for prompts >= 1024 tokens)",
            )

        else:
            raise ValueError(f"Unsupported provider: {provider}")

        return provider_for_init, additional_kwargs, temperature_override

    @staticmethod
    def _parse_provider_config(config_json: str, llm_type: str) -> dict[str, Any]:
        """
        Parse advanced provider configuration from JSON string.

        The JSON string comes from LLMAgentConfig.provider_config (code defaults
        or DB override via admin UI).

        Args:
            config_json: JSON string with provider-specific config
            llm_type: LLM type for logging context

        Returns:
            dict: Parsed configuration dict (empty if invalid JSON)
        """
        try:
            return json.loads(config_json)
        except json.JSONDecodeError as e:
            logger.warning(
                "invalid_provider_config_json",
                llm_type=llm_type,
                config_json=config_json,
                error=str(e),
            )
            return {}

    @staticmethod
    def _validate_provider_model(provider: ProviderType, model: str, llm_type: str) -> None:
        """
        Validate provider/model combination for compatibility.

        Validation rules:
        - deepseek-reasoner: Does NOT support tools or structured output
          → Reject for contacts_agent (requires tools)
          → Warn for router/planner (requires structured output or JSON mode)
        - Ollama/Perplexity: Model-dependent tool support
          → Warn for contacts_agent

        Args:
            provider: Provider type
            model: Model name
            llm_type: LLM type

        Raises:
            ValueError: If combination is incompatible
        """
        # Tool-using agent names (includes new unified names and deprecated aliases)
        tool_using_agents = {
            # New unified names (domain_agent pattern)
            "contact_agent",
            "email_agent",
            "event_agent",
            "file_agent",
            "task_agent",
            "place_agent",
            "route_agent",
            "weather_agent",
            "wikipedia_agent",
            "perplexity_agent",
            "query_agent",
            # Deprecated aliases (for backward compatibility)
            "contacts_agent",
            "emails_agent",
            "calendar_agent",
            "drive_agent",
            "tasks_agent",
            "places_agent",
            "routes_agent",
        }

        # DeepSeek-Reasoner validation
        if provider == "deepseek" and model == "deepseek-reasoner":
            if llm_type in tool_using_agents:
                raise ValueError(
                    f"{llm_type} requires tool support. "
                    "deepseek-reasoner does NOT support tools. "
                    "Use deepseek-chat instead."
                )

            if llm_type in ["router", "planner"]:
                logger.warning(
                    "deepseek_reasoner_no_structured_output",
                    llm_type=llm_type,
                    msg="deepseek-reasoner does NOT support structured output. "
                    f"{llm_type} may fail if it requires structured output. "
                    "Consider using deepseek-chat instead.",
                )

        # Ollama/Perplexity tool support warning
        if provider in ["ollama", "perplexity"] and llm_type in tool_using_agents:
            logger.warning(
                "provider_model_dependent_tool_support",
                provider=provider,
                model=model,
                llm_type=llm_type,
                msg=f"{provider} has model-dependent tool support. "
                f"Verify that {model} supports tool calling for {llm_type}.",
            )
