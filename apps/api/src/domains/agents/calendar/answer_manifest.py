"""Catalogue manifest of the invitation tool (ADR-369, lot 5, owner decision D2).

Beside ``catalogue_manifests.py``, at its size cap. What it publishes is what the tool
enforces (ADR-184): the answers are written ONCE, in the words both the planner's
manifest and the ReAct tool schema read (ADR-310).
"""

from typing import Final, get_args

from src.core.constants import GOOGLE_CALENDAR_SCOPES
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.connectors.clients.calendar_answers import EventAnswer

#: The answers an invitation takes.
EVENT_ANSWERS: Final[tuple[str, ...]] = get_args(EventAnswer)

EVENT_ID_DESCRIPTION: Final = "The event's id (from get_events_tool or CONTEXT)."
RESPONSE_DESCRIPTION: Final = "accepted, declined or tentative: the organiser is told."
CALENDAR_ID_DESCRIPTION: Final = "Its calendar, when it is not the primary one."

respond_to_event_catalogue_manifest = ToolManifest(
    name="respond_to_event_tool",
    agent="event_agent",
    description=(
        "**Tool: respond_to_event_tool** - Answer an invitation in the person's name (Google, "
        "Outlook or iCloud): accept it, decline it, or say maybe. The organiser is told, so the "
        "person is asked to confirm first.\n"
        "- 'accept tomorrow's meeting', 'decline the invitation from Paul', 'say maybe to it'\n"
        "- The id comes from get_events_tool or CONTEXT\n"
        "- It answers for the person alone: an event that does not name them is refused\n"
        "**RETURNS**: `event_id`, `response`."
    ),
    tool_category="update",
    mutation_policy="draft",
    semantic_keywords=[
        "accept this invitation",
        "decline the meeting invitation",
        "answer maybe to this event",
        "tell the organiser I am coming",
        "say I cannot attend the meeting",
    ],
    parameters=[
        ParameterSchema(
            name="event_id",
            type="string",
            required=True,
            description=EVENT_ID_DESCRIPTION,
            semantic_type="event_id",
        ),
        ParameterSchema(
            name="response",
            type="string",
            required=True,
            description=RESPONSE_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(EVENT_ANSWERS))],
        ),
        ParameterSchema(
            name="calendar_id",
            type="string",
            required=False,
            description=CALENDAR_ID_DESCRIPTION,
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="event_id", type="string", description="The event", semantic_type="event_id"
        ),
        OutputFieldSchema(path="response", type="string", description="The answer given"),
    ],
    cost=CostProfile(est_tokens_in=70, est_tokens_out=40, est_cost_usd=0.0, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CALENDAR_SCOPES,
        # Draft-based: the card IS the confirmation, as every calendar write (see
        # ``delete_event_catalogue_manifest``); the flag only drives ReAct's other interrupt.
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    reference_examples=["event_id", "response"],
    display=DisplayMetadata(emoji="📨", i18n_key="respond_to_event", visible=True, category="tool"),
    version="1.0.0",
    maintainer="Team Agents",
)

__all__ = [
    "CALENDAR_ID_DESCRIPTION",
    "EVENT_ANSWERS",
    "EVENT_ID_DESCRIPTION",
    "RESPONSE_DESCRIPTION",
    "respond_to_event_catalogue_manifest",
]
