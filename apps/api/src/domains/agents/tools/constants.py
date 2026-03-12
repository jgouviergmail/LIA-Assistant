"""
Constants for agent tools.

Centralizes tool names and metadata to avoid magic strings and improve maintainability.
"""

# ============================================================================
# TOOL NAMES - Google Contacts
# ============================================================================

TOOL_NAME_SEARCH_CONTACTS = "search_contacts_tool"
TOOL_NAME_LIST_CONTACTS = "list_contacts_tool"
TOOL_NAME_GET_CONTACT_DETAILS = "get_contact_details_tool"

# All Google Contacts tools
ALL_CONTACTS_TOOLS = [
    TOOL_NAME_SEARCH_CONTACTS,
    TOOL_NAME_LIST_CONTACTS,
    TOOL_NAME_GET_CONTACT_DETAILS,
]

# ============================================================================
# TOOL NAMES - Context Management
# ============================================================================

TOOL_NAME_RESOLVE_REFERENCE = "resolve_reference"

# All context tools
ALL_CONTEXT_TOOLS = [
    TOOL_NAME_RESOLVE_REFERENCE,
]

# ============================================================================
# TOOL NAMES - Gmail (LOT 5)
# ============================================================================

TOOL_NAME_SEARCH_EMAILS = "search_emails_tool"
TOOL_NAME_SEND_EMAIL = "send_email_tool"
TOOL_NAME_GET_EMAIL_DETAILS = "get_email_details_tool"

# All Gmail tools
ALL_EMAILS_TOOLS = [
    TOOL_NAME_SEARCH_EMAILS,
    TOOL_NAME_SEND_EMAIL,
    TOOL_NAME_GET_EMAIL_DETAILS,
]

# ============================================================================
# TOOL NAMES - Google Calendar (LOT 9)
# ============================================================================

TOOL_NAME_SEARCH_EVENTS = "search_events_tool"
TOOL_NAME_CREATE_EVENT = "create_event_tool"
TOOL_NAME_UPDATE_EVENT = "update_event_tool"
TOOL_NAME_DELETE_EVENT = "delete_event_tool"
TOOL_NAME_GET_EVENT_DETAILS = "get_event_details_tool"

# All Calendar tools
ALL_CALENDAR_TOOLS = [
    TOOL_NAME_SEARCH_EVENTS,
    TOOL_NAME_CREATE_EVENT,
    TOOL_NAME_UPDATE_EVENT,
    TOOL_NAME_DELETE_EVENT,
    TOOL_NAME_GET_EVENT_DETAILS,
]

# ============================================================================
# TOOL NAMES - Google Drive (LOT 9)
# ============================================================================

TOOL_NAME_SEARCH_FILES = "search_files_tool"
TOOL_NAME_LIST_FILES = "list_files_tool"
TOOL_NAME_GET_FILE_DETAILS = "get_file_details_tool"

# All Drive tools
ALL_DRIVE_TOOLS = [
    TOOL_NAME_SEARCH_FILES,
    TOOL_NAME_LIST_FILES,
    TOOL_NAME_GET_FILE_DETAILS,
]

# ============================================================================
# TOOL NAMES - Google Tasks (LOT 9)
# ============================================================================

TOOL_NAME_LIST_TASKS = "list_tasks_tool"
TOOL_NAME_CREATE_TASK = "create_task_tool"
TOOL_NAME_COMPLETE_TASK = "complete_task_tool"
TOOL_NAME_LIST_TASK_LISTS = "list_task_lists_tool"

# All Tasks tools
ALL_TASKS_TOOLS = [
    TOOL_NAME_LIST_TASKS,
    TOOL_NAME_CREATE_TASK,
    TOOL_NAME_COMPLETE_TASK,
    TOOL_NAME_LIST_TASK_LISTS,
]

# ============================================================================
# TOOL NAMES - Weather (LOT 10)
# ============================================================================

TOOL_NAME_GET_CURRENT_WEATHER = "get_current_weather_tool"
TOOL_NAME_GET_WEATHER_FORECAST = "get_weather_forecast_tool"
TOOL_NAME_GET_HOURLY_FORECAST = "get_hourly_forecast_tool"

# All Weather tools
ALL_WEATHER_TOOLS = [
    TOOL_NAME_GET_CURRENT_WEATHER,
    TOOL_NAME_GET_WEATHER_FORECAST,
    TOOL_NAME_GET_HOURLY_FORECAST,
]

# ============================================================================
# TOOL NAMES - Wikipedia (LOT 10)
# ============================================================================

