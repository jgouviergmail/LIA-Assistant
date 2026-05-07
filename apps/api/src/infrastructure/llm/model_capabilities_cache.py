"""In-memory cache of LLM model capabilities (provider + ModelProfile).

Singleton populated from ``llm_models`` at app boot. Cross-worker invalidated
via the centralized Redis Pub/Sub system (ADR-063, see
``src/infrastructure/cache/invalidation.py``). Read synchronously by
``get_model_profile()`` on the LLM hot path — no DB roundtrip per call.

Pattern aligned with :class:`LLMConfigOverrideCache`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import LLMModel
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ModelCapabilitiesCache:
    """Singleton in-memory cache of model capabilities, keyed by ``model_name``.

    State:
        _cache: ``model_name`` → :class:`ModelProfile` (capabilities snapshot)
        _provider_by_model: ``model_name`` → provider string (for grouping)
        _loaded: True once :meth:`load_from_db` has succeeded at least once

    Hot-path reads (``get``) are O(1) without I/O. Writes happen only via
    :meth:`load_from_db` (during boot or after invalidation).
    """

    _cache: dict[str, ModelProfile] = {}
    _provider_by_model: dict[str, str] = {}
    _loaded: bool = False

    @classmethod
    async def load_from_db(cls, db: AsyncSession) -> None:
        """Load all active ``llm_models`` rows into memory (atomic swap).

        Called at startup (``main.py`` lifespan) and by the cross-worker
        invalidation subscriber. Never publishes — use
        :meth:`invalidate_and_reload` for the local-write-then-publish path.
        """
        stmt = select(LLMModel).where(LLMModel.is_active).order_by(LLMModel.model_name)
        result = await db.execute(stmt)
        rows = list(result.scalars().all())

        new_cache: dict[str, ModelProfile] = {}
        new_provider_by_model: dict[str, str] = {}
        for row in rows:
            new_cache[row.model_name] = cls._row_to_profile(row)
            new_provider_by_model[row.model_name] = row.provider.value

        # Atomic swap (single attribute assignment is atomic in CPython).
        cls._cache = new_cache
        cls._provider_by_model = new_provider_by_model
        cls._loaded = True

        logger.info(
            "model_capabilities_cache_loaded",
            count=len(new_cache),
            providers=sorted(set(new_provider_by_model.values())),
        )

    @classmethod
    async def invalidate_and_reload(cls, db: AsyncSession) -> None:
        """Reload the cache locally then publish a cross-worker invalidation.

        Called by admin endpoints after every llm_models mutation
        (POST/PUT/DELETE).
        """
        from src.core.constants import CACHE_NAME_MODEL_CAPABILITIES
        from src.infrastructure.cache.invalidation import publish_cache_invalidation

        await cls.load_from_db(db)
        await publish_cache_invalidation(CACHE_NAME_MODEL_CAPABILITIES)

    @classmethod
    def get(cls, model_name: str) -> ModelProfile | None:
        """O(1) hot-path lookup. Returns ``None`` for unknown models.

        Callers should fall back to a conservative default profile when
        ``None`` is returned (cf. :func:`get_model_profile`).
        """
        return cls._cache.get(model_name)

    @classmethod
    def get_provider(cls, model_name: str) -> str | None:
        """Return the provider string for a known model, or ``None``."""
        return cls._provider_by_model.get(model_name)

    @classmethod
    def get_models_grouped_by_provider(cls) -> dict[str, list[str]]:
        """Return ``{provider → [model_name, ...]}`` with deterministic order.

        Used by ``/llm-config/metadata`` to populate the admin Configuration LLM
        dropdowns. Each provider's model list is sorted alphabetically.
        """
        grouped: dict[str, list[str]] = {}
        for model_name, provider in cls._provider_by_model.items():
            grouped.setdefault(provider, []).append(model_name)
        for models in grouped.values():
            models.sort()
        return grouped

    @classmethod
    def is_loaded(cls) -> bool:
        """Return True once the cache has been populated at least once."""
        return cls._loaded

    @classmethod
    def reset(cls) -> None:
        """Reset cache state (testing only)."""
        cls._cache = {}
        cls._provider_by_model = {}
        cls._loaded = False

    @staticmethod
    def _row_to_profile(row: LLMModel) -> ModelProfile:
        """Map a SQLAlchemy ``LLMModel`` row to the runtime ``ModelProfile``.

        Cost fields stay at their defaults (0.0): pricing is sourced from
        ``llm_model_pricing`` separately and consumed by
        :class:`AsyncPricingService`, never from this cache. The metadata
        marker ``pricing_source="capabilities_cache"`` lets future callers
        detect that the cost fields are intentionally placeholder values.
        """
        return ModelProfile(
            max_input_tokens=row.max_input_tokens,
            max_output_tokens=row.max_output_tokens,
            supports_structured_output=row.supports_structured_output,
            supports_tool_calling=row.supports_tools,
            supports_strict_mode=row.supports_strict_mode,
            supports_streaming=row.supports_streaming,
            supports_vision=row.supports_vision,
            supports_temperature=row.supports_temperature,
            supports_top_p=row.supports_top_p,
            supports_frequency_penalty=row.supports_frequency_penalty,
            supports_presence_penalty=row.supports_presence_penalty,
            is_reasoning_model=row.is_reasoning_model,
            model_id=row.model_name,
            kind=row.kind.value,
            reasoning_widget=row.reasoning_widget.value,
            reasoning_enum_values=row.reasoning_enum_values,
            reasoning_budget_range=row.reasoning_budget_range,
            reasoning_doc_i18n_key=row.reasoning_doc_i18n_key,
            metadata={"pricing_source": "capabilities_cache"},
        )
