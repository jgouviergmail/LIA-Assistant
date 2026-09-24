"""A connector that asks nothing of the person belongs to the INSTANCE (ADR-307).

Wikipedia, the browser, Google Places, Google Weather and Google Environment
need no OAuth consent and no personal key. Whether one of them serves an
account is therefore decided by the instance alone — the administrator's global
switch, the platform ``GOOGLE_API_KEY``, the browser flag — and never by a
per-account row.

A row was the previous authority (ADR-307 records why it went): every account
created before sign-up provisioning had none, an administrator re-enabling a
type left every row ``REVOKED`` with no way back once the settings stopped
offering the switch, and the person could turn off a service that costs them
nothing and then fail to find it. Reading the instance instead makes « always
active » true by construction, for every account, with no reconciliation job.

The same predicate answers everywhere a keyless type is asked about:
``ConnectorService.is_connector_active``, the functional-category resolver
(Google Weather is the weather default when the person configured no
provider of their own) and the heartbeat's source availability probe.

Created: 2026-09-23
"""

from __future__ import annotations

from src.core.config import settings
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.repository import ConnectorRepository

#: Why a keyless type does not serve this instance (bounded, logged, tested).
REASON_DISABLED_BY_ADMIN = "disabled_by_admin"
REASON_PLATFORM_KEY_MISSING = "platform_key_missing"
REASON_BROWSER_DISABLED = "browser_disabled"


async def keyless_unavailable_reason(
    repository: ConnectorRepository, connector_type: ConnectorType
) -> str | None:
    """Why this keyless type does NOT serve the instance, or ``None`` when it does.

    Args:
        repository: Connector repository on the caller's session (reads the
            administrator's global configuration).
        connector_type: A keyless connector type.

    Returns:
        One of the ``REASON_*`` constants, or ``None`` when the type is available.

    Raises:
        ValueError: If ``connector_type`` is not keyless — the question has no
            instance-wide answer for a connector the person must configure.
    """
    if not connector_type.is_keyless:
        raise ValueError(f"{connector_type.value} is not a keyless connector type")
    # No row means enabled — the default `ConnectorService._check_connector_enabled` applies.
    config = await repository.get_global_config_by_type(connector_type)
    if config is not None and not config.is_enabled:
        return REASON_DISABLED_BY_ADMIN
    if connector_type.uses_global_api_key and not settings.google_api_key:
        return REASON_PLATFORM_KEY_MISSING
    if connector_type is ConnectorType.BROWSER and not settings.browser_enabled:
        return REASON_BROWSER_DISABLED
    return None


async def is_keyless_available(
    repository: ConnectorRepository, connector_type: ConnectorType
) -> bool:
    """Whether this keyless type serves every account of the instance.

    Args:
        repository: Connector repository on the caller's session.
        connector_type: A keyless connector type.

    Returns:
        True when nothing on the instance withholds the service.
    """
    return await keyless_unavailable_reason(repository, connector_type) is None
