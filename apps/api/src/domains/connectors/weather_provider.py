"""Weather provider chokepoint (lot E, 2026-08).

Single place the read paths (briefing, heartbeat) obtain the active weather
provider's client. Both providers expose the same OWM-shaped interface, so
callers stay provider-agnostic:

- Google Weather: platform key, toggle activation (default-friendly);
- OpenWeatherMap: personal API key.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings

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
