"""
LangChain tools for agents.

Note: Legacy ToolCatalogue removed in Phase 5.
Tool manifests now managed via registry/catalogue_loader.py and
domain-specific catalogue_manifests.py files.

LOT 5.4: Added Calendar tools.
LOT 9: Added Drive and Tasks tools.
LOT 10: Added Weather and Wikipedia tools.
LOT 11: Added Perplexity and Places tools.
"""

from src.domains.agents.tools.base import APIKeyConnectorTool, ConnectorTool
from src.domains.agents.tools.brave_tools import (
    brave_news_tool,
    brave_search_tool,
)
from src.domains.agents.tools.calendar_tools import (
    create_event_tool,
    delete_event_tool,
    get_event_details_tool,
    search_events_tool,
    update_event_tool,
)
from src.domains.agents.tools.context_tools import (
    get_context_list,
    get_context_state,
    list_active_domains,
    resolve_reference,
    set_current_item,
)
from src.domains.agents.tools.drive_tools import (
    get_file_details_tool,
    list_files_tool,
    search_files_tool,
)
from src.domains.agents.tools.emails_tools import (
    delete_email_tool,
    forward_email_tool,
    get_email_details_tool,
    reply_email_tool,
    search_emails_tool,
    send_email_tool,
)
from src.domains.agents.tools.google_contacts_tools import (
    get_contact_details_tool,
    list_contacts_tool,
    search_contacts_tool,
)
from src.domains.agents.tools.labels_tools import (
    apply_labels_tool,
    create_label_tool,
    delete_label_tool,
    list_labels_tool,
    remove_labels_tool,
    update_label_tool,
)
from src.domains.agents.tools.local_query_tool import local_query_engine_tool
from src.domains.agents.tools.mixins import (
    ToolOutputMixin,
    create_tool_formatter,
)
from src.domains.agents.tools.output import StandardToolOutput, UnifiedToolOutput
from src.domains.agents.tools.perplexity_tools import (
    perplexity_ask_tool,
    perplexity_search_tool,
)
from src.domains.agents.tools.places_tools import (
    get_current_location_tool,
    get_place_details_tool,
    search_places_tool,
)
from src.domains.agents.tools.routes_tools import (
    RouteItem,
    get_route_matrix_tool,
    get_route_tool,
    should_trigger_hitl,
)
from src.domains.agents.tools.schemas import (
    ToolResponse,
    ToolResponseError,
    ToolResponseSuccess,
)
from src.domains.agents.tools.tasks_tools import (
    complete_task_tool,
    create_task_tool,
    list_task_lists_tool,
    list_tasks_tool,
)
from src.domains.agents.tools.weather_tools import (
    get_current_weather_tool,
    get_hourly_forecast_tool,
    get_weather_forecast_tool,
)
from src.domains.agents.tools.web_search_tools import (
    UnifiedWebSearchOutput,
    WebSearchResult,
    WikipediaResult,
    unified_web_search_tool,
)
from src.domains.agents.tools.wikipedia_tools import (
    get_wikipedia_article_tool,
    get_wikipedia_related_tool,
    get_wikipedia_summary_tool,
    search_wikipedia_tool,
)

# Sub-Agent Delegation Tool (F6 — feature-flagged)
# Conditional import: only load when SUB_AGENTS_ENABLED=true
try:
    from src.core.config import settings as _settings

    if getattr(_settings, "sub_agents_enabled", False):
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        _SUB_AGENT_TOOLS_AVAILABLE = True
    else:
        _SUB_AGENT_TOOLS_AVAILABLE = False
except Exception:
    _SUB_AGENT_TOOLS_AVAILABLE = False

# Browser Tools (F7 — auto-detected)
# Always try to import. No feature flag needed — activation is via admin connector panel.
# If Playwright is not installed, browser_tools.py imports fine (lazy Playwright imports).
try:
    from src.domains.agents.tools.browser_tools import (
        browser_click_tool,
        browser_fill_tool,
        browser_navigate_tool,
        browser_press_key_tool,
        browser_snapshot_tool,
        browser_task_tool,
    )

    _BROWSER_TOOLS_AVAILABLE = True
