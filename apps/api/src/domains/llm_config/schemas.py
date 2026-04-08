"""
LLM Configuration Admin API schemas.

Pydantic models for request/response validation in the LLM config admin API.

Created: 2026-03-08
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.llm_agent_config import LLMAgentConfig

# --- Provider Keys ---


class ProviderKeyStatus(BaseModel):
    """Status of a provider's API key configuration."""

    provider: str
    display_name: str
    has_db_key: bool
    masked_key: str | None = None  # "sk-...abc" (last 4 chars)
    updated_at: datetime | None = None


class ProviderKeysResponse(BaseModel):
    """Response for listing all provider key statuses."""

    providers: list[ProviderKeyStatus]


class ProviderKeyUpdate(BaseModel):
    """Request to update a provider's API key."""

    key: str = Field(min_length=1, max_length=500)


# --- LLM Type Config ---


class LLMTypeInfo(BaseModel):
    """Metadata for an LLM type (static, from registry)."""

    llm_type: str
    display_name: str
    category: str
    description_key: str
    required_capabilities: list[str]
    power_tier: str | None = Field(
        None,
        description="Visual power tier indicator: critical, high, medium, low, or null",
    )


class LLMTypeConfig(BaseModel):
    """Complete config view for a single LLM type."""

    llm_type: str
    info: LLMTypeInfo
    effective: LLMAgentConfig  # Merged: defaults + overrides
    overrides: dict[str, Any]  # Non-null override fields from DB
    defaults: LLMAgentConfig  # Code constants (LLM_DEFAULTS)
    is_overridden: bool  # True if at least one DB override exists


class LLMTypeConfigUpdate(BaseModel):
    """Request to update an LLM type's config (full replace semantics).

    Each PUT replaces the entire override row. null = use code default.
    The frontend always sends the complete state of overrides.
    """

    provider: (
        Literal["openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini", "qwen"] | None
    ) = None
    model: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    frequency_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    presence_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    max_tokens: int | None = Field(None, gt=0)
    timeout_seconds: int | None = Field(None, gt=0)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    provider_config: str | None = None


class LLMConfigListResponse(BaseModel):
    """Response for listing all LLM type configs."""

    configs: list[LLMTypeConfig]


# --- Metadata (static) ---


class ModelCapabilities(BaseModel):
    """Capabilities metadata for a single model."""

    model_id: str
    max_output_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    supports_vision: bool
    is_reasoning_model: bool
    is_image_model: bool = False
    cost_input: float | None = None
    cost_output: float | None = None


class ProviderModelsMetadata(BaseModel):
    """Available models grouped by provider."""

    providers: dict[str, list[ModelCapabilities]]


# --- Ollama dynamic discovery ---


class OllamaModelCapabilities(ModelCapabilities):
    """Extended capabilities for a dynamically discovered Ollama model."""

    size: str | None = None  # e.g. "8B", "70B"
    family: str | None = None  # e.g. "llama", "qwen2"


class OllamaModelsResponse(BaseModel):
    """Response for dynamically discovered Ollama models.

    ``source`` indicates whether models were fetched live from the Ollama
    server ("live") or fell back to static profiles ("fallback").
    """

    models: list[OllamaModelCapabilities]
    source: Literal["live", "fallback"]
