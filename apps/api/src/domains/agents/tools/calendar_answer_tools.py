"""The assistant answers an invitation, on any calendar (ADR-369, lot 5, D2).

The clients gained one contract for the « Tools » section (``calendar_answers``), and what
they gain reaches the assistant in the same lot. An answer leaves for the organiser, so
this tool only drafts it: the card is the confirmation, in both execution modes, as for
every calendar write, and ``execute_event_answer_draft`` gives it. It reads the event first:
the card names what is answered and who is told, and an event that does not name the
person is refused there, before anyone is asked anything.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.domains.agents.calendar.answer_manifest import (
    CALENDAR_ID_DESCRIPTION,
    EVENT_ANSWERS,
    EVENT_ID_DESCRIPTION,
    RESPONSE_DESCRIPTION,
)
from src.domains.agents.constants import AGENT_EVENT, CONTEXT_DOMAIN_EVENTS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.drafts import EventAnswerDraftInput, create_event_answer_draft
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.calendar_context import resolve_calendar_id_from_context
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.connectors.clients.calendar_answers import own_answer
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.resolver import resolve_calendar_name

logger = structlog.get_logger(__name__)


class RespondToEventTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """Answer an invitation of the active calendar."""

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialise the invitation tool."""
        super().__init__(tool_name="respond_to_event_tool", operation="respond")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Read the invitation and prepare its answer for the card."""
        event_id = str(kwargs.get("event_id") or "").strip()
        response = str(kwargs.get("response") or "")
        if not event_id:
            return refusal(ToolErrorCode.INVALID_INPUT, "event_id is required: name the event.")
        if response not in EVENT_ANSWERS:
            return refusal(ToolErrorCode.INVALID_INPUT, f"response is one of {EVENT_ANSWERS}.")
        calendar_id = await self._calendar_of(client, event_id, kwargs.get("calendar_id"))
        event = await client.get_event(event_id, calendar_id)
        if own_answer(event) is None:
            return refusal(
                ToolErrorCode.CONSTRAINT_VIOLATION,
                "This event does not name the person among those invited: nothing to answer.",
            )
        logger.info("calendar_invitation_answer_drafted", user_id=str(user_id))
        start = event.get("start") or {}
        return {
            "event_id": event_id,
            "response": response,
            "calendar_id": calendar_id,
            "summary": event.get("summary"),
            "start_datetime": start.get("dateTime") or start.get("date"),
            "organizer": (event.get("organizer") or {}).get("email"),
        }

    async def _calendar_of(
        self, client: GoogleCalendarClient, event_id: str, named: str | None
    ) -> str:
        """Where the event lives: the calendar named, the one the context knows, the primary.

        The card keeps this id: the answer leaves from the calendar the event was read in.
        """
        if named:
            return await resolve_calendar_name(client, named)
        if self.runtime:
            config = validate_runtime_config(self.runtime, "respond_to_event_tool")
            if not isinstance(config, UnifiedToolOutput):
                return await resolve_calendar_id_from_context(config, event_id) or "primary"
        return "primary"

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """The card that asks; a refusal is said."""
        if "error_code" in result:
            return UnifiedToolOutput.failure(
                message=str(result["message"]), error_code=str(result["error_code"])
            )
        return create_event_answer_draft(
            EventAnswerDraftInput(**result, user_language=self.get_user_language())
        )


_respond_to_event_tool_instance = RespondToEventTool()


@connector_tool(
    name="respond_to_event",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    context_save_mode=ContextSaveMode.NONE,
    category="write",
)
async def respond_to_event_tool(
    event_id: Annotated[str, EVENT_ID_DESCRIPTION],
    response: Annotated[str, RESPONSE_DESCRIPTION],
    calendar_id: Annotated[str | None, CALENDAR_ID_DESCRIPTION] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Answer an invitation in the person's name, on any calendar.

    Args:
        event_id: The event.
        response: The answer.
        calendar_id: Its calendar.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput saying the answer given.
    """
    return await _respond_to_event_tool_instance.execute(
        runtime=runtime, event_id=event_id, response=response, calendar_id=calendar_id
    )


__all__ = ["RespondToEventTool", "respond_to_event_tool"]
