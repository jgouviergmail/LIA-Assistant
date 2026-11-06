"""The calendars a person holds, as a tool (LOT 9) — moved out of calendar_tools.py.

Its own module since ADR-369 lot 10: ``calendar_tools.py`` is frozen at its audited size, and the
rule of a repeating event had to be paid for by a cohesive move rather than a raised cap.
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.i18n import get_locale_for_language
from src.domains.agents.constants import (
    AGENT_EVENT,
    CONTEXT_DOMAIN_CALENDARS,
    CONTEXT_DOMAIN_EVENTS,
)
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.data_registry.card_payload import take_display_fields
from src.domains.agents.display.components.calendar_details import calendar_display_fields
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


class ListCalendarsTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """
    List user's available calendars tool with Data Registry support.

    LOT 9: Read operation returning calendar list for frontend rendering.

    Benefits:
    - Shows all calendars available to the user
    - Helps user select which calendar to use
    - Returns calendar ID, name, color, access role
    """

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"

    # Data Registry mode enabled
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize list calendars tool with Data Registry support."""
        super().__init__(tool_name="list_calendars_tool", operation="list")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list calendars API call."""
        show_hidden: bool = kwargs.get("show_hidden", False)
        max_results: int = kwargs.get("max_results", 100)

        result = await client.list_calendars(
            max_results=max_results,
            show_hidden=show_hidden,
        )

        calendars = result.get("items", [])

        logger.info(
            "list_calendars_success",
            user_id=str(user_id),
            total_calendars=len(calendars),
            show_hidden=show_hidden,
        )

        # Get user preferences for locale, falling back to the declared language's
        try:
            _, _, locale = await get_user_preferences(self.runtime)
        except ValueError, KeyError, AttributeError:
            locale = get_locale_for_language(None)

        return {
            "calendars": calendars,
            "total": len(calendars),
            "show_hidden": show_hidden,
            "locale": locale,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format as Data Registry UnifiedToolOutput with calendar registry items."""
        from src.domains.agents.data_registry.models import (
            RegistryItem,
            RegistryItemMeta,
            RegistryItemType,
            generate_registry_id,
        )

        calendars = result.get("calendars", [])
        total = result.get("total", 0)

        # Build registry items for each calendar
        registry_updates: dict[str, RegistryItem] = {}
        summary_parts = []

        for cal in calendars:
            cal_id = cal.get("id", "")
            summary = cal.get("summaryOverride") or cal.get("summary", "")
            access_role = cal.get("accessRole", "reader")
            primary = cal.get("primary", False)
            background_color = cal.get("backgroundColor", "#4285f4")

            # Generate deterministic ID for registry
            registry_id = generate_registry_id(RegistryItemType.CALENDAR, cal_id)

            # Create registry item
            registry_updates[registry_id] = RegistryItem(
                id=registry_id,
                type=RegistryItemType.CALENDAR,
                payload={
                    "id": cal_id,
                    "summary": summary,
                    "access_role": access_role,
                    "primary": primary,
                    "background_color": background_color,
                    "description": cal.get("description", ""),
                    "time_zone": cal.get("timeZone", ""),
                },
                meta=RegistryItemMeta(
                    source="google_calendar",
                    domain=CONTEXT_DOMAIN_CALENDARS,
                    tool_name="list_calendars_tool",
                    display={**take_display_fields(cal), **calendar_display_fields(cal)},
                ),
            )

            # Build summary line
            primary_marker = " (primary)" if primary else ""
            summary_parts.append(f"- {summary or 'Unnamed'}{primary_marker} [{registry_id}]")

        # Build LLM message
        if calendars:
            message = f"[calendars] {total} calendar(s) available:\n" + "\n".join(
                summary_parts[:10]
            )
            if total > 10:
                message += f"\n... and {total - 10} more"
        else:
            message = "[calendars] No calendar found"

        return UnifiedToolOutput.data_success(
            message=message,
            registry_updates=registry_updates,
            metadata={
                "tool_name": "list_calendars_tool",
                "total": total,
                "show_hidden": result.get("show_hidden", False),
            },
        )


# Create tool instance (singleton)
_list_calendars_tool_instance = ListCalendarsTool()


@connector_tool(
    name="list_calendars",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="read",
)
async def list_calendars_tool(
    show_hidden: Annotated[
        bool,
        "Include hidden calendars in the list (default: False)",
    ] = False,
    max_results: Annotated[
        int,
        "Maximum number of calendars to return (default: 100, max: 250)",
    ] = 100,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    List all calendars available to the user.

    Returns a list of all calendars the user has access to, including:
    - Primary calendar
    - Secondary calendars (created by user)
    - Shared calendars (shared by others)
    - Subscribed calendars (public calendars)

    **Use Cases:**
    - User asks "what calendars do I have?"
    - User wants to know available calendars before creating/searching events
    - User needs calendar ID for specific calendar operations

    **Output includes for each calendar:**
    - id: Calendar ID (use this for calendar_id parameter in other tools)
    - summary: Calendar name/title
    - access_role: User's access level (owner, writer, reader)
    - primary: Whether this is the user's primary calendar
    - background_color: Calendar color in UI

    Args:
        show_hidden: Include hidden calendars (default: False)
        max_results: Maximum calendars to return (default: 100, max: 250)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with CALENDAR registry items for frontend rendering

    Example:
        User: "Which calendars can I use?"
        -> Returns list of all calendars with their IDs and properties
    """
    return await _list_calendars_tool_instance.execute(
        runtime=runtime,
        show_hidden=show_hidden,
        max_results=max_results,
    )
