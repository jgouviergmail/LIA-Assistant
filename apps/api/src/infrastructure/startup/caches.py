"""Startup steps: in-memory caches and cross-worker invalidation (ADR-063).

Redis connection, pricing caches (LLM, Google API, image generation),
DB-backed config caches (LLM overrides, model capabilities, image options,
skills) and the Redis Pub/Sub invalidation subscriber. Every cache loaded
here is also registered for cross-worker invalidation via ``register_cache``;
``verify_registry_completeness()`` enforces that pairing at subscriber start.

Extracted verbatim from ``src.main.lifespan`` (ADR-123): same structlog
events, same exception handling, same feature-flag guards. Lazy imports are
kept inside each step on purpose (identical import timing and ImportError
surfaces as before the extraction).
"""

import asyncio

import structlog

from src.core.bootstrap import validate_llm_defaults_against_matrix
from src.core.config import settings
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)


async def init_redis() -> None:
    """Initialize Redis connections (non-fatal on failure)."""
    try:
        await get_redis_cache()
        logger.info("redis_initialized")
    except (ConnectionError, TimeoutError, OSError) as exc:
        logger.error("redis_initialization_failed", error=str(exc), exc_info=True)


async def init_pricing_caches() -> None:
    """Initialize the pricing caches and register them for invalidation.

    Covers, in order: global LLM pricing (callback safety — no DB access in
    callbacks), Google API pricing, and image generation pricing (gated by
    ``image_generation_enabled``). Each load is non-fatal; invalidation
    registration happens regardless of load success (ADR-063).
    """
    # Initialize global pricing cache (for callback safety - no DB access in callbacks)
    # See: src/infrastructure/cache/pricing_cache.py for implementation
    try:
        from src.infrastructure.cache.pricing_cache import refresh_pricing_cache

        await refresh_pricing_cache()
        logger.info("pricing_cache_initialized")
    except Exception as exc:
        # Non-critical - callbacks will use default prices (0.0 cost)
        logger.warning("pricing_cache_initialization_failed", error=str(exc))

    # Register pricing cache for cross-worker invalidation (ADR-063)
    from src.core.constants import CACHE_NAME_PRICING
    from src.infrastructure.cache.invalidation import register_cache

    async def _reload_pricing_cache() -> None:
        from src.infrastructure.cache.pricing_cache import refresh_pricing_cache as _refresh

        await _refresh()

    register_cache(CACHE_NAME_PRICING, _reload_pricing_cache)

    # Initialize Google API pricing cache (for cost tracking in tools and endpoints)
    try:
        from src.domains.google_api.pricing_service import GoogleApiPricingService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await GoogleApiPricingService.load_pricing_cache(db)
        logger.info("google_api_pricing_cache_initialized")
    except Exception as exc:
        # Non-critical - tracking will use zero cost if cache not loaded
        logger.warning("google_api_pricing_cache_initialization_failed", error=str(exc))

    # Register Google API pricing cache for cross-worker invalidation (ADR-063)
    from src.core.constants import CACHE_NAME_GOOGLE_API_PRICING

    async def _reload_google_api_pricing_cache() -> None:
        from src.domains.google_api.pricing_service import GoogleApiPricingService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await GoogleApiPricingService.load_pricing_cache(db)

    register_cache(CACHE_NAME_GOOGLE_API_PRICING, _reload_google_api_pricing_cache)

    # Initialize Image Generation pricing cache (for cost tracking in tools)
    if getattr(settings, "image_generation_enabled", False):
        try:
            from src.domains.image_generation.pricing_service import ImageGenerationPricingService
            from src.infrastructure.database.session import get_db_context

            async with get_db_context() as db:
                await ImageGenerationPricingService.load_pricing_cache(db)
            logger.info("image_generation_pricing_cache_initialized")
        except Exception as exc:
            logger.warning("image_generation_pricing_cache_initialization_failed", error=str(exc))

        # Register for cross-worker invalidation (ADR-063)
        from src.core.constants import CACHE_NAME_IMAGE_GENERATION_PRICING

        async def _reload_image_generation_pricing_cache() -> None:
            from src.domains.image_generation.pricing_service import (
                ImageGenerationPricingService,
            )
            from src.infrastructure.database.session import get_db_context

            async with get_db_context() as db:
                await ImageGenerationPricingService.load_pricing_cache(db)

        register_cache(CACHE_NAME_IMAGE_GENERATION_PRICING, _reload_image_generation_pricing_cache)


