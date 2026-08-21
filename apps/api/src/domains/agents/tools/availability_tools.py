"""Calendar availability / free-slot search tool (lot B, 2026-08).

"Find me a 30-min slot Thursday" — computes free slots over the user's
calendar window:

- Google: through the freeBusy endpoint (busy ranges only — strictly less
  data than fetching events, minimization by capability);
- providers without freeBusy (Apple/Microsoft): through the same minimized
  start/end events projection telephony availability uses.

Counts are exact (count doctrine): ``total`` is the number of returned
slots, ``busy_count`` the number of busy blocks actually considered.
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.constants import (
    AVAILABILITY_DURATION_MAX_MINUTES,
    AVAILABILITY_DURATION_MIN_MINUTES,
    AVAILABILITY_PROJECTION_MAX_EVENTS,
)
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.constants import AGENT_EVENT, CONTEXT_DOMAIN_EVENTS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services.availability_slots import (
    busy_intervals_from_events,
    busy_intervals_from_freebusy,
    find_free_slots,
)
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


def _aware(raw: str, tz: ZoneInfo) -> datetime | None:
    """Parse an ISO datetime; naive values are localized to the user's tz."""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except TypeError, ValueError:
        return None
    return parsed.replace(tzinfo=tz) if parsed.tzinfo is None else parsed


class FindAvailabilityTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """Compute free calendar slots over a window (freeBusy fast-path)."""

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize find availability tool."""
        super().__init__(tool_name="find_availability_tool", operation="read")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Fetch busy intervals (freeBusy or projection) and compute free slots."""
        from src.domains.agents.tools.runtime_helpers import get_user_preferences

        user_timezone, _, _ = await get_user_preferences(self.runtime)
        try:
            tz = ZoneInfo(user_timezone or "UTC")
        except KeyError, ValueError:
            tz = ZoneInfo("UTC")

        window_start = _aware(str(kwargs.get("start_datetime") or ""), tz)
        window_end = _aware(str(kwargs.get("end_datetime") or ""), tz)
        if window_start is None or window_end is None or window_end <= window_start:
            return {
                "success": False,
                "error": "INVALID_INPUT",
                "message": APIMessages.invalid_date(),
            }

        # Repair-before-validate: an out-of-bounds duration is clamped, never
        # rejected (the bounds are published in the catalogue manifest).
        duration_minutes = int(kwargs.get("duration_minutes") or 30)
        duration_minutes = max(
            AVAILABILITY_DURATION_MIN_MINUTES,
            min(duration_minutes, AVAILABILITY_DURATION_MAX_MINUTES),
        )
        working_hours_only = bool(kwargs.get("working_hours_only", True))

        if hasattr(client, "query_freebusy"):
            response = await client.query_freebusy(
                time_min=window_start.astimezone(UTC).isoformat(),
                time_max=window_end.astimezone(UTC).isoformat(),
            )
            busy = busy_intervals_from_freebusy(response)
            source = "freebusy"
        else:
            # Minimization by capability: start/end only, never event details.
            result = await client.list_events(
                time_min=window_start.astimezone(UTC).isoformat(),
                time_max=window_end.astimezone(UTC).isoformat(),
                max_results=AVAILABILITY_PROJECTION_MAX_EVENTS,
                calendar_id="primary",
                fields=["start", "end"],
            )
            busy = busy_intervals_from_events(result.get("items", []))
            source = "events_projection"

        slots = find_free_slots(
            busy,
            window_start,
            window_end,
            duration_minutes,
            working_hours=(
                (settings.availability_work_start_hour, settings.availability_work_end_hour)
                if working_hours_only
                else None
            ),
            timezone_name=str(tz.key),
        )

        logger.info(
            "availability_computed",
            user_id=str(user_id),
            source=source,
            busy_count=len(busy),
            slot_count=len(slots),
        )
        return {
            "success": True,
            "slots": [{"start": start.isoformat(), "end": end.isoformat()} for start, end in slots],
            "total": len(slots),
            "busy_count": len(busy),
            "duration_minutes": duration_minutes,
            "window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
            "source": source,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Slots are plain structured data (no registry items)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Availability request failed"),
                error_code=result.get("error"),
            )
        return UnifiedToolOutput.data_success(
            message=f"{result['total']} free slots",
            structured_data={
                key: result[key]
                for key in ("slots", "total", "busy_count", "duration_minutes", "window")
            },
        )


_find_availability_instance = FindAvailabilityTool()


@connector_tool(
    name="find_availability",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="read",
)
async def find_availability_tool(
    start_datetime: Annotated[
        str,
        "Search window start in LOCAL time (user's timezone), ISO format "
        "WITHOUT offset, e.g. '2026-08-27T00:00:00'.",
    ],
    end_datetime: Annotated[
        str,
        "Search window end in LOCAL time (user's timezone), ISO format "
        "WITHOUT offset, e.g. '2026-08-28T00:00:00'.",
    ],
    duration_minutes: Annotated[int, "Minimum slot duration in minutes (5-480, default 30)"] = 30,
    working_hours_only: Annotated[
        bool,
        "Keep only working-hours slots (default True). Set False for "
        "explicitly off-hours requests (evenings, weekends).",
    ] = True,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Find free calendar slots in a time window ("find me a 30-min slot Thursday").

    Reads the user's primary calendar busy ranges (never event details) and
    returns the free gaps of at least the requested duration, clamped to
    working hours unless told otherwise.

    Returns:
        UnifiedToolOutput with free slots (ISO datetimes), exact totals and
        the busy-block count.
    """
    return await _find_availability_instance.execute(
        runtime=runtime,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        duration_minutes=duration_minutes,
        working_hours_only=working_hours_only,
    )
