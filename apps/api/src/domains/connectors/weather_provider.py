"""Weather provider chokepoint (lot E, 2026-08).

Single place the read paths (briefing, heartbeat) obtain the active weather
provider's client. Both providers expose the same OWM-shaped interface, so
callers stay provider-agnostic:

- Google Weather: platform key, toggle activation (default-friendly);
- OpenWeatherMap: personal API key.

A weather ROUTINE is the exception, and reads :func:`open_platform_weather_client`:
what fires it must be the source the platform guarantees for every account,
not whichever provider the person picked (ADR-322 amendment 2026-09-29).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.models import ConnectorType

if TYPE_CHECKING:
    from src.domains.connectors.clients.google_weather_client import GoogleWeatherClient
    from src.domains.connectors.service import ConnectorService

logger = structlog.get_logger(__name__)


async def resolve_weather_client(user_id: UUID, connector_service: Any) -> Any | None:
    """Client of the active weather provider (OWM-shaped), or None.

    Args:
        user_id: Owner of the connectors.
        connector_service: ConnectorService for resolution + credentials.

    Returns:
        A GoogleWeatherClient or OpenWeatherMapClient, or None when no
        weather provider is active/usable.
    """
    from src.domains.connectors.provider_resolver import resolve_active_connector

    resolved = await resolve_active_connector(user_id, "weather", connector_service)
    if resolved is None:
        return None

    if resolved.uses_global_api_key:
        if not settings.google_api_key:
            logger.warning("weather_provider_platform_key_missing", user_id=str(user_id))
            return None
        from src.domains.connectors.clients.google_weather_client import GoogleWeatherClient

        return GoogleWeatherClient(user_id)

    credentials = await connector_service.get_api_key_credentials(user_id, resolved)
    if credentials is None:
        return None
    from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient

    return OpenWeatherMapClient(api_key=credentials.api_key, user_id=user_id)


async def open_platform_weather_client(
    user_id: UUID, connector_service: ConnectorService
) -> GoogleWeatherClient | None:
    """The instance's own weather client — Google Weather — whatever the person chose.

    Google Weather is keyless: whether it serves the account is the
    instance's answer (the administrator's switch and the platform key,
    ADR-307), never a per-account row, so it is the one weather source the
    platform can guarantee. A person's OpenWeatherMap key is never read here.

    Args:
        user_id: The account the calls are billed to.
        connector_service: Answers whether the instance serves Google Weather.

    Returns:
        The client, or ``None`` when the instance withholds Google Weather —
        never a fallback on another provider.
    """
    if not await connector_service.is_connector_active(user_id, ConnectorType.GOOGLE_WEATHER):
        return None
    from src.domains.connectors.clients.google_weather_client import GoogleWeatherClient

    return GoogleWeatherClient(user_id)
