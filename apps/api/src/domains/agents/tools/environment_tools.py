"""Air quality + pollen tools (lot E, 2026-08).

Platform services behind the GOOGLE_ENVIRONMENT toggle, independent of the
weather provider choice. "Je cours ce soir ?" → air quality; proactive
allergy signals → pollen forecast.

Location resolution mirrors the places tools: explicit ``location`` is
geocoded; otherwise the implicit cascade (browser > last-known > home).
Indices are the API aggregates verbatim (a number shown to the user is a
claim: exact or absent).
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.constants import GOOGLE_POLLEN_MAX_DAYS
from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.constants import AGENT_WEATHER, CONTEXT_DOMAIN_WEATHER
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_environment_client import GoogleEnvironmentClient
from src.domains.connectors.clients.google_geocoding_helpers import forward_geocode
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


async def _resolve_environment_point(
    runtime: Any, location: str
) -> tuple[float, float, str] | dict[str, Any]:
    """Resolve (lat, lon, label) for a query, or a localized error dict."""
    from src.domains.agents.tools.location_resolution import resolve_implicit_location
    from src.domains.agents.tools.runtime_helpers import get_user_language_safe

    language = normalize_language(await get_user_language_safe(runtime))
    if location:
        coords = await forward_geocode(location)
        if coords is not None:
            return coords[0], coords[1], coords[2] or location
        return {
            "success": False,
            "error": "location_required",
            "message": APIMessages.gps_required_for_nearby(language),
        }
    implicit = await resolve_implicit_location(runtime)
    if implicit is None or implicit.lat is None or implicit.lon is None:
        return {
            "success": False,
            "error": "location_required",
            "message": APIMessages.gps_required_for_nearby(language),
        }
    return implicit.lat, implicit.lon, ""


class GetAirQualityTool(ToolOutputMixin, ConnectorTool[GoogleEnvironmentClient]):
    """Current air quality (universal + local national index)."""

    connector_type = ConnectorType.GOOGLE_ENVIRONMENT
    client_class = GoogleEnvironmentClient
    registry_enabled = True
    uses_global_api_key = True

    def __init__(self) -> None:
        """Initialize air quality tool."""
        super().__init__(tool_name="get_air_quality_tool", operation="read")

    async def execute_api_call(
        self,
        client: GoogleEnvironmentClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Resolve the point and fetch current air quality."""
        from src.domains.agents.tools.runtime_helpers import get_user_language_safe

        point = await _resolve_environment_point(
            self.runtime, str(kwargs.get("location") or "").strip()
        )
        if isinstance(point, dict):
            return point
        lat, lon, label = point

        language = normalize_language(await get_user_language_safe(self.runtime))
        result = await client.get_air_quality(lat=lat, lon=lon, language=language)
        return {
            "success": True,
            "location_label": label,
            "region_code": result.get("region_code", ""),
            "date_time": result.get("date_time", ""),
            "indexes": result.get("indexes", []),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Structured data only (rendered by the response LLM)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Air quality request failed"),
                error_code=result.get("error"),
            )
        return UnifiedToolOutput.data_success(
            message=f"{len(result['indexes'])} air quality indexes",
            structured_data={
                key: result[key]
                for key in ("location_label", "region_code", "date_time", "indexes")
            },
        )


class GetPollenForecastTool(ToolOutputMixin, ConnectorTool[GoogleEnvironmentClient]):
    """Pollen forecast (grass/tree/weed, per-day indices)."""

    connector_type = ConnectorType.GOOGLE_ENVIRONMENT
    client_class = GoogleEnvironmentClient
    registry_enabled = True
    uses_global_api_key = True

    def __init__(self) -> None:
        """Initialize pollen forecast tool."""
        super().__init__(tool_name="get_pollen_forecast_tool", operation="read")

    async def execute_api_call(
        self,
        client: GoogleEnvironmentClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Resolve the point and fetch the pollen forecast."""
        from src.domains.agents.tools.runtime_helpers import get_user_language_safe

        point = await _resolve_environment_point(
            self.runtime, str(kwargs.get("location") or "").strip()
        )
        if isinstance(point, dict):
            return point
        lat, lon, label = point

        days = max(1, min(int(kwargs.get("days") or 3), GOOGLE_POLLEN_MAX_DAYS))
        language = normalize_language(await get_user_language_safe(self.runtime))
        result = await client.get_pollen_forecast(lat=lat, lon=lon, days=days, language=language)
        return {
            "success": True,
            "location_label": label,
            "region_code": result.get("region_code", ""),
            "days": result.get("days", []),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Structured data only (rendered by the response LLM)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Pollen request failed"),
                error_code=result.get("error"),
            )
        return UnifiedToolOutput.data_success(
            message=f"{len(result['days'])} pollen forecast days",
            structured_data={key: result[key] for key in ("location_label", "region_code", "days")},
        )


_air_quality_instance = GetAirQualityTool()
_pollen_instance = GetPollenForecastTool()


@connector_tool(
    name="get_air_quality",
    agent_name=AGENT_WEATHER,
    context_domain=CONTEXT_DOMAIN_WEATHER,
    category="read",
)
async def get_air_quality_tool(
    location: Annotated[
        str,
        "City or address (empty = the user's current location).",
    ] = "",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Current air quality at a location (universal AQI + local national index).

    Use for "can I run tonight?", pollution questions, health-sensitive
    outdoor activity advice.

    Returns:
        UnifiedToolOutput with the exact air-quality indexes.
    """
    return await _air_quality_instance.execute(runtime=runtime, location=location)


@connector_tool(
    name="get_pollen_forecast",
    agent_name=AGENT_WEATHER,
    context_domain=CONTEXT_DOMAIN_WEATHER,
    category="read",
)
async def get_pollen_forecast_tool(
    location: Annotated[
        str,
        "City or address (empty = the user's current location).",
    ] = "",
    days: Annotated[int, f"Forecast days (1-{GOOGLE_POLLEN_MAX_DAYS}, default 3)"] = 3,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Pollen forecast (grass, tree, weed) with per-day indices.

    Use for allergy questions and proactive allergy warnings.

    Returns:
        UnifiedToolOutput with per-day pollen types and exact indices.
    """
    return await _pollen_instance.execute(runtime=runtime, location=location, days=days)
