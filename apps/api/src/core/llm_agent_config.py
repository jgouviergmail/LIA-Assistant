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

from src.core.reasoning_intent import ReasoningIntent, intent_from_legacy, is_intent_shape


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
        "openai",
        "anthropic",
        "deepseek",
        "perplexity",
        "ollama",
        "gemini",
        "qwen",
        "elevenlabs",
        "edge",
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

    # Reasoning override, in ONE shape whatever the provider (ADR-245). The
    # ladder is ordinal and provider-independent; each family's translator turns
    # it into that provider's kwargs, coercing to the nearest level the model
    # actually accepts. There is nothing left to validate about the SHAPE -- the
    # Literal on ``ReasoningIntent.level`` rejects an unknown level here, and the
    # service layer only checks membership of the model's ladder.
    reasoning_effort: ReasoningIntent | None = Field(
        default=None,
        description=(
            "Reasoning override. None = no override (the model's own default "
            "applies). One shape for every provider; see ReasoningIntent."
        ),
    )

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _accept_legacy_reasoning_shapes(cls, value: Any) -> Any:
        """Read the four shapes ADR-245 replaced, so no deployment needs a flag day.

        ``llm_config_overrides.reasoning_effort`` still holds
        ``{"effort": "off"}``, ``{"enabled": false}`` and their siblings until
        the migration runs -- and it runs per instance, at whatever moment that
        instance is deployed. Without this, taking the code before running the
        migration would make EVERY override row fail validation at read time:
        a total outage, on a schedule nobody chose.

        With it, the code reads both formats and the migration becomes what it
        should be -- a cleanup that removes the need for this shim, not a
        synchronisation point between a deployment and a database.
        """
        if value is None or isinstance(value, ReasoningIntent):
            return value
        if not isinstance(value, dict):
            # Anything else is Pydantic's problem, and it should be: the legacy
            # shapes were STORED shapes, and a database gives dicts. The four
            # Pydantic classes that used to model them no longer exist, so a
            # branch for them here would be unreachable by construction.
            return value
        # An intent-shaped dict is handed to Pydantic UNTOUCHED so the
        # ``Literal`` on ``level`` still rejects a typo. Only the shapes the
        # Literal cannot describe go through the mapper.
        return value if is_intent_shape(value) else intent_from_legacy(value)

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
                    "reasoning_effort": {"effort": "low"},
                },
                {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0,
                    "max_tokens": 2048,
                    "reasoning_effort": {"effort": "minimal"},
                },
            ]
        }
    }