async def init_config_caches() -> None:
    """Initialize the DB-backed config caches and register them for invalidation.

    Covers, in order: LLM config override cache (must be loaded before any
    ``get_llm()`` call), model capabilities cache (LLM hot path) with the
    LLM_DEFAULTS/matrix fail-fast check, image generation options cache, and
    the skills cache with its DB sync (gated by ``skills_enabled``).
    """
    # Initialize LLM config override cache (must be before any get_llm() call)
    try:
        from src.domains.llm_config.cache import LLMConfigOverrideCache
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await LLMConfigOverrideCache.load_from_db(db)
        logger.info("llm_config_cache_initialized")

        # Warn about missing provider API keys (DB is the sole source of truth)
        from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_PROVIDERS

        required_providers = {cfg.provider for cfg in LLM_DEFAULTS.values()}
        for provider in sorted(required_providers):
            if not LLMConfigOverrideCache.get_api_key(provider):
                display = LLM_PROVIDERS.get(provider, provider)
                logger.warning(
                    "provider_api_key_missing",
                    provider=provider,
                    msg=f"No API key in DB for provider '{display}'. "
                    "Configure via Settings > Administration > LLM Configuration.",
                )
    except Exception as exc:
        logger.warning("llm_config_cache_initialization_failed", error=str(exc))

    # Register LLM config cache for cross-worker invalidation (ADR-063)
    from src.core.constants import CACHE_NAME_LLM_CONFIG
    from src.infrastructure.cache.invalidation import register_cache

    async def _reload_llm_config_cache() -> None:
        from src.domains.llm_config.cache import LLMConfigOverrideCache
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await LLMConfigOverrideCache.load_from_db(db)

    register_cache(CACHE_NAME_LLM_CONFIG, _reload_llm_config_cache)

    # Initialize LLM model capabilities cache from llm_models table.
    # Sits on the LLM hot path: get_model_profile() reads from this cache
    # synchronously without DB I/O.
    try:
        from src.infrastructure.database.session import get_db_context
        from src.infrastructure.llm.model_capabilities_cache import (
            ModelCapabilitiesCache,
        )

        async with get_db_context() as db:
            await ModelCapabilitiesCache.load_from_db(db)
        logger.info("model_capabilities_cache_initialized")

        # Fail-fast: every LLM_DEFAULTS entry must be compatible with the
        # matrix exposed by ModelCapabilitiesCache. Catches config drift at
        # boot rather than at the next admin API write or runtime call.
        validate_llm_defaults_against_matrix()
    except Exception as exc:
        # Boot continues; get_model_profile() will fall back to a conservative
        # default for any model not in the (possibly empty) cache.
        logger.critical(
            "model_capabilities_cache_initialization_failed",
            error=str(exc),
            exc_info=True,
        )

    # Register model capabilities cache for cross-worker invalidation (ADR-063)
    from src.core.constants import CACHE_NAME_MODEL_CAPABILITIES

    async def _reload_model_capabilities_cache() -> None:
        from src.infrastructure.database.session import get_db_context
        from src.infrastructure.llm.model_capabilities_cache import (
            ModelCapabilitiesCache,
        )

        async with get_db_context() as db:
            await ModelCapabilitiesCache.load_from_db(db)

    register_cache(CACHE_NAME_MODEL_CAPABILITIES, _reload_model_capabilities_cache)

    # Initialize image generation options cache from image_generation_pricing.
    # Powers Configuration LLM (image_generation type dropdown) and the
    # /image-generation/options endpoint consumed by the user-facing
    # ImageGenerationSettings component.
    try:
        from src.domains.image_generation.options_cache import ImageOptionsCache
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await ImageOptionsCache.load_from_db(db)
        logger.info("image_options_cache_initialized")
    except Exception as exc:
        logger.critical(
            "image_options_cache_initialization_failed",
            error=str(exc),
            exc_info=True,
        )

    # Register image options cache for cross-worker invalidation (ADR-063)
    from src.core.constants import CACHE_NAME_IMAGE_GENERATION_OPTIONS

    async def _reload_image_options_cache() -> None:
        from src.domains.image_generation.options_cache import ImageOptionsCache
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await ImageOptionsCache.load_from_db(db)

    register_cache(CACHE_NAME_IMAGE_GENERATION_OPTIONS, _reload_image_options_cache)

    # Initialize Skills cache (agentskills.io standard — SKILL.md files on disk)
    # Then sync DB (skills + user_skill_states) with disk state.
    if getattr(settings, "skills_enabled", False):
        try:
            from src.domains.skills.cache import SkillsCache

            SkillsCache.load_from_disk(settings.skills_system_path, settings.skills_users_path)
            logger.info("skills_cache_initialized")

            # Sync DB with disk (create new skills, remove orphans, ensure user
            # states). The in-memory cache load above is per-worker, but this
            # write-sync is O(users×skills) — running it on every worker at boot
            # is O(workers×users×skills). Gate it behind a distributed lock so
            # only one worker performs the write per deploy; the others skip
            # (the shared DB is already consistent, and per-user states are also
            # created lazily on demand). F018.
            from src.core.constants import SCHEDULER_JOB_SKILLS_DB_SYNC
            from src.domains.skills.preference_service import SkillPreferenceService
            from src.infrastructure.database.session import AsyncSessionLocal
            from src.infrastructure.locks.scheduler_lock import SchedulerLock

            redis = await get_redis_cache()
            async with SchedulerLock(
                redis_client=redis,
                job_id=SCHEDULER_JOB_SKILLS_DB_SYNC,
                ttl_seconds=300,
            ) as lock:
                if not lock.acquired:
                    # Another worker is performing (or has performed) the sync.
                    logger.debug("skills_db_sync_skipped_not_leader")
                else:
                    async with AsyncSessionLocal() as db:
                        svc = SkillPreferenceService(db)
                        sync_result = await svc.sync_from_disk()
                        await db.commit()
                        logger.info(
                            "skills_db_synced",
                            created=len(sync_result.created),
                            removed=len(sync_result.removed),
                            updated=len(sync_result.updated),
                        )
        except Exception as exc:
            logger.warning("skills_cache_initialization_failed", error=str(exc))

        # Register skills cache for cross-worker invalidation (ADR-063)
        from src.core.constants import CACHE_NAME_SKILLS

        async def _reload_skills_cache() -> None:
            from src.domains.skills.cache import SkillsCache

            SkillsCache.load_from_disk(settings.skills_system_path, settings.skills_users_path)

        register_cache(CACHE_NAME_SKILLS, _reload_skills_cache)


def start_cache_invalidation_subscriber() -> asyncio.Task[None] | None:
    """Start the cross-worker cache invalidation subscriber (Redis Pub/Sub — ADR-063).

    ``verify_registry_completeness()`` fail-fasts if a cache was loaded
    without being registered for invalidation (or vice versa).

    Returns:
        The running subscriber task (to cancel at shutdown), or None on failure.
    """
    cache_invalidation_task: asyncio.Task[None] | None = None
    try:
        from src.infrastructure.cache.invalidation import (
            run_invalidation_subscriber,
            verify_registry_completeness,
        )

        verify_registry_completeness()
        cache_invalidation_task = asyncio.create_task(run_invalidation_subscriber())
        logger.info("cache_invalidation_subscriber_started")
    except (RuntimeError, ImportError) as exc:
        logger.error("cache_invalidation_subscriber_start_failed", error=str(exc), exc_info=True)
    return cache_invalidation_task