except Exception:
    _BROWSER_TOOLS_AVAILABLE = False

__all__ = [
    # Google Contacts Tools
    "search_contacts_tool",
    "list_contacts_tool",
    "get_contact_details_tool",
    # Gmail Tools
    "search_emails_tool",
    "get_email_details_tool",
    "send_email_tool",
    "reply_email_tool",
    "forward_email_tool",
    "delete_email_tool",
    # Gmail Labels Tools
    "list_labels_tool",
    "create_label_tool",
    "update_label_tool",
    "delete_label_tool",
    "apply_labels_tool",
    "remove_labels_tool",
    # Google Calendar Tools (LOT 5.4)
    "search_events_tool",
    "get_event_details_tool",
    "create_event_tool",
    "update_event_tool",
    "delete_event_tool",
    # Google Drive Tools (LOT 9)
    "search_files_tool",
    "list_files_tool",
    "get_file_details_tool",
    # Google Tasks Tools (LOT 9)
    "list_tasks_tool",
    "create_task_tool",
    "complete_task_tool",
    "list_task_lists_tool",
    # Weather Tools (LOT 10)
    "get_current_weather_tool",
    "get_weather_forecast_tool",
    "get_hourly_forecast_tool",
    # Wikipedia Tools (LOT 10)
    "search_wikipedia_tool",
    "get_wikipedia_summary_tool",
    "get_wikipedia_article_tool",
    "get_wikipedia_related_tool",
    # Perplexity Tools (LOT 11)
    "perplexity_search_tool",
    "perplexity_ask_tool",
    # Brave Search Tools
    "brave_search_tool",
    "brave_news_tool",
    # Web Search Tools (Unified Triple Source)
    "unified_web_search_tool",
    "UnifiedWebSearchOutput",
    "WebSearchResult",
    "WikipediaResult",
    # Google Places Tools (LOT 11)
    "search_places_tool",
    "get_place_details_tool",
    "get_current_location_tool",  # Reverse geocoding
    # Google Routes Tools
    "get_route_tool",
    "get_route_matrix_tool",
    "RouteItem",
    "should_trigger_hitl",
    # Context Tools
    "resolve_reference",
    "list_active_domains",
    "set_current_item",
    "get_context_state",
    "get_context_list",
    # LocalQueryEngine
    "local_query_engine_tool",
    # Schemas
    "ToolResponse",
    "ToolResponseSuccess",
    "ToolResponseError",
    # Tool output
    "StandardToolOutput",
    "UnifiedToolOutput",
    "ToolOutputMixin",
    "create_tool_formatter",
    # Base classes for custom tools
    "ConnectorTool",
    "APIKeyConnectorTool",
]

# Conditionally extend __all__ with sub-agent delegation tool
if _SUB_AGENT_TOOLS_AVAILABLE:
    __all__.extend(
        [
            "delegate_to_sub_agent_tool",
        ]
    )

# DevOps Tools (Claude CLI Remote Server Management — feature-flagged)
# Conditional import: only load when DEVOPS_ENABLED=true
_DEVOPS_TOOLS_AVAILABLE = False
try:
    from src.core.config import settings as _devops_settings

    if getattr(_devops_settings, "devops_enabled", False):
        from src.domains.agents.tools.devops_tools import claude_server_task_tool

        _DEVOPS_TOOLS_AVAILABLE = True
except Exception:
    _DEVOPS_TOOLS_AVAILABLE = False

# Conditionally extend __all__ with browser tools
if _BROWSER_TOOLS_AVAILABLE:
    __all__.extend(
        [
            "browser_task_tool",
            "browser_navigate_tool",
            "browser_snapshot_tool",
            "browser_click_tool",
            "browser_fill_tool",
            "browser_press_key_tool",
        ]
    )

# Conditionally extend __all__ with devops tools
if _DEVOPS_TOOLS_AVAILABLE:
    __all__.extend(
        [
            "claude_server_task_tool",
        ]
    )
