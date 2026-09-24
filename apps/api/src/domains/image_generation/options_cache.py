"""In-memory cache of what each SERVABLE image model offers (ADR-305).

Built from the active ``image_generation_pricing`` rows, kept only when a family
declares the model (``families.py`` — a declared family has a client, which
``client.py`` checks at import) and accepts the row's quality and size. What the
cache holds is therefore exactly what can run and be billed. Used by:

- Configuration LLM — the image slot's model list
  (:meth:`get_models_grouped_by_provider`), and the write path's check that a
  configured image model is served;
- ``GET /image-generation/options`` and the image tools — the configured model's
  qualities (with price ranges) and sizes (with orientation and billing tier)
  (:meth:`get_options_for_model`).

Cross-worker invalidated via Redis Pub/Sub (ADR-063), aligned with
``ModelCapabilitiesCache``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.image_generation.families import ImageFamily, resolve_image_family
from src.domains.image_generation.models import ImageGenerationPricing
from src.domains.image_generation.sizing import ImageSize, Orientation
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_ORIENTATION_ORDER: dict[Orientation, int] = {"square": 0, "landscape": 1, "portrait": 2}


@dataclass(frozen=True)
class QualityOption:
    """One quality level offered for a given model.

    ``min_cost_usd`` / ``max_cost_usd`` span the price range across the sizes
    offered at that quality (the "(~$0.04-0.06)" hint of the settings).
    """

    value: str
    min_cost_usd: Decimal
    max_cost_usd: Decimal


@dataclass(frozen=True)
class SizeOption:
    """One image size offered for a given model.

    Attributes:
        value: ``WIDTHxHEIGHT``.
        orientation: Square, landscape or portrait (the settings' label).
        tier: The family's billing tier for this size, or ``None`` without tiers.
    """

    value: str
    orientation: Orientation
    tier: str | None


@dataclass(frozen=True)
class ModelOptions:
    """What one servable image model offers."""

    model: str
    provider: str
    family: ImageFamily
    qualities: tuple[QualityOption, ...]
    sizes: tuple[SizeOption, ...]


class ImageOptionsCache:
    """Singleton in-memory cache of servable image models and their offer.

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
        """Group rows by model and keep what a family and a client can serve."""
        per_model: dict[str, list[ImageGenerationPricing]] = {}
        for row in rows:
            per_model.setdefault(row.model, []).append(row)

        result: dict[str, ModelOptions] = {}
        for model_name, model_rows in per_model.items():
            options = _servable_options(model_name, model_rows)
            if options is not None:
                result[model_name] = options
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
        """Return what ``model_name`` offers, or ``None`` when it is not servable."""
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


def _servable_options(
    model_name: str, model_rows: list[ImageGenerationPricing]
) -> ModelOptions | None:
    """What one model offers, or ``None`` when nothing of it can be served.

    Args:
        model_name: The model.
        model_rows: Its active pricing rows.

    Returns:
        The model's options, restricted to the rows of one provider that its
        family accepts.
    """
    providers = {r.provider.value for r in model_rows}
    if len(providers) > 1:
        # The router's invariant prevents this; log loudly if stale data slips in.
        logger.warning(
            "image_options_cache_multi_provider", model=model_name, providers=sorted(providers)
        )
    provider = min(providers)
    family = resolve_image_family(provider, model_name)
    if family is None:
        logger.warning("image_options_model_unserved", model=model_name, provider=provider)
        return None

    accepted = [
        r
        for r in model_rows
        if r.provider.value == provider and family.refusal(r.quality, r.size) is None
    ]
    if len(accepted) < len(model_rows):
        logger.warning(
            "image_options_rows_refused",
            model=model_name,
            refused=len(model_rows) - len(accepted),
        )
    if not accepted:
        return None

    return ModelOptions(
        model=model_name,
        provider=provider,
        family=family,
        qualities=_quality_options(family, accepted),
        sizes=_size_options(family, accepted),
    )


def _quality_options(
    family: ImageFamily, rows: list[ImageGenerationPricing]
) -> tuple[QualityOption, ...]:
    """Offered qualities in the family's declared order, with their price range."""
    buckets: dict[str, list[Decimal]] = {}
    for row in rows:
        buckets.setdefault(row.quality, []).append(row.cost_per_image_usd)
    return tuple(
        QualityOption(value=quality, min_cost_usd=min(costs), max_cost_usd=max(costs))
        for quality in family.qualities
        if (costs := buckets.get(quality))
    )


def _size_options(
    family: ImageFamily, rows: list[ImageGenerationPricing]
) -> tuple[SizeOption, ...]:
    """Offered sizes by tier, then square/landscape/portrait, then area."""
    tier_order = {tier.name: rank for rank, tier in enumerate(family.billing_tiers)}
    sizes = {ImageSize.parse(row.size) for row in rows}
    options = [
        SizeOption(value=str(size), orientation=size.orientation, tier=family.tier_of(size))
        for size in sizes
    ]
    return tuple(
        sorted(
            options,
            key=lambda option: (
                tier_order.get(option.tier or "", 0),
                _ORIENTATION_ORDER[option.orientation],
                ImageSize.parse(option.value).area,
            ),
        )
    )
