"""Composition of the egress publisher from the deployment's settings (ADR-298).

Everything the publisher needs — the cache, the management token the proxy
minted, the shared volume's path, the tunables — is read here and nowhere
else, so the tool and the boot step build the SAME publisher.
"""

from __future__ import annotations

from pathlib import Path

from src.core.config import get_settings
from src.core.constants import PYTHON_SANDBOX_EGRESS_CONFIG_DIR
from src.domains.agents.python_sandbox.egress.proxy_client import ProxyManagement
from src.domains.agents.python_sandbox.egress.publisher import EgressPublisher
from src.domains.agents.python_sandbox.egress.registry import LiveRunRegistry
from src.domains.agents.python_sandbox.egress.ruleset import RulesetConfig
from src.infrastructure.cache.redis import get_redis_cache

#: A registry entry outlives the run's own budget by this much, so a worker
#: that dies mid-run leaves a token the proxy forgets soon after the container
#: would have died anyway.
REGISTRY_TTL_GRACE_SECONDS = 60
#: The writer claim: rendering plus one reload, never more than seconds.
CLAIM_TTL_SECONDS = 15
CLAIM_WAIT_SECONDS = 5.0


def registry_ttl_seconds() -> int:
    """How long a live-run entry survives an unregistering nobody did."""
    return get_settings().python_sandbox_network_timeout_seconds + REGISTRY_TTL_GRACE_SECONDS


async def deployment_publisher() -> EgressPublisher:
    """The publisher for this deployment, on the shared cache.

    Raises:
        EgressProxyUnavailable: When the proxy has minted no management token
            — it is not running, or this container does not mount its volume.
    """
    settings = get_settings()
    config_dir = Path(PYTHON_SANDBOX_EGRESS_CONFIG_DIR)
    redis = await get_redis_cache()
    proxy = ProxyManagement(
        management_url=settings.python_sandbox_egress_management_url,
        health_url=settings.python_sandbox_egress_health_url,
        token=ProxyManagement.read_token(config_dir),
        timeout_seconds=settings.python_sandbox_egress_reload_timeout_seconds,
    )
    ttl = registry_ttl_seconds()
    return EgressPublisher(
        redis=redis,
        registry=LiveRunRegistry(redis, ttl_seconds=ttl),
        config_dir=config_dir,
        proxy=proxy,
        ruleset_config=RulesetConfig(max_body_bytes=settings.python_sandbox_egress_max_body_bytes),
        claim_ttl_seconds=CLAIM_TTL_SECONDS,
        claim_wait_seconds=CLAIM_WAIT_SECONDS,
        orphan_secret_age_seconds=ttl,
    )


__all__ = [
    "CLAIM_TTL_SECONDS",
    "CLAIM_WAIT_SECONDS",
    "REGISTRY_TTL_GRACE_SECONDS",
    "deployment_publisher",
    "registry_ttl_seconds",
]
