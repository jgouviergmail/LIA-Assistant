"""
LLM Configuration Admin database models.

Two tables for dynamic LLM configuration management:
- provider_api_keys: Encrypted API keys per LLM provider (sole source of truth)
- llm_config_overrides: Per-LLM-type config overrides (override code defaults)

Created: 2026-03-08
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class ProviderApiKey(BaseModel):
    """
    Encrypted API key for an LLM provider.

    Sole source of truth for provider API keys (Fernet encrypted).
    Managed via Admin UI (Settings > Administration > LLM Configuration).

    Attributes:
        provider: Provider identifier (e.g., "openai", "anthropic", "gemini")
        encrypted_key: Fernet-encrypted API key (or base_url for Ollama)
        updated_by: Admin user ID who last updated the key
    """

    __tablename__ = "provider_api_keys"

    provider: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    encrypted_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<ProviderApiKey(provider={self.provider})>"


class LLMConfigOverride(BaseModel):
    """
    Per-LLM-type configuration override.

    All fields are nullable: None means "use code default" (LLM_DEFAULTS).
    Resolution: LLM_DEFAULTS (code) -> DB override (if exists) -> Effective config.

    Attributes:
        llm_type: LLM type identifier (e.g., "router", "response", "planner")
        provider: Provider override (e.g., "openai", "anthropic")
        model: Model override (e.g., "gpt-4.1-mini")
        temperature: Temperature override (0.0-2.0)
        top_p: Top-p override (0.0-1.0)
        frequency_penalty: Frequency penalty override (-2.0 to 2.0)
        presence_penalty: Presence penalty override (-2.0 to 2.0)
        max_tokens: Max tokens override
        timeout_seconds: Timeout override in seconds
        reasoning_effort: Reasoning effort override (e.g., "low", "medium", "high")
        provider_config: Provider-specific JSON config override
        updated_by: Admin user ID who last updated the override
    """

    __tablename__ = "llm_config_overrides"

    llm_type: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
        index=True,
    )

    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    temperature: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    top_p: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    frequency_penalty: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    presence_penalty: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    max_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    timeout_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    reasoning_effort: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    provider_config: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<LLMConfigOverride(llm_type={self.llm_type})>"
