"""In-memory cache of per-model image-generation options (qualities/sizes).

Built by DISTINCT on ``image_generation_pricing`` rows (active only). Used by:

- Configuration LLM admin dropdown (image_generation LLM type) → list of
  models, grouped by provider. Powered by
  :meth:`get_models_grouped_by_provider`.
- ``GET /image-generation/options`` (Task 17) → for a given active model,
  list of qualities (with min/max price ranges) and sizes. Powered by
  :meth:`get_options_for_model`.

Cross-worker invalidated via Redis Pub/Sub (ADR-063), aligned with
``ModelCapabilitiesCache``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.image_generation.models import ImageGenerationPricing
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class QualityOption:
    """One quality level supported for a given model.

    ``min_cost_usd`` / ``max_cost_usd`` span the price range across all
    sizes available at that quality (lets the UI display the
    "(~$0.04-0.06)" hint that ``ImageGenerationSettings`` shows today).
    """

    value: str
    min_cost_usd: Decimal
    max_cost_usd: Decimal


@dataclass(frozen=True)
class SizeOption:
    """One image size supported for a given model."""

    value: str


@dataclass(frozen=True)
class ModelOptions:
    """Aggregated options for one image-generation model."""

    model: str
    provider: str
    qualities: tuple[QualityOption, ...]
    sizes: tuple[SizeOption, ...]


class ImageOptionsCache:
    """Singleton in-memory cache of image-generation options.

    State:
        _by_model: ``model_name`` → :class:`ModelOptions`
        _by_provider: ``provider`` → sorted list of ``model_name`` strings
        _loaded: True once :meth:`load_from_db` succeeded at least once

    Hot-path reads (``get_options_for_model``) are O(1).
    """

    _by_model: dict[str, ModelOptions] = {}
    _by_provider: dict[str, list[str]] = {}
    _loaded: bool = False

    @classmethod
    async def load_from_db(cls, db: AsyncSession) -> None:
        """Load all active rows and rebuild both indexes (atomic swap)."""
        stmt = select(ImageGenerationPricing).where(ImageGenerationPricing.is_active)
        rows = list((await db.execute(stmt)).scalars().all())

        new_by_model = cls._build_by_model(rows)
        new_by_provider: dict[str, list[str]] = {}
        for model_name, opts in new_by_model.items():
            new_by_provider.setdefault(opts.provider, []).append(model_name)
        for names in new_by_provider.values():
            names.sort()

        cls._by_model = new_by_model
        cls._by_provider = new_by_provider
        cls._loaded = True

        logger.info(
            "image_options_cache_loaded",
            model_count=len(new_by_model),
            providers=sorted(new_by_provider.keys()),
        )

    @staticmethod
    def _build_by_model(rows: list[ImageGenerationPricing]) -> dict[str, ModelOptions]:
        """Group rows by model and aggregate qualities/sizes/price ranges."""
        # First pass: group rows by model.
        per_model: dict[str, list[ImageGenerationPricing]] = {}
        for row in rows:
            per_model.setdefault(row.model, []).append(row)

        result: dict[str, ModelOptions] = {}
        for model_name, model_rows in per_model.items():
            providers = {r.provider.value for r in model_rows}
            if len(providers) > 1:
                # The application-level invariant (router) prevents this, but
                # log loudly if it ever happens (e.g. stale data from a
                # legacy seed).
                logger.warning(
                    "image_options_cache_multi_provider",
                    model=model_name,
                    providers=sorted(providers),
                )
            provider = next(iter(providers))

            # Qualities with min/max price across the model's sizes.
            quality_buckets: dict[str, list[Decimal]] = {}
            for r in model_rows:
                quality_buckets.setdefault(r.quality, []).append(r.cost_per_image_usd)
            qualities = tuple(
                sorted(
                    (
                        QualityOption(
                            value=quality,
                            min_cost_usd=min(costs),
                            max_cost_usd=max(costs),
                        )
                        for quality, costs in quality_buckets.items()
                    ),
                    key=lambda q: q.value,
                )
            )

            # Sizes (DISTINCT, sorted).
            size_set = {r.size for r in model_rows}
            sizes = tuple(sorted((SizeOption(value=s) for s in size_set), key=lambda s: s.value))

            result[model_name] = ModelOptions(
                model=model_name,
                provider=provider,
                qualities=qualities,
                sizes=sizes,
            )

        return result

    @classmethod
    async def invalidate_and_reload(cls, db: AsyncSession) -> None:
        """Reload locally then publish a cross-worker invalidation."""
        from src.core.constants import CACHE_NAME_IMAGE_GENERATION_OPTIONS
        from src.infrastructure.cache.invalidation import publish_cache_invalidation

        await cls.load_from_db(db)
        await publish_cache_invalidation(CACHE_NAME_IMAGE_GENERATION_OPTIONS)

    @classmethod
    def get_options_for_model(cls, model_name: str) -> ModelOptions | None:
        """Return the aggregated options for ``model_name``, or ``None``."""
        return cls._by_model.get(model_name)

    @classmethod
    def get_models_grouped_by_provider(cls) -> dict[str, list[str]]:
        """Return ``{provider → [model_name, ...]}`` with deterministic order."""
        # Return a shallow copy so callers can mutate freely.
        return {provider: list(names) for provider, names in cls._by_provider.items()}

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._loaded

    @classmethod
    def reset(cls) -> None:
        """Reset cache state (testing only)."""
        cls._by_model = {}
        cls._by_provider = {}
        cls._loaded = False
