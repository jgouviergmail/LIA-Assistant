"""
LLM Configuration In-Memory Cache.

Singleton cache for LLM config overrides and provider API keys.
Populated from DB at startup, invalidated directly by the admin service.
Read synchronously by get_llm() factory — no async lookup at runtime.

Created: 2026-03-08
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import decrypt_data
from src.domains.llm_config.models import LLMConfigOverride, ProviderApiKey
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Override fields that correspond to LLMAgentConfig parameters
OVERRIDE_FIELDS = (
    "provider",
    "model",
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "max_tokens",
    "timeout_seconds",
    "reasoning_effort",
    "provider_config",
)


class LLMConfigOverrideCache:
    """Singleton in-memory cache for LLM config overrides.

    Populated at startup from DB, invalidated directly by admin service.
    Read synchronously by get_llm() — no Redis or async lookup at runtime.
    """

    _overrides: dict[str, dict[str, Any]] = {}  # llm_type → {field: value}
    _provider_keys: dict[str, str] = {}  # provider → decrypted key
    _loaded: bool = False

    @classmethod
    async def load_from_db(cls, db: AsyncSession) -> None:
        """Load all overrides and provider keys from DB into memory.

        Called at startup (lifespan) and after each admin modification.
        """
        # Load config overrides
        result = await db.execute(select(LLMConfigOverride))
        overrides: dict[str, dict[str, Any]] = {}
        for row in result.scalars().all():
            fields = {}
            for field in OVERRIDE_FIELDS:
                value = getattr(row, field, None)
                if value is not None:
                    fields[field] = value
            if fields:
                overrides[row.llm_type] = fields

        # Load provider API keys
        result = await db.execute(select(ProviderApiKey))
        provider_keys: dict[str, str] = {}
        for row in result.scalars().all():
            try:
                assert row.provider is not None  # noqa: S101 — provider is NOT NULL
                provider_keys[row.provider] = decrypt_data(row.encrypted_key)
            except Exception:
                logger.error(
                    "llm_config_cache_decrypt_failed",
                    provider=row.provider,
                    msg=f"Failed to decrypt API key for provider {row.provider}",
                    exc_info=True,
                )

        # Atomic swap
        cls._overrides = overrides
        cls._provider_keys = provider_keys
        cls._loaded = True

        logger.info(
            "llm_config_cache_loaded",
            overrides_count=len(overrides),
            provider_keys_count=len(provider_keys),
            msg=f"Loaded {len(overrides)} LLM overrides and {len(provider_keys)} provider keys",
        )

    @classmethod
    def get_override(cls, llm_type: str) -> dict[str, Any] | None:
        """Get config override for an LLM type (SYNC read).

        Called by get_llm_config_for_agent() in the sync LLM pipeline.

        Returns:
            Dict of override fields, or None if no override exists.
        """
        return cls._overrides.get(llm_type)

    @classmethod
    def get_api_key(cls, provider: str) -> str | None:
        """Get decrypted API key for a provider (SYNC read).

        Called by ProviderAdapter to resolve API keys.
        DB is the sole source of truth for provider API keys.

        Returns:
            Decrypted API key string, or None if not configured.
        """
        return cls._provider_keys.get(provider)

    @classmethod
    async def invalidate_and_reload(cls, db: AsyncSession) -> None:
        """Invalidate cache and reload from DB.

        Called by admin service after each PUT/DELETE operation.
        Publishes cross-worker invalidation via Redis Pub/Sub (ADR-063).
        """
        await cls.load_from_db(db)

        from src.core.constants import CACHE_NAME_LLM_CONFIG
        from src.infrastructure.cache.invalidation import publish_cache_invalidation

        await publish_cache_invalidation(CACHE_NAME_LLM_CONFIG)

    @classmethod
    def is_loaded(cls) -> bool:
        """Check if cache has been loaded at least once."""
        return cls._loaded

    @classmethod
    def reset(cls) -> None:
        """Reset cache state (for testing only)."""
        cls._overrides = {}
        cls._provider_keys = {}
        cls._loaded = False
