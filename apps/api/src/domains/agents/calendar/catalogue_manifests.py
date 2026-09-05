"""
Catalogue manifests for Google Calendar tools.
Refined & Optimized for orchestration efficiency.

Architecture Simplification (2026-01):
- get_events_tool replaces search_events_tool + get_event_details_tool
- Always returns full event content (description, attendees, conference link)
- Supports query mode (search) OR ID mode (direct fetch)
"""

from src.core.config import settings
from src.core.constants import (
    CALENDAR_TOOL_DEFAULT_LIMIT,
    GOOGLE_CALENDAR_SCOPES,
)

# Re-export: the loader imports the whole calendar family from this module.
from src.domains.agents.calendar.availability_manifest import (
    find_availability_catalogue_manifest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# Shared Constraints & Micro-optimizations
# ============================================================================

# Note: Backend handles name-to-ID resolution.
_CALENDAR_ID_PARAM = ParameterSchema(
    name="calendar_id",
    type="string",
    required=False,
    description="Target calendar. Accepts 'primary', a specific ID, or a human name (e.g., 'Famille') resolved by backend.",
    semantic_type="calendar_id",
)

# ============================================================================
# 1. GET EVENTS (Unified - replaces search + details)
# ============================================================================
_get_events_desc = (
    "**Tool: get_events_tool** - Get calendar events with full details.\n"
    "\n"
    "**USAGE**:\n"
    "- Search: use `query` parameter (optionally with `time_min`/`time_max`)\n"
    "- Fetch by ID (from $steps or CONTEXT only): use `event_id` or `event_ids`\n"
    "- List by range: use `time_min`/`time_max` without query\n"
    "\n"
    "**QUERY PARAMETER — attendee (person) search ONLY**:\n"
    "- Use `query` ONLY to find events with a specific PERSON, by name:\n"
    "  → get_events_tool(query='Jean Dupont') — resolved to their email (attendee).\n"
    "- For ANY title / topic / category / quality ('medical', 'dentist', a\n"
    "  project name, 'important'): OMIT query. Calendar free-text search is\n"
    "  unreliable; the assistant lists events in the time window and filters the\n"
    "  concept when answering.\n"
    "- Generic listing (next N events): OMIT query, set max_results.\n"
    "\n"
    "**COMMON USE CASES**:\n"
    "- 'my next 2 appointments/events' → NO query, just max_results=2\n"
    "- 'what is on my calendar today' → NO query, time_min=today_start, time_max=today_end\n"
    "- 'my upcoming events' → NO query, default time range applies\n"
    "- 'meeting with John' → query='John' (person → attendee search)\n"
    "- 'doctor / medical appointment' → NO query (list + filter the concept)\n"
    "- 'show this event details' → event_id=ID from $steps or CONTEXT\n"
    "\n"
    "**Time Format**: ISO 8601 (e.g., '2025-01-15T00:00:00+01:00').\n"
    "**Default**: Next 7 days if unspecified.\n"
    "**RETURNS**: Full event info (description, attendees, conference link, etc.)."
)

get_events_catalogue_manifest = ToolManifest(
    name="get_events_tool",
    agent="event_agent",
    description=_get_events_desc,
    # Discriminant phrases - Calendar event operations
    semantic_keywords=[
        # Calendar event retrieval
        "show scheduled events",
        "what meetings today",
        "list appointments for tomorrow",
        "show scheduled events on my calendar",
        "what meetings are on my agenda today",
        "list appointments for tomorrow on calendar",
        "upcoming events this week in schedule",
        # Appointment lookup (read-only queries)
        "which appointment do I have on Saturday",
        "what appointments this week",
        "do I have any appointments on that day",
        "what is on my calendar this weekend",
        "any events planned for Saturday",
        # Calendar availability
        "when am I free on my calendar",
        "check availability in my schedule",
        "busy time slots on calendar",
        "find free time in my agenda",
        # Event details
        "show meeting attendees and location",
        "event description and conference link",
        "who is attending this calendar event",
        "video call link for scheduled meeting",
        # Calendar search
        "find specific event on my calendar",
        "search meetings by topic in schedule",
        "calendar entries for date range",
    ],
    parameters=[
        # Query mode parameters
        ParameterSchema(
            name="query", type="string", required=False, description="Free text search query"
        ),
        ParameterSchema(
            name="time_min",
            type="string",
            required=False,
            description="Start of search window (ISO format)",
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="time_max",
            type="string",
            required=False,
            description="End of search window (ISO format)",
            # Emptied by the validator for open/relative queries with no user
            # temporal reference, so the tool's default window applies instead of
            # a planner-hallucinated narrow bound (e.g. "my next medical appts").
            search_role="range_end",
            semantic_type="datetime",
        ),
        # ID mode parameters
        ParameterSchema(
            name="event_id",
            type="string",
            required=False,
            description="Single event ID for direct fetch.",
            semantic_type="event_id",
        ),
        ParameterSchema(
            name="event_ids",
            type="array",
            required=False,
            description="Multiple event IDs for batch fetch.",
            semantic_type="event_id",
        ),
        # Common options
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max return (def: {CALENDAR_TOOL_DEFAULT_LIMIT}, max: {settings.calendar_tool_default_max_results})",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(
                    kind="maximum", value=settings.calendar_tool_default_max_results
                ),
            ],
        ),
        _CALENDAR_ID_PARAM,
    ],
    outputs=[
        # Full event outputs (merged from search + details)
        OutputFieldSchema(
            path="events", type="array", description="List of events with full details"
        ),
        OutputFieldSchema(
            path="events[].id", type="string", description="Event ID", semantic_type="event_id"
        ),
        OutputFieldSchema(path="events[].summary", type="string", description="Title"),
        OutputFieldSchema(
            path="events[].description", type="string", nullable=True, description="Description"
        ),
        OutputFieldSchema(path="events[].start", type="object", description="Start time object"),
        OutputFieldSchema(
            path="events[].date",
            type="string",
            description="Start datetime ISO 8601 (alias for weather.date, routes.arrival_time)",
            semantic_type="event_start_datetime",  # Cross-domain binding by name match
        ),
        OutputFieldSchema(path="events[].end", type="object", description="End time object"),
        OutputFieldSchema(
            path="events[].location",
            type="string",
            nullable=True,
            description="Location",
            semantic_type="physical_address",  # Cross-domain: can be used as routes.destination
        ),
        OutputFieldSchema(path="events[].attendees", type="array", description="Attendees list"),
        OutputFieldSchema(
            path="events[].attendees[].email",
            type="string",
            description="Attendee email address (Google API format)",
            semantic_type="email_address",  # Cross-domain: "email the attendees of this meeting"
        ),
        OutputFieldSchema(
            path="events[].conferenceData", type="object", nullable=True, description="Video link"
        ),
        OutputFieldSchema(
            path="events[].calendar_id",
            type="string",
            description="Calendar ID where event is stored",
            semantic_type="calendar_id",
        ),
        OutputFieldSchema(path="count", type="integer", description="Count"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=800, est_cost_usd=0.002, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CALENDAR_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    context_key="events",
    # context_save_mode set dynamically by tool (LIST for search, DETAILS for ID fetch)
    reference_examples=[
        "events[0].id",
        "events[0].start.dateTime",
        "events[0].location",
        "events[0].description",
        "events[0].calendar_id",
        "count",
    ],
    version="2.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📅", i18n_key="get_events", visible=True, category="tool"),
)


