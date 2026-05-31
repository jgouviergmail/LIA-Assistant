"""
LLM Agent Configuration - Unified configuration for all LLM-based agents.

This module provides a centralized configuration structure for LLM agents,
eliminating redundancy and simplifying the addition of new agents.

ADR: Architecture Decision Record
- Decision: Centralize LLM configuration to avoid 42+ redundant settings
- Impact: 57% reduction in config lines (350 → 150), easier agent additions
- Migration: Gradual, backward-compatible via property accessors
"""

from typing import Literal

from pydantic import BaseModel, Field

from src.core.reasoning_types import ReasoningEffortValue


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

    # Reasoning effort override. Shape determined by the model's reasoning_widget
    # on llm_models (validated at the service layer, NOT here — strict check
    # happens in domains/llm_config/reasoning_validation.py once Task 5 lands).
    reasoning_effort: ReasoningEffortValue = Field(
        default=None,
        description=(
            "Reasoning effort override. Shape depends on the model's reasoning_widget. "
            "None = no override (model default applies). "
            "Validation strictness lives at the service layer, not on this Pydantic field."
        ),
    )

    effort: str | None = Field(
        default=None,
        description=(
            "Global effort override (Anthropic output_config.effort), distinct from "
            "reasoning_effort. Allowed values come from the model's effort_values "
            "(currently opus-4-5 only). None = model default (high)."
        ),
    )

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
