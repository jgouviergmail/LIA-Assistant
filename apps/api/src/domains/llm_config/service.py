"""
LLM Configuration Admin Service.

Handles CRUD operations for provider API keys and LLM type config overrides.
Uses AdminAuditLog for tracking all admin actions.

Created: 2026-03-08
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_PROVIDERS, LLM_TYPES_REGISTRY
from src.domains.llm_config.models import LLMConfigOverride, ProviderApiKey
from src.domains.llm_config.schemas import (
    LLMTypeConfig,
    LLMTypeConfigUpdate,
    LLMTypeInfo,
    ModelCapabilities,
    OllamaModelCapabilities,
    OllamaModelsResponse,
    ProviderKeysResponse,
    ProviderKeyStatus,
    ProviderModelsMetadata,
)
from src.domains.users.models import AdminAuditLog
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from fastapi import Request

    from src.core.llm_agent_config import LLMAgentConfig

logger = get_logger(__name__)


def _mask_key(key: str) -> str:
    """Mask an API key, showing only last 4 characters."""
    if len(key) <= 4:
        return "****"
    return f"{'*' * min(8, len(key) - 4)}...{key[-4:]}"


def _merge_config(defaults: LLMAgentConfig, overrides: dict[str, Any]) -> LLMAgentConfig:
    """Merge DB overrides onto code defaults, producing effective config.

    Delegates to the canonical implementation in llm_config_helper.
    """
    if not overrides:
        return defaults
    from src.core.llm_config_helper import merge_config as _merge_impl

    return _merge_impl(defaults, overrides)


class LLMConfigService:
    """Service for managing LLM configuration overrides and provider API keys."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- Provider API Keys ---

    async def get_all_provider_keys(self) -> ProviderKeysResponse:
        """List status of all known providers' API keys (DB only)."""
        result = await self.db.execute(select(ProviderApiKey))
        db_keys = {row.provider: row for row in result.scalars().all()}

        providers = []
        for provider_key, display_name in LLM_PROVIDERS.items():
            db_row = db_keys.get(provider_key)

            masked = None
            if db_row:
                try:
                    decrypted = decrypt_data(db_row.encrypted_key)
                    masked = _mask_key(decrypted)
                except Exception:
                    masked = "****"

            providers.append(
                ProviderKeyStatus(
                    provider=provider_key,
                    display_name=display_name,
                    has_db_key=db_row is not None,
                    masked_key=masked,
                    updated_at=db_row.updated_at if db_row else None,
                )
            )

        return ProviderKeysResponse(providers=providers)

    async def update_provider_key(
        self,
        provider: str,
        key: str,
        admin_user_id: UUID,
        request: Request,
    ) -> None:
        """Create or update a provider's API key (encrypted)."""
        if provider not in LLM_PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")

        encrypted = encrypt_data(key)

        result = await self.db.execute(
            select(ProviderApiKey).where(ProviderApiKey.provider == provider)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.encrypted_key = encrypted
            existing.updated_by = admin_user_id
        else:
            self.db.add(
                ProviderApiKey(
                    provider=provider,
                    encrypted_key=encrypted,
                    updated_by=admin_user_id,
                )
            )

        self._log_audit(
            admin_user_id,
            "provider_api_key_updated",
            "provider_api_key",
            request,
            details={"provider": provider},
        )

        await self.db.commit()
        await LLMConfigOverrideCache.invalidate_and_reload(self.db)

    async def delete_provider_key(
        self,
        provider: str,
        admin_user_id: UUID,
        request: Request,
    ) -> None:
        """Delete a provider's API key. The provider will be unavailable until reconfigured."""
        if provider not in LLM_PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")

        await self.db.execute(delete(ProviderApiKey).where(ProviderApiKey.provider == provider))

        self._log_audit(
            admin_user_id,
            "provider_api_key_deleted",
            "provider_api_key",
            request,
            details={"provider": provider},
        )

        await self.db.commit()
        await LLMConfigOverrideCache.invalidate_and_reload(self.db)

    # --- LLM Type Configs ---

    async def get_all_configs(self) -> list[LLMTypeConfig]:
        """Get all LLM type configs with effective values (defaults + overrides)."""
        result = await self.db.execute(select(LLMConfigOverride))
        db_overrides = {row.llm_type: row for row in result.scalars().all()}

        configs = []
        for llm_type, metadata in LLM_TYPES_REGISTRY.items():
            defaults = LLM_DEFAULTS.get(llm_type)
            if not defaults:
                continue

            db_row = db_overrides.get(llm_type)
            overrides = self._extract_overrides(db_row) if db_row else {}
            effective = _merge_config(defaults, overrides)

            configs.append(
                LLMTypeConfig(
                    llm_type=llm_type,
                    info=LLMTypeInfo(
                        llm_type=metadata.llm_type,
                        display_name=metadata.display_name,
                        category=metadata.category,
                        description_key=metadata.description_key,
                        required_capabilities=metadata.required_capabilities,
                    ),
                    effective=effective,
                    overrides=overrides,
                    defaults=defaults,
                    is_overridden=bool(overrides),
                )
            )

        return configs

    async def get_config(self, llm_type: str) -> LLMTypeConfig:
        """Get a single LLM type config."""
        if llm_type not in LLM_TYPES_REGISTRY:
            raise ValueError(f"Unknown LLM type: {llm_type}")

        metadata = LLM_TYPES_REGISTRY[llm_type]
        defaults = LLM_DEFAULTS[llm_type]

        result = await self.db.execute(
            select(LLMConfigOverride).where(LLMConfigOverride.llm_type == llm_type)
        )
        db_row = result.scalar_one_or_none()
        overrides = self._extract_overrides(db_row) if db_row else {}
        effective = _merge_config(defaults, overrides)

        return LLMTypeConfig(
            llm_type=llm_type,
            info=LLMTypeInfo(
                llm_type=metadata.llm_type,
                display_name=metadata.display_name,
                category=metadata.category,
                description_key=metadata.description_key,
                required_capabilities=metadata.required_capabilities,
            ),
            effective=effective,
            overrides=overrides,
            defaults=defaults,
            is_overridden=bool(overrides),
        )

    async def update_config(
        self,
        llm_type: str,
        update: LLMTypeConfigUpdate,
        admin_user_id: UUID,
        request: Request,
    ) -> LLMTypeConfig:
        """Update an LLM type's config (full replace semantics)."""
        if llm_type not in LLM_TYPES_REGISTRY:
            raise ValueError(f"Unknown LLM type: {llm_type}")

        result = await self.db.execute(
            select(LLMConfigOverride).where(LLMConfigOverride.llm_type == llm_type)
        )
        existing = result.scalar_one_or_none()

        update_data = update.model_dump(exclude_unset=False)

        if existing:
            for field_name, value in update_data.items():
                setattr(existing, field_name, value)
            existing.updated_by = admin_user_id
        else:
            self.db.add(
                LLMConfigOverride(
                    llm_type=llm_type,
                    updated_by=admin_user_id,
                    **update_data,
                )
            )

        self._log_audit(
            admin_user_id,
            "llm_config_updated",
            "llm_config_override",
            request,
            details={"llm_type": llm_type, "overrides": update_data},
        )

        await self.db.commit()
        await LLMConfigOverrideCache.invalidate_and_reload(self.db)

        return await self.get_config(llm_type)

    async def reset_config(
        self,
        llm_type: str,
        admin_user_id: UUID,
        request: Request,
    ) -> LLMTypeConfig:
        """Reset an LLM type to code defaults (delete DB override row)."""
        if llm_type not in LLM_TYPES_REGISTRY:
            raise ValueError(f"Unknown LLM type: {llm_type}")

        await self.db.execute(
            delete(LLMConfigOverride).where(LLMConfigOverride.llm_type == llm_type)
        )

        self._log_audit(
            admin_user_id,
            "llm_config_reset",
            "llm_config_override",
            request,
            details={"llm_type": llm_type},
        )

        await self.db.commit()
        await LLMConfigOverrideCache.invalidate_and_reload(self.db)

        return await self.get_config(llm_type)

    # --- Metadata ---

    @staticmethod
    def get_provider_models() -> ProviderModelsMetadata:
        """Get available models grouped by provider (from FALLBACK_PROFILES)."""
        from src.infrastructure.llm.model_profiles import FALLBACK_PROFILES

        providers: dict[str, list[ModelCapabilities]] = {}
        for provider, models in FALLBACK_PROFILES.items():
            caps = []
            for model_id, profile in models.items():
                # Skip internal "default" fallback entry — not a real model
                if model_id == "default":
                    continue
                caps.append(
                    ModelCapabilities(
                        model_id=model_id,
                        max_output_tokens=profile.max_output_tokens,
                        supports_tools=profile.supports_tool_calling,
                        supports_structured_output=profile.supports_structured_output,
                        supports_vision=profile.supports_vision,
                        is_reasoning_model=profile.is_reasoning_model,
                        cost_input=(
                            profile.cost_per_1m_input
                            if profile.cost_per_1m_input is not None
                            else None
                        ),
                        cost_output=(
                            profile.cost_per_1m_output
                            if profile.cost_per_1m_output is not None
                            else None
                        ),
                    )
                )
            providers[provider] = caps

        return ProviderModelsMetadata(providers=providers)

    @staticmethod
    async def get_ollama_models() -> OllamaModelsResponse:
        """Get Ollama models via dynamic discovery with fallback to static profiles.

        When Ollama is reachable, capabilities come from the server itself
        (via ``/api/show``), not from static profile guesses.
        """
        from src.infrastructure.llm.model_profiles import FALLBACK_PROFILES
        from src.infrastructure.llm.providers.ollama_discovery import discover_ollama_models

        discovered = await discover_ollama_models()

        if discovered:
            # Live: capabilities come directly from Ollama /api/show
            models = []
            for info in discovered:
                caps = info.capabilities
                models.append(
                    OllamaModelCapabilities(
                        model_id=info.name,
                        max_output_tokens=8192,  # Ollama doesn't expose this; safe default
                        supports_tools="tools" in caps,
                        supports_structured_output="tools"
                        in caps,  # Tool-capable models support JSON mode
                        supports_vision="vision" in caps,
                        is_reasoning_model="thinking" in caps,
                        cost_input=0.0,  # Local = free
                        cost_output=0.0,
                        size=info.size,
                        family=info.family,
                    )
                )
            return OllamaModelsResponse(models=models, source="live")

        # Fallback: Ollama unreachable, return static profiles (without "default")
        ollama_profiles = FALLBACK_PROFILES.get("ollama", {})
        models = []
        for model_id, profile in ollama_profiles.items():
            if model_id == "default":
                continue
            models.append(
                OllamaModelCapabilities(
                    model_id=model_id,
                    max_output_tokens=profile.max_output_tokens,
                    supports_tools=profile.supports_tool_calling,
                    supports_structured_output=profile.supports_structured_output,
                    supports_vision=profile.supports_vision,
                    is_reasoning_model=profile.is_reasoning_model,
                    cost_input=profile.cost_per_1m_input,
                    cost_output=profile.cost_per_1m_output,
                    size=None,
                    family=None,
                )
            )
        return OllamaModelsResponse(models=models, source="fallback")

    # --- Internal ---

    @staticmethod
    def _extract_overrides(db_row: LLMConfigOverride) -> dict[str, Any]:
        """Extract non-null override fields from a DB row."""
        from src.domains.llm_config.cache import OVERRIDE_FIELDS

        overrides: dict[str, Any] = {}
        for field in OVERRIDE_FIELDS:
            value = getattr(db_row, field, None)
            if value is not None:
                overrides[field] = value
        return overrides

    def _log_audit(
        self,
        admin_user_id: UUID,
        action: str,
        resource_type: str,
        request: Request,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Create an audit log entry for an admin action."""
        audit_entry = AdminAuditLog(
            admin_user_id=admin_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=None,
            details=details,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        self.db.add(audit_entry)