# ============================================================================
# 2. CREATE EVENT
# ============================================================================
_create_desc = (
    "**Tool: create_event_tool** - Create new calendar event. **REQUIRES HITL**.\n"
    "**Inputs**: 'start_datetime'/'end_datetime' specify the event timing.\n"
    "**Timezone**: If ISO includes offset (+02:00), 'timezone' param is IGNORED.\n"
    "**Video call**: set add_conference=true when the user asks for a visio/"
    "video call/online meeting — a Meet or Teams link is attached at creation "
    "(not supported on Apple calendars: event created without a link)."
)

create_event_catalogue_manifest = ToolManifest(
    name="create_event_tool",
    mutation_policy="draft",
    agent="event_agent",
    description=_create_desc,
    # Discriminant phrases - Calendar event creation
    semantic_keywords=[
        # Create new calendar event
        "schedule new event on my calendar",
        "planify new event on my calendar",
        "create new event on my calendar",
        "add meeting to my schedule",
        "schedule appointment on calendar",
        "book time slot in my agenda",
        # Plan and organize meetings
        "set up video call with attendees",
        "arrange meeting with colleagues",
        "plan recurring event on calendar",
        "block time for focus work",
        # Invite and location
        "invite people to calendar event",
        "add attendees to scheduled meeting",
        "set meeting location and time",
        "reserve conference room for event",
    ],
    parameters=[
        ParameterSchema(
            name="summary",
            type="string",
            required=True,
            description="Title",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
        ParameterSchema(
            name="start_datetime",
            type="string",
            required=True,
            description="Start in LOCAL time (user timezone), ISO WITHOUT offset e.g. '2025-01-15T19:00:00'. NEVER convert to UTC.",
            semantic_type="event_start_datetime",
        ),
        ParameterSchema(
            name="end_datetime",
            type="string",
            required=True,
            description="End in LOCAL time (user timezone), ISO WITHOUT offset e.g. '2025-01-15T20:00:00'. NEVER convert to UTC.",
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="timezone",
            type="string",
            required=False,
            description="IANA Timezone (e.g. 'Europe/Paris'). Ignored if dates have offsets.",
            semantic_type="timezone",
        ),
        _CALENDAR_ID_PARAM,
        ParameterSchema(
            name="description", type="string", required=False, description="Description"
        ),
        ParameterSchema(
            name="location",
            type="string",
            required=False,
            description="Location",
            semantic_type="physical_address",  # Cross-domain: can use contacts[].addresses[].formattedValue
        ),
        ParameterSchema(
            name="attendees",
            type="array",
            required=False,
            description="List of attendee email addresses. MUST be emails, NOT person names. To invite a person, first get their email from contacts.",
            semantic_type="email_address",  # Cross-domain: can use contacts[].emails[].value
        ),
        ParameterSchema(
            name="add_conference",
            type="boolean",
            required=False,
            description=(
                "Attach a video-conference link (Meet/Teams by provider). Set true "
                "when the user asks for a visio/video call/online meeting. "
                "Unsupported on Apple calendars (event created without a link)."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="event_id", type="string", description="Created ID", semantic_type="event_id"
        ),
        OutputFieldSchema(path="html_link", type="string", description="Link", semantic_type="URL"),
        OutputFieldSchema(path="summary", type="string", description="Title"),
        OutputFieldSchema(
            path="conference_link",
            type="string",
            nullable=True,
            description="Video join URL, only when the provider actually created one",
            semantic_type="URL",
        ),
    ],
    cost=CostProfile(est_tokens_in=200, est_tokens_out=100, est_cost_usd=0.01, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CALENDAR_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before creation)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    reference_examples=["event_id", "html_link", "summary"],
    version="1.2.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="➕", i18n_key="create_event", visible=True, category="tool"),
)

# ============================================================================
# 4. UPDATE EVENT
# ============================================================================
_update_desc = (
    "**Tool: update_event_tool** - Modify existing event. **REQUIRES HITL**.\n"
    "**Behavior**: Only provided fields are updated. Omitted fields unchanged."
)

update_event_catalogue_manifest = ToolManifest(
    name="update_event_tool",
    mutation_policy="draft",
    agent="event_agent",
    description=_update_desc,
    # Discriminant phrases - Calendar event modification
    semantic_keywords=[
        # Reschedule calendar event
        "reschedule meeting to different time",
        "move calendar event to another date",
        "change appointment time on schedule",
        "postpone event to later date",
        # Modify event details
        "update meeting location on calendar",
        "change event attendees list",
        "edit calendar event description",
        "modify meeting duration or time",
        # Extend or adjust
        "extend scheduled meeting time",
        "shorten calendar event duration",
        "add more attendees to event",
        "change conference room for meeting",
    ],
    parameters=[
        ParameterSchema(
            name="event_id",
            type="string",
            required=True,
            description="ID to update",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
            semantic_type="event_id",
        ),
        ParameterSchema(name="summary", type="string", required=False, description="New title"),
        ParameterSchema(
            name="start_datetime",
            type="string",
            required=False,
            description="New start in LOCAL time (user timezone), ISO WITHOUT offset. NEVER convert to UTC.",
            semantic_type="event_start_datetime",
        ),
        ParameterSchema(
            name="end_datetime",
            type="string",
            required=False,
            description="New end in LOCAL time (user timezone), ISO WITHOUT offset. NEVER convert to UTC.",
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="timezone",
            type="string",
            required=False,
            description="New timezone (if shifting zones)",
            semantic_type="timezone",
        ),
        ParameterSchema(
            name="description", type="string", required=False, description="New description"
        ),
        ParameterSchema(
            name="location",
            type="string",
            required=False,
            description="New location",
            semantic_type="physical_address",  # Cross-domain: can use contacts[].addresses[].formattedValue
        ),
        ParameterSchema(
            name="attendees",
            type="array",
            required=False,
            description="New list of attendee email addresses (replaces old). MUST be emails, NOT person names. To invite a person, first get their email from contacts.",
            semantic_type="email_address",  # Cross-domain: can use contacts[].emails[].value
        ),
        _CALENDAR_ID_PARAM,
    ],
    outputs=[
        OutputFieldSchema(
            path="event_id", type="string", description="Updated ID", semantic_type="event_id"
        ),
        OutputFieldSchema(path="html_link", type="string", description="Link", semantic_type="URL"),
        OutputFieldSchema(path="summary", type="string", description="Title"),
    ],
    cost=CostProfile(est_tokens_in=200, est_tokens_out=100, est_cost_usd=0.01, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CALENDAR_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before modification)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    reference_examples=["event_id", "html_link", "summary"],
    version="1.1.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="✏️", i18n_key="update_event", visible=True, category="tool"),
)

# ============================================================================
# 5. DELETE EVENT
# ============================================================================
_delete_desc = (
    "**Tool: delete_event_tool** - Delete calendar event. **REQUIRES HITL**. Destructive."
)

delete_event_catalogue_manifest = ToolManifest(
    name="delete_event_tool",
    mutation_policy="draft",
    agent="event_agent",
    description=_delete_desc,
    # Discriminant phrases - Calendar event deletion
    semantic_keywords=[
        # Cancel calendar event
        "cancel scheduled meeting on calendar",
        "delete event from my schedule",
        "remove appointment from calendar",
        "cancel upcoming calendar event",
        # Free up time
        "clear time slot on my calendar",
        "free up blocked time in schedule",
        "unschedule planned meeting",
        "remove calendar block",
    ],
    parameters=[
        ParameterSchema(
            name="event_id",
            type="string",
            required=True,
            description="ID to delete",
            semantic_type="event_id",
        ),
        ParameterSchema(
            name="send_updates",
            type="string",
            required=False,
            description="'all' (def), 'externalOnly', 'none'",
            semantic_type="send_updates_option",
        ),
        _CALENDAR_ID_PARAM,
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success status"),
        OutputFieldSchema(
            path="event_id", type="string", description="Deleted ID", semantic_type="event_id"
        ),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=50, est_cost_usd=0.01, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CALENDAR_SCOPES,
        # Draft-based: delete_event_tool returns requires_confirmation=True
        # (event_delete draft) → confirmed post-execution via draft_critique, exactly
        # like create/update and like delete_contact/delete_task. hitl_required MUST
        # stay False: the flag only drives ReAct's pre-execution interrupt, which for
        # a draft tool is redundant AND currently unrendered (silent hang).
        # Enforced by test_hitl_required_consistency.py.
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["success", "event_id"],
    version="1.1.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_event", visible=True, category="tool"),
)

# ============================================================================
# 6. LIST CALENDARS
# ============================================================================
_list_cal_desc = "**Tool: list_calendars_tool** - List available calendars to find 'calendar_id'."

list_calendars_catalogue_manifest = ToolManifest(
    name="list_calendars_tool",
    agent="event_agent",
    description=_list_cal_desc,
    # Discriminant phrases - Calendar list operations
    semantic_keywords=[
        # List available calendars
        "show all my available calendars",
        "list calendars I have access to",
        "which calendars are in my account",
        "display calendar names and IDs",
        # Calendar selection
        "find calendar ID for specific name",
        "show shared calendars I can view",
    ],
    parameters=[
        ParameterSchema(
            name="show_hidden", type="boolean", required=False, description="Include hidden"
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description="Max (def 100)",
            constraints=[ParameterConstraint(kind="maximum", value=250)],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="calendars", type="array", description="List"),
        OutputFieldSchema(
            path="calendars[].id",
            type="string",
            description="Calendar ID",
            semantic_type="calendar_id",
        ),
        OutputFieldSchema(path="calendars[].summary", type="string", description="Name"),
        OutputFieldSchema(
            path="calendars[].accessRole",
            type="string",
            description="Access",
            semantic_type="access_role",
        ),
        OutputFieldSchema(path="calendars[].primary", type="boolean", description="Is primary"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=300, est_cost_usd=0.001, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CALENDAR_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_fields=["id", "summary", "primary"],
    reference_examples=["calendars[0].id", "calendars[*].summary"],
    version="1.1.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📚", i18n_key="list_calendars", visible=True, category="tool"),
    initiative_eligible=False,  # Structural tool, not useful for proactive enrichment
)

# Registration collection for the catalogue loader (whole calendar family)
CALENDAR_TOOL_MANIFESTS: tuple[ToolManifest, ...] = (
    get_events_catalogue_manifest,
    find_availability_catalogue_manifest,
    create_event_catalogue_manifest,
    update_event_catalogue_manifest,
    delete_event_catalogue_manifest,
    list_calendars_catalogue_manifest,
)

__all__ = [
    # Unified tool (v2.0 - replaces search + details)
    "get_events_catalogue_manifest",
    # Availability (lot B)
    "find_availability_catalogue_manifest",
    # Action tools
    "create_event_catalogue_manifest",
    "update_event_catalogue_manifest",
    "delete_event_catalogue_manifest",
    # Metadata tools (list containers, not items)
    "list_calendars_catalogue_manifest",
    # Loader collection
    "CALENDAR_TOOL_MANIFESTS",
]