TOOL_NAME_SEARCH_WIKIPEDIA = "search_wikipedia_tool"
TOOL_NAME_GET_WIKIPEDIA_SUMMARY = "get_wikipedia_summary_tool"
TOOL_NAME_GET_WIKIPEDIA_ARTICLE = "get_wikipedia_article_tool"
TOOL_NAME_GET_WIKIPEDIA_RELATED = "get_wikipedia_related_tool"

# All Wikipedia tools
ALL_WIKIPEDIA_TOOLS = [
    TOOL_NAME_SEARCH_WIKIPEDIA,
    TOOL_NAME_GET_WIKIPEDIA_SUMMARY,
    TOOL_NAME_GET_WIKIPEDIA_ARTICLE,
    TOOL_NAME_GET_WIKIPEDIA_RELATED,
]

# ============================================================================
# TOOL NAMES - Perplexity (LOT 10)
# ============================================================================

TOOL_NAME_PERPLEXITY_SEARCH = "perplexity_search_tool"
TOOL_NAME_PERPLEXITY_ASK = "perplexity_ask_tool"

# All Perplexity tools
ALL_PERPLEXITY_TOOLS = [
    TOOL_NAME_PERPLEXITY_SEARCH,
    TOOL_NAME_PERPLEXITY_ASK,
]

# ============================================================================
# TOOL NAMES - Google Places (LOT 10)
# ============================================================================

TOOL_NAME_SEARCH_PLACES = "search_places_tool"
TOOL_NAME_GET_PLACE_DETAILS = "get_place_details_tool"

# All Places tools
ALL_PLACES_TOOLS = [
    TOOL_NAME_SEARCH_PLACES,
    TOOL_NAME_GET_PLACE_DETAILS,
]

# ============================================================================
# ALL TOOLS (Registry)
# ============================================================================

ALL_TOOLS = (
    ALL_CONTACTS_TOOLS
    + ALL_CONTEXT_TOOLS
    + ALL_EMAILS_TOOLS
    + ALL_CALENDAR_TOOLS
    + ALL_DRIVE_TOOLS
    + ALL_TASKS_TOOLS
    + ALL_WEATHER_TOOLS
    + ALL_WIKIPEDIA_TOOLS
    + ALL_PERPLEXITY_TOOLS
    + ALL_PLACES_TOOLS
)

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Google Contacts
    "TOOL_NAME_SEARCH_CONTACTS",
    "TOOL_NAME_LIST_CONTACTS",
    "TOOL_NAME_GET_CONTACT_DETAILS",
    "ALL_CONTACTS_TOOLS",
    # Context
    "TOOL_NAME_RESOLVE_REFERENCE",
    "ALL_CONTEXT_TOOLS",
    # Gmail
    "TOOL_NAME_SEARCH_EMAILS",
    "TOOL_NAME_SEND_EMAIL",
    "TOOL_NAME_GET_EMAIL_DETAILS",
    "ALL_EMAILS_TOOLS",
    # Calendar
    "TOOL_NAME_SEARCH_EVENTS",
    "TOOL_NAME_CREATE_EVENT",
    "TOOL_NAME_UPDATE_EVENT",
    "TOOL_NAME_DELETE_EVENT",
    "TOOL_NAME_GET_EVENT_DETAILS",
    "ALL_CALENDAR_TOOLS",
    # Drive
    "TOOL_NAME_SEARCH_FILES",
    "TOOL_NAME_LIST_FILES",
    "TOOL_NAME_GET_FILE_DETAILS",
    "ALL_DRIVE_TOOLS",
    # Tasks
    "TOOL_NAME_LIST_TASKS",
    "TOOL_NAME_CREATE_TASK",
    "TOOL_NAME_COMPLETE_TASK",
    "TOOL_NAME_LIST_TASK_LISTS",
    "ALL_TASKS_TOOLS",
    # Weather
    "TOOL_NAME_GET_CURRENT_WEATHER",
    "TOOL_NAME_GET_WEATHER_FORECAST",
    "TOOL_NAME_GET_HOURLY_FORECAST",
    "ALL_WEATHER_TOOLS",
    # Wikipedia
    "TOOL_NAME_SEARCH_WIKIPEDIA",
    "TOOL_NAME_GET_WIKIPEDIA_SUMMARY",
    "TOOL_NAME_GET_WIKIPEDIA_ARTICLE",
    "TOOL_NAME_GET_WIKIPEDIA_RELATED",
    "ALL_WIKIPEDIA_TOOLS",
    # Perplexity
    "TOOL_NAME_PERPLEXITY_SEARCH",
    "TOOL_NAME_PERPLEXITY_ASK",
    "ALL_PERPLEXITY_TOOLS",
    # Places
    "TOOL_NAME_SEARCH_PLACES",
    "TOOL_NAME_GET_PLACE_DETAILS",
    "ALL_PLACES_TOOLS",
    # Registry
    "ALL_TOOLS",
]
