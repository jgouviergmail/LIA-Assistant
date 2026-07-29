"""
LLM Configuration Admin Service.

Handles CRUD operations for provider API keys and LLM type config overrides.
Uses AdminAuditLog for tracking all admin actions.

Created: 2026-03-08
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import raise_structured_validation_error
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


# Capability vocabulary understood by the checker. LLM_TYPES_REGISTRY entries
# must only use these strings — an unknown capability passes silently (True),
# which is how the 'tool_calling' vs 'tools' drift shipped unverified.
# Locked by tests/unit/domains/llm_config/test_capability_checks.py.
_CAPABILITY_CHECKS: dict[str, Callable[[ModelCapabilities], bool]] = {
    "vision": lambda caps: caps.supports_vision,
    "tools": lambda caps: caps.supports_tools,
    "structured_output": lambda caps: caps.supports_structured_output,
}
KNOWN_MODEL_CAPABILITIES = frozenset(_CAPABILITY_CHECKS)


def _model_has_capability(caps: ModelCapabilities, capability: str) -> bool:
    """Check whether a ``ModelCapabilities`` declares the given capability.

    Knows ``"vision"``, ``"tools"`` and ``"structured_output"``; any other
    string is not filtered (returns True).
    """
    check = _CAPABILITY_CHECKS.get(capability)
    return check(caps) if check else True


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
                        power_tier=metadata.power_tier,
                        required_kind=metadata.required_kind.value,
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
                power_tier=metadata.power_tier,
                required_kind=metadata.required_kind.value,
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

        # === Strict validation of reasoning_effort against the model's matrix ===
        # Replaces the old regex-based auto-clearing logic. The new policy
        # (philosophy A — raw truth) rejects any (model, reasoning_effort)
        # combination not declared in llm_models.reasoning_widget /
        # reasoning_enum_values / reasoning_budget_range with HTTP 422 +
        # structured ctx (see domains/llm_config/reasoning_validation.py).
        if update.model is not None and update.reasoning_effort is not None:
            from src.domains.llm_config.reasoning_validation import (
                validate_reasoning_effort,
            )
            from src.infrastructure.llm.model_capabilities_cache import (
                ModelCapabilitiesCache,
            )

            caps = ModelCapabilitiesCache.get(update.model)
            if caps is None:
                raise_structured_validation_error(
                    error_type="unknown_model",
                    loc=["body", "model"],
                    msg=f"Model {update.model!r} is not in the catalogue.",
                    input_value=update.model,
                    ctx={"model": update.model},
                )
            validate_reasoning_effort(caps, update.reasoning_effort)

            # Coherence rule (Anthropic): extended thinking is incompatible with a
            # custom temperature/top_p (API: "temperature may only be set to 1 when
            # thinking is enabled"). When the selected reasoning_effort enables
            # thinking, force temperature/top_p to None so the stored config stays
            # coherent. The admin UI mirrors this by locking those fields; the
            # factory also omits them at call time (defense in depth).
            if update.provider == "anthropic":
                from src.infrastructure.llm.providers.reasoning_builders import (
                    build_anthropic_reasoning,
                )

                thinking_on = "thinking" in build_anthropic_reasoning(
                    update.reasoning_effort, update.model
                )
                if thinking_on and (update.temperature is not None or update.top_p is not None):
                    logger.info(
                        "anthropic_reasoning_temperature_locked",
                        llm_type=llm_type,
                        model=update.model,
                        msg=(
                            "Reasoning enabled → temperature/top_p forced to None "
                            "(Anthropic API constraint)"
                        ),
                    )
                    update.temperature = None
                    update.top_p = None

        # === Validate the separate global 'effort' (Anthropic opus-4-5) ===
        if update.model is not None and update.effort is not None:
            from src.infrastructure.llm.model_capabilities_cache import (
                ModelCapabilitiesCache,
            )

            caps = ModelCapabilitiesCache.get(update.model)
            allowed = getattr(caps, "effort_values", None) if caps else None
            if not allowed or update.effort not in allowed:
                raise_structured_validation_error(
                    error_type="invalid_effort",
                    loc=["body", "effort"],
                    msg=(
                        f"Effort {update.effort!r} is not supported by "
                        f"{update.model}. Allowed: {', '.join(allowed) if allowed else 'none'}."
                    ),
                    input_value=update.effort,
                    ctx={
                        "model": update.model,
                        "provided": update.effort,
                        "allowed": list(allowed or []),
                    },
                )

        update_data = update.model_dump(exclude_unset=False)

        # === Thinking × completion-budget coherence (systemic lock) ===
        # Reasoning tokens are billed inside max_tokens. Validated on the
        # EFFECTIVE config (pending override merged onto code defaults with the
        # same merge_config the runtime uses), because the incident shape is
        # precisely "set effort=high, leave max_tokens empty → inherit a
        # pre-thinking default" (prod 2026-07-29, telephony_synthesis: 600-token
        # cap fully consumed by reasoning, every call report degraded).
        from src.domains.llm_config.reasoning_validation import (
            validate_thinking_token_budget,
        )

        pending_overrides = {k: v for k, v in update_data.items() if v is not None}
        validate_thinking_token_budget(
            llm_type=llm_type,
            effective=_merge_config(LLM_DEFAULTS[llm_type], pending_overrides),
            floor=settings.llm_thinking_max_tokens_floor,
        )

        result = await self.db.execute(
            select(LLMConfigOverride).where(LLMConfigOverride.llm_type == llm_type)
        )
        existing = result.scalar_one_or_none()

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
    def get_provider_models(
        kinds: list[str] | None = None,
        capability: str | None = None,
    ) -> ProviderModelsMetadata:
        """Get available models grouped by provider.

        Both chat and image-generation models are sourced from DB-backed
        in-memory caches:
        - Chat models → :class:`ModelCapabilitiesCache` (from
          ``llm_models``, populated at boot).
        - Image-generation models →
          :class:`ImageOptionsCache.get_models_grouped_by_provider`
          (DISTINCT on ``image_generation_pricing``).

        Cost fields are intentionally None: pricing lives in separate
        caches consumed by ``AsyncPricingService`` and
        ``ImageGenerationPricingService``, not surfaced here.

        Args:
            kinds: Optional filter on ``ModelCapabilities.kind``. When
                provided, only models whose kind is in the set are
                returned. Default ``None`` = no filter (all kinds).
                The Configuration LLM admin UI passes
                ``[required_kind]`` from ``LLMTypeMetadata``.
            capability: Optional capability filter (currently only
                ``"vision"`` is meaningful — filters to models with
                ``supports_vision=True``).
        """
        from src.domains.image_generation.options_cache import ImageOptionsCache
        from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

        providers: dict[str, list[ModelCapabilities]] = {}

        # Chat models from the in-memory cache.
        for (
            provider,
            model_names,
        ) in ModelCapabilitiesCache.get_models_grouped_by_provider().items():
            caps: list[ModelCapabilities] = []
            for model_id in model_names:
                profile = ModelCapabilitiesCache.get(model_id)
                if profile is None:
                    # Race condition guard: provider list changed between
                    # get_models_grouped_by_provider() and get(). Skip.
                    continue
                caps.append(
                    ModelCapabilities(
                        model_id=model_id,
                        kind=profile.kind,
                        max_output_tokens=profile.max_output_tokens,
                        supports_tools=profile.supports_tool_calling,
                        supports_structured_output=profile.supports_structured_output,
                        supports_vision=profile.supports_vision,
                        is_reasoning_model=profile.is_reasoning_model,
                        supports_temperature=profile.supports_temperature,
                        supports_top_p=profile.supports_top_p,
                        supports_frequency_penalty=profile.supports_frequency_penalty,
                        supports_presence_penalty=profile.supports_presence_penalty,
                        reasoning_widget=profile.reasoning_widget,
                        reasoning_enum_values=profile.reasoning_enum_values,
                        reasoning_budget_range=profile.reasoning_budget_range,
                        reasoning_doc_i18n_key=profile.reasoning_doc_i18n_key,
                        effort_values=profile.effort_values,
                        cost_input=None,
                        cost_output=None,
                    )
                )
            providers[provider] = caps

        # Image-generation models from ImageOptionsCache. The model list is
        # the DISTINCT of model_name across active image_generation_pricing
        # rows, grouped by provider. Capability flags are False/0 — image
        # models don't expose chat capabilities. ``kind="image"`` is the
        # source of truth (replaces the legacy ``is_image_model`` flag).
        for (
            provider,
            image_model_ids,
        ) in ImageOptionsCache.get_models_grouped_by_provider().items():
            existing = providers.get(provider, [])
            existing_ids = {m.model_id for m in existing}
            for model_id in image_model_ids:
                if model_id not in existing_ids:
                    existing.append(
                        ModelCapabilities(
                            model_id=model_id,
                            kind="image",
                            max_output_tokens=0,
                            supports_tools=False,
                            supports_structured_output=False,
                            supports_vision=False,
                            is_reasoning_model=False,
                            # Image generation has no sampling parameters.
                            supports_temperature=False,
                            supports_top_p=False,
                            supports_frequency_penalty=False,
                            supports_presence_penalty=False,
                            reasoning_widget="none",
                            reasoning_enum_values=None,
                            reasoning_budget_range=None,
                            reasoning_doc_i18n_key=None,
                        )
                    )
            providers[provider] = existing

        # Apply optional filters (?kinds= and ?capability=)
        if kinds is not None or capability is not None:
            kind_set = set(kinds) if kinds is not None else None
            providers = {
                p: [
                    m
                    for m in caps_list
                    if (kind_set is None or m.kind in kind_set)
                    and (capability is None or _model_has_capability(m, capability))
                ]
                for p, caps_list in providers.items()
            }
            # Drop providers with empty lists post-filter
            providers = {p: caps for p, caps in providers.items() if caps}

        return ProviderModelsMetadata(providers=providers)

    @staticmethod
    async def get_ollama_models() -> OllamaModelsResponse:
        """Get Ollama models via dynamic discovery with fallback to the cache.

        When Ollama is reachable, capabilities come from the server itself
        (via ``/api/show``), not from cached profile guesses. When Ollama
        is unreachable, fall back to the DB-backed
        :class:`ModelCapabilitiesCache` filtered to ``provider=ollama``.
        """
        from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
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
                        kind="chat",  # Ollama models surfaced via /v1/chat are chat
                        max_output_tokens=8192,  # Ollama doesn't expose this; safe default
                        supports_tools="tools" in caps,
                        supports_structured_output="tools"
                        in caps,  # Tool-capable models support JSON mode
                        supports_vision="vision" in caps,
                        is_reasoning_model="thinking" in caps,
                        # Ollama's OpenAI-compatible bridge accepts the four
                        # sampling parameters for all chat models.
                        supports_temperature=True,
                        supports_top_p=True,
                        supports_frequency_penalty=True,
                        supports_presence_penalty=True,
                        reasoning_widget="none",  # Ollama bridge: no per-model widget surfaced
                        reasoning_enum_values=None,
                        reasoning_budget_range=None,
                        reasoning_doc_i18n_key=None,
                        cost_input=0.0,  # Local = free
                        cost_output=0.0,
                        size=info.size,
                        family=info.family,
                    )
                )
            return OllamaModelsResponse(models=models, source="live")

        # Fallback: Ollama unreachable — list whatever Ollama models the cache
        # knows about (populated from llm_models at boot).
        ollama_model_names = ModelCapabilitiesCache.get_models_grouped_by_provider().get(
            "ollama", []
        )
        models = []
        for model_id in ollama_model_names:
            profile = ModelCapabilitiesCache.get(model_id)
            if profile is None:
                continue
            models.append(
                OllamaModelCapabilities(
                    model_id=model_id,
                    kind=profile.kind,
                    max_output_tokens=profile.max_output_tokens,
                    supports_tools=profile.supports_tool_calling,
                    supports_structured_output=profile.supports_structured_output,
                    supports_vision=profile.supports_vision,
                    is_reasoning_model=profile.is_reasoning_model,
                    # Mirror the cache profile so fallback discovery agrees
                    # with the rest of the catalogue.
                    supports_temperature=profile.supports_temperature,
                    supports_top_p=profile.supports_top_p,
                    supports_frequency_penalty=profile.supports_frequency_penalty,
                    supports_presence_penalty=profile.supports_presence_penalty,
                    reasoning_widget=profile.reasoning_widget,
                    reasoning_enum_values=profile.reasoning_enum_values,
                    reasoning_budget_range=profile.reasoning_budget_range,
                    reasoning_doc_i18n_key=profile.reasoning_doc_i18n_key,
                    cost_input=0.0,  # Ollama is local — free
                    cost_output=0.0,
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
