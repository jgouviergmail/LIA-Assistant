"""
LLM Agent Configuration - Unified configuration for all LLM-based agents.

This module provides a centralized configuration structure for LLM agents,
eliminating redundancy and simplifying the addition of new agents.

ADR: Architecture Decision Record
- Decision: Centralize LLM configuration to avoid 42+ redundant settings
- Impact: 57% reduction in config lines (350 → 150), easier agent additions
- Migration: Gradual, backward-compatible via property accessors
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.core.constants import REASONING_MODELS_PATTERN
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class LLMAgentConfig(BaseModel):
    """
    Unified LLM configuration for all agents.

    This class replaces the pattern of having 6+ separate fields per agent
    (model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty).

    Example:
        >>> config = LLMAgentConfig(
        ...     provider="openai",
        ...     model="gpt-4.1-mini",
        ...     temperature=0.5,
        ...     max_tokens=10000,
        ... )

    Benefits:
        - Single source of truth for LLM parameters
        - Type-safe with Pydantic validation
        - Easy to extend with new parameters
        - Consistent validation across all agents
    """

    # Provider configuration
    provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini", "qwen"
    ] = Field(
        default="openai",
        description="LLM provider",
    )
    provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config (JSON string)",
    )

    # Model parameters (core 6 settings shared by all agents)
    model: str = Field(
        description="LLM model name (e.g., gpt-4.1-mini, claude-3-opus)",
    )
    temperature: float = Field(
        ge=0.0,
        le=2.0,
        description="Temperature for LLM (0.0 = deterministic, 2.0 = creative)",
    )
    top_p: float = Field(
        ge=0.0,
        le=1.0,
        description="Nucleus sampling (1.0 = disabled, use temperature)",
    )
    frequency_penalty: float = Field(
        ge=-2.0,
        le=2.0,
        description="Frequency penalty (reduce repetition)",
    )
    presence_penalty: float = Field(
        ge=-2.0,
        le=2.0,
        description="Presence penalty (encourage diversity)",
    )
    max_tokens: int = Field(
        gt=0,
        description="Maximum tokens for LLM output",
    )

    # Optional timeout
    timeout_seconds: float | None = Field(
        default=None,
        gt=0.0,
        description="Timeout for LLM call (optional, inherits from agent default)",
    )

    # Reasoning effort level (OpenAI o-series and GPT-5 models only)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = Field(
        default=None,
        description=(
            "Reasoning effort level for reasoning models. Controls depth of thinking:\n"
            "OpenAI o-series (o1, o3, o3-mini, o4-mini): low/medium/high. o1-mini: unsupported.\n"
            "OpenAI GPT-5/5-mini: minimal/low/medium/high.\n"
            "OpenAI GPT-5.1: low/medium/high.\n"
            "OpenAI GPT-5.2: none/minimal/low/medium/high/xhigh.\n"
            "Anthropic (via effort param): low/medium/high.\n"
            "- none: Disables reasoning (GPT-5.2 only, enables temperature)\n"
            "- minimal: Few reasoning tokens, fastest (GPT-5 family only)\n"
            "- low: Faster inference, lower cost\n"
            "- medium: Balanced trade-off (default)\n"
            "- high: Maximum reasoning depth\n"
            "- xhigh: Extended reasoning (GPT-5.2 only)"
        ),
    )

    @field_validator("reasoning_effort", mode="after")
    @classmethod
    def validate_reasoning_effort(cls, v: str | None, info: Any) -> str | None:
        """
        Validate reasoning_effort is only used with compatible OpenAI models.

        This validator ensures:
        1. reasoning_effort is only set for OpenAI provider
        2. Warning is logged if used with non-reasoning models
        3. No blocking errors (graceful degradation)

        Args:
            v: reasoning_effort value (low/medium/high or None)
            info: Pydantic validation context with access to other fields

        Returns:
            The validated reasoning_effort value (unchanged)

        Note:
            This is a non-blocking validator. It logs warnings but allows
            the configuration to proceed even if misused, as the provider
            adapter will handle parameter injection appropriately.
        """
        if v is None:
            return v

        # Get provider and model from validation context
        provider = info.data.get("provider")
        model = info.data.get("model", "")

        # Validation 1: Check provider supports reasoning_effort
        # OpenAI (o-series, GPT-5), Anthropic (effort param), Gemini (thinking_level),
        # Qwen (enable_thinking + thinking_budget)
        supported_providers = {"openai", "anthropic", "gemini", "qwen"}
        if provider not in supported_providers:
            logger.warning(
                "reasoning_effort_unsupported_provider",
                provider=provider,
                reasoning_effort=v,
                msg=f"reasoning_effort parameter is only supported for OpenAI, Anthropic, "
                f"and Gemini providers, got provider={provider}. "
                f"This parameter will be ignored.",
            )
            return v

        # Validation 2: For OpenAI only, check if model is a reasoning model
        # Other providers (Anthropic, Gemini, Qwen) handle reasoning_effort natively
        # via their own mapping in the adapter — no model-name validation needed.
        if provider == "openai":
            import re

            is_reasoning_model = bool(re.match(REASONING_MODELS_PATTERN, model, re.IGNORECASE))

            if not is_reasoning_model:
                logger.debug(
                    "reasoning_effort_auto_cleared",
                    model=model,
                    reasoning_effort=v,
                    msg=f"reasoning_effort cleared: model={model} is not a reasoning model.",
                )
                return None

        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "temperature": 0.5,
                    "top_p": 1.0,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0,
                    "max_tokens": 10000,
                },
                {
                    "provider": "openai",
                    "model": "o3-mini",
                    "temperature": 0.3,
                    "top_p": 1.0,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0,
                    "max_tokens": 4096,
                    "reasoning_effort": "low",
                },
                {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0,
                    "max_tokens": 2048,
                    "reasoning_effort": "minimal",
                },
            ]
        }
    }
