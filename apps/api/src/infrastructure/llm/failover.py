"""Which fallback models this deployment can actually reach.

Assert, not crash. A broken failover list is a configuration defect worth
shouting about, but it must never prevent a boot: the primary model works, and
refusing to start would turn a degraded fallback into a total outage.

Measured 2026-08-23, before ADR-244 retargeted the constant: the shipped chain
named ``claude-sonnet-4-5``, absent from the catalogue entirely, and
``deepseek-chat``, deactivated. The chain therefore had **no reachable target at
all**, the middleware mounted it anyway, and nothing anywhere said so.

One implementation, two callers: the boot step says it loudly once, and the
middleware factory mounts exactly the chain this returns -- so what is announced
and what is armed can never differ.
"""

from __future__ import annotations

from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def usable_fallback_models(configured: str) -> list[str]:
    """Return the configured fallback entries the catalogue can serve.

    Args:
        configured: The comma-separated ``FALLBACK_MODELS`` value.

    Returns:
        The usable subset, in the configured priority order. Empty means the
        caller must disable the failover middleware rather than mount a chain
        that cannot fire.
    """
    names = [part.strip() for part in configured.split(",") if part.strip()]
    return [name for name in names if ModelCapabilitiesCache.get(name) is not None]


def assert_failover_chain(configured: str) -> list[str]:
    """Report on the chain and return its usable subset.

    Called once at boot, after ``ModelCapabilitiesCache.load_from_db`` -- the
    only moment the chain can be checked against the real catalogue.

    Args:
        configured: The comma-separated ``FALLBACK_MODELS`` value.

    Returns:
        The usable subset, in the configured priority order.
    """
    names = [part.strip() for part in configured.split(",") if part.strip()]
    usable = usable_fallback_models(configured)
    unreachable = [name for name in names if name not in usable]

    if unreachable:
        logger.error(
            "llm_failover_chain_unreachable",
            unreachable=unreachable,
            usable=usable,
            msg="these fallback models are absent from the active catalogue",
        )
    if names and not usable:
        logger.error(
            "llm_failover_chain_empty",
            configured=names,
            msg="failover disabled: no configured fallback model is reachable",
        )
    if not unreachable and usable:
        logger.info("llm_failover_chain_verified", models=usable)
    return usable
