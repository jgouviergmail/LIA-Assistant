"""
Constants for agents domain.

Centralizes hardcoded values to improve maintainability and reduce magic strings.
"""

from src.core.constants import (
    CONTEXT_REFERENCE_CONFIDENCE_THRESHOLD_DEFAULT,
)

# ============================================================================
# NODE NAMES (used in graph construction and routing)
# ============================================================================

# Core graph nodes (used as keys in graph.add_node())
NODE_ROUTER = "router"
NODE_RESPONSE = "response"
NODE_TASK_ORCHESTRATOR = "task_orchestrator"
NODE_PLANNER = "planner"  # Phase 5: LLM-based plan generation
NODE_SEMANTIC_VALIDATOR = "semantic_validator"  # Phase 2 OPTIMPLAN: Semantic validation of plans
NODE_CLARIFICATION = "clarification"  # Phase 2 OPTIMPLAN: Clarification HITL node
NODE_APPROVAL_GATE = "approval_gate"  # Phase 8: Plan-level HITL approval before execution
# Context Compaction: Summarize old conversation history before routing
NODE_COMPACTION = "compaction"  # 2026-03: Intelligent context compaction node
# HITL Dispatch: Generic HITL handler supporting draft_critique, entity_disambiguation, tool_confirmation
NODE_HITL_DISPATCH = "hitl_dispatch"  # 2025-12-23: Generic HITL dispatch node
NODE_DRAFT_CRITIQUE = NODE_HITL_DISPATCH  # Backward compatibility alias

# Agent nodes (NAMING: domain=entity(singular), agent=domain+"_agent")
NODE_QUERY_AGENT = "query_agent"  # INTELLIA: LocalQueryEngine agent
NODE_WEATHER_AGENT = "weather_agent"  # LOT 10: Weather API agent
NODE_WIKIPEDIA_AGENT = "wikipedia_agent"  # LOT 10: Wikipedia API agent
NODE_PERPLEXITY_AGENT = "perplexity_agent"  # LOT 11: Perplexity internet search
NODE_BRAVE_AGENT = "brave_agent"  # Brave Search web/news search
NODE_WEB_SEARCH_AGENT = "web_search_agent"  # Unified web search (Perplexity + Brave + Wikipedia)
NODE_WEB_FETCH_AGENT = "web_fetch_agent"  # Web page content fetching (evolution F1)
NODE_BROWSER_AGENT = "browser_agent"  # Interactive web browsing (evolution F7)
NODE_HUE_AGENT = "hue_agent"  # Philips Hue smart lighting (Smart Home)

# ============================================================================
# AGENT NAMES (used in orchestration and result tracking)
# ============================================================================

AGENT_CONTACT = "contact_agent"
AGENT_EMAIL = "email_agent"
AGENT_EVENT = "event_agent"  # Was calendar_agent (domain=event)
AGENT_FILE = "file_agent"  # Was drive_agent (domain=file)
AGENT_TASK = "task_agent"
AGENT_QUERY = "query_agent"  # INTELLIA: LocalQueryEngine agent
AGENT_WEATHER = "weather_agent"  # LOT 10: Weather API agent
AGENT_WIKIPEDIA = "wikipedia_agent"  # LOT 10: Wikipedia API agent
AGENT_PERPLEXITY = "perplexity_agent"  # LOT 11: Internet search via Perplexity
AGENT_PLACE = "place_agent"  # LOT 11: Google Places location search (domain=place)
AGENT_ROUTE = "route_agent"  # LOT 12: Google Routes directions (domain=route)
AGENT_BRAVE = "brave_agent"  # Brave Search web/news search
AGENT_WEB_SEARCH = "web_search_agent"  # Unified web search meta-agent
AGENT_WEB_FETCH = "web_fetch_agent"  # Web page content fetching (evolution F1)
AGENT_MCP = "mcp_agent"  # Virtual agent grouping all MCP tools (evolution F2)
AGENT_BROWSER = "browser_agent"  # Interactive web browsing (evolution F7)
AGENT_HUE = "hue_agent"  # Philips Hue smart lighting (Smart Home)
AGENT_IMAGE = "image_generation_agent"  # AI image generation (evolution)

# Per-server MCP domain prefix (evolution F2.2)
# Each user MCP server gets its own domain: mcp_<slugified_server_name>
MCP_DOMAIN_PREFIX = "mcp_"

# Agent registry (all available agents)
ALL_AGENTS = [
    AGENT_CONTACT,
    AGENT_EMAIL,
    AGENT_QUERY,  # INTELLIA: LocalQueryEngine agent
    AGENT_EVENT,  # Events/Calendar operations
    AGENT_FILE,  # Files/Drive operations
    AGENT_TASK,  # Tasks operations
    AGENT_WEATHER,  # Weather queries
    AGENT_WIKIPEDIA,  # Wikipedia searches
    AGENT_PERPLEXITY,  # Internet search
    AGENT_PLACE,  # Location search
    AGENT_ROUTE,  # Google Routes directions
    AGENT_BRAVE,  # Brave Search web/news
    AGENT_WEB_SEARCH,  # Unified web search
    AGENT_WEB_FETCH,  # Web page content fetching
    AGENT_MCP,  # MCP external tools (virtual agent, evolution F2)
    AGENT_BROWSER,  # Interactive web browsing (evolution F7)
    AGENT_HUE,  # Philips Hue smart lighting (Smart Home)
]

# ============================================================================
# ROUTER INTENTIONS (routing decisions)
# ============================================================================
# Convention v3.2:
# - Variable: INTENTION_{DOMAIN}_{ACTION} with singular domain name
# - Value: "{domain}_{action}" with singular domain name
# - Generic domain intention: INTENTION_{DOMAIN} = "{domain}"

# Generic intentions
INTENTION_CONVERSATION = "conversation"  # Simple conversation, no tools needed
INTENTION_UNKNOWN = "unknown"  # Unknown intention
INTENTION_COMPLEX_MULTI_STEP = "complex_multi_step"  # Phase 5: Complex query requiring planner

# Contact domain (singular)
INTENTION_CONTACT = "contact"  # Contact-related (generic)
INTENTION_CONTACT_SEARCH = "contact_search"  # Search contacts
INTENTION_CONTACT_LIST = "contact_list"  # List all contacts
INTENTION_CONTACT_DETAILS = "contact_details"  # Get contact details

# Email domain (singular)
INTENTION_EMAIL = "email"  # Email-related (generic)
INTENTION_EMAIL_SEARCH = "email_search"  # Search emails
INTENTION_EMAIL_READ = "email_read"  # Read email details
INTENTION_EMAIL_SEND = "email_send"  # Send email

# Event domain (was calendar)
INTENTION_EVENT = "event"  # Event-related (generic)
INTENTION_EVENT_LIST = "event_list"  # List events
INTENTION_EVENT_CREATE = "event_create"  # Create event

# File domain (was drive)
INTENTION_FILE = "file"  # File-related (generic)
INTENTION_FILE_SEARCH = "file_search"  # Search files
INTENTION_FILE_READ = "file_read"  # Read file content

# Task domain (singular)
INTENTION_TASK = "task"  # Task-related (generic)
INTENTION_TASK_LIST = "task_list"  # List tasks
INTENTION_TASK_CREATE = "task_create"  # Create task

# Weather domain
INTENTION_WEATHER = "weather"  # Weather-related (generic)
INTENTION_WEATHER_CURRENT = "weather_current"  # Get current weather
INTENTION_WEATHER_FORECAST = "weather_forecast"  # Get weather forecast

# Wikipedia domain
INTENTION_WIKIPEDIA = "wikipedia"  # Wikipedia-related (generic)
INTENTION_WIKIPEDIA_SEARCH = "wikipedia_search"  # Search Wikipedia
INTENTION_WIKIPEDIA_ARTICLE = "wikipedia_article"  # Get Wikipedia article

# Perplexity domain
INTENTION_PERPLEXITY = "perplexity"  # Perplexity web search (generic)
INTENTION_PERPLEXITY_SEARCH = "perplexity_search"  # Search web

# Place domain
INTENTION_PLACE = "place"  # Place-related (generic)
INTENTION_PLACE_SEARCH = "place_search"  # Search places

# Route domain
INTENTION_ROUTE = "route"  # Route-related (generic)
INTENTION_ROUTE_DIRECTIONS = "route_directions"  # Get directions

# Brave domain
INTENTION_BRAVE = "brave"  # Brave-related (generic)
INTENTION_BRAVE_SEARCH = "brave_search"  # Brave web search
INTENTION_BRAVE_NEWS = "brave_news"  # Brave news search

# Web Search domain (unified meta-search)
INTENTION_WEB_SEARCH = "web_search"  # Unified web search

# Web Fetch domain (page content extraction, evolution F1)
INTENTION_WEB_FETCH = "web_fetch"  # Fetch and read a web page

# Browser domain (interactive web browsing, evolution F7)
INTENTION_BROWSER = "browser"  # Browser-related (generic)
INTENTION_BROWSER_NAVIGATE = "browser_navigate"  # Navigate to a page
INTENTION_BROWSER_INTERACT = "browser_interact"  # Click, fill, interact with page

# Hue domain (smart home lighting)
INTENTION_HUE = "hue"  # Hue-related (generic)
INTENTION_HUE_CONTROL = "hue_control"  # Control lights/rooms
INTENTION_HUE_LIST = "hue_list"  # List lights/rooms/scenes
INTENTION_HUE_SCENE = "hue_scene"  # Activate scene

# ============================================================================
# CONTEXT TYPES (for context management and state)
# ============================================================================

# Context domain names - MUST match DomainConfig.result_key in domain_taxonomy.py
# These are the canonical keys for $steps.STEP_ID.{key} references in planner.
# The executor uses meta.domain directly as the key for structured_data.
# IMPORTANT: Keep in sync with domain_taxonomy.py result_keys!
CONTEXT_DOMAIN_CONTACTS = "contacts"
CONTEXT_DOMAIN_EMAILS = "emails"
CONTEXT_DOMAIN_EVENTS = "events"
CONTEXT_DOMAIN_CALENDARS = "calendars"  # List of calendars (distinct from events)
CONTEXT_DOMAIN_FILES = "files"
CONTEXT_DOMAIN_TASKS = "tasks"
CONTEXT_DOMAIN_WEATHER = "weathers"  # Aligned with result_key (was "weather_forecast")

# LOT 10-11: New agents context domains (all follow domain + "s" pattern)
CONTEXT_DOMAIN_WIKIPEDIA = "wikipedias"  # domain + "s" pattern
CONTEXT_DOMAIN_PERPLEXITY = "perplexitys"  # domain + "s" pattern
CONTEXT_DOMAIN_PLACES = "places"
CONTEXT_DOMAIN_LOCATION = "locations"
CONTEXT_DOMAIN_QUERY = "querys"  # domain + "s" pattern
CONTEXT_DOMAIN_ROUTES = "routes"
CONTEXT_DOMAIN_BRAVE = "braves"  # domain + "s" pattern
CONTEXT_DOMAIN_WEB_SEARCH = "web_searchs"  # domain + "s" pattern
CONTEXT_DOMAIN_WEB_FETCH = "web_fetchs"  # domain + "s" pattern (evolution F1)
CONTEXT_DOMAIN_MCP = "mcps"  # domain + "s" pattern (evolution F2)
CONTEXT_DOMAIN_MCP_APPS = "mcp_apps"  # MCP Apps interactive widgets (evolution F2.5)
CONTEXT_DOMAIN_BROWSERS = "browsers"  # Interactive web browsing (evolution F7)
CONTEXT_DOMAIN_HUE = "hues"  # Philips Hue smart lights (Smart Home)

# Web Search sources (used by unified_web_search_tool)
WEB_SEARCH_SOURCE_PERPLEXITY = "perplexity"
WEB_SEARCH_SOURCE_BRAVE = "brave"
WEB_SEARCH_SOURCE_WIKIPEDIA = "wikipedia"
WEB_SEARCH_ALL_SOURCES: list[str] = [
    WEB_SEARCH_SOURCE_PERPLEXITY,
    WEB_SEARCH_SOURCE_BRAVE,
    WEB_SEARCH_SOURCE_WIKIPEDIA,
]

# Context type names (used in Store namespace)
CONTEXT_TYPE_CONTACTS_LIST = "contacts_list"
CONTEXT_TYPE_CONTACTS_ITEM = "contacts_item"
CONTEXT_TYPE_EMAILS_LIST = "emails_list"
CONTEXT_TYPE_EMAILS_ITEM = "emails_item"
CONTEXT_TYPE_EVENTS_LIST = "events_list"
CONTEXT_TYPE_EVENTS_ITEM = "events_item"
CONTEXT_TYPE_FILES_LIST = "files_list"
CONTEXT_TYPE_FILES_ITEM = "files_item"
CONTEXT_TYPE_TASKS_LIST = "tasks_list"
CONTEXT_TYPE_TASKS_ITEM = "tasks_item"

# All context types
ALL_CONTEXT_TYPES = [
    CONTEXT_TYPE_CONTACTS_LIST,
    CONTEXT_TYPE_CONTACTS_ITEM,
    CONTEXT_TYPE_EMAILS_LIST,
    CONTEXT_TYPE_EMAILS_ITEM,
    CONTEXT_TYPE_EVENTS_LIST,
    CONTEXT_TYPE_EVENTS_ITEM,
    CONTEXT_TYPE_FILES_LIST,
    CONTEXT_TYPE_FILES_ITEM,
    CONTEXT_TYPE_TASKS_LIST,
    CONTEXT_TYPE_TASKS_ITEM,
]

# ============================================================================
# STATE KEYS (for MessagesState dictionary keys)
# ============================================================================

STATE_KEY_MESSAGES = "messages"
STATE_KEY_METADATA = "metadata"
STATE_KEY_ROUTING_HISTORY = "routing_history"
STATE_KEY_AGENT_RESULTS = "agent_results"
STATE_KEY_ORCHESTRATION_PLAN = "orchestration_plan"
STATE_KEY_CURRENT_TURN_ID = "current_turn_id"
STATE_KEY_USER_ID = "user_id"
STATE_KEY_SESSION_ID = "session_id"
STATE_KEY_EXECUTION_PLAN = "execution_plan"  # Phase 5: ExecutionPlan from planner
STATE_KEY_PLANNER_METADATA = (
    "planner_metadata"  # Phase 5: Planner metadata for streaming to frontend
)
STATE_KEY_PLANNER_ERROR = (
    "planner_error"  # Phase 5: Planner error/warning for streaming to frontend
)
STATE_KEY_VALIDATION_RESULT = "validation_result"  # Phase 8: ValidationResult from planner
STATE_KEY_SEMANTIC_VALIDATION = "semantic_validation"  # Phase 2 OPTIMPLAN: SemanticValidationResult
STATE_KEY_CLARIFICATION_RESPONSE = "clarification_response"  # Phase 2 OPTIMPLAN: User clarification
STATE_KEY_CLARIFICATION_FIELD = (
    "clarification_field"  # Field name for which clarification was asked
)
STATE_KEY_PLANNER_ITERATION = (
    "planner_iteration"  # Phase 2 OPTIMPLAN: Iteration counter for feedback loop
)
STATE_KEY_NEEDS_REPLAN = "needs_replan"  # Phase 2 OPTIMPLAN: Flag to trigger planner regeneration
STATE_KEY_REPLAN_INSTRUCTIONS = "replan_instructions"  # Instructions for planner when replanning
STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS = (
    "exclude_sub_agent_tools"  # F6: Exclude sub-agent tools from catalogue during replan
)
STATE_KEY_APPROVAL_EVALUATION = "approval_evaluation"  # Phase 8: ApprovalEvaluation result
STATE_KEY_PLAN_APPROVED = "plan_approved"  # Phase 8: Boolean flag if plan approved
STATE_KEY_PLAN_REJECTION_REASON = "plan_rejection_reason"  # Phase 8: Rejection reason if rejected
STATE_KEY_FOR_EACH_CANCELLED = (
    "for_each_cancelled"  # For-each HITL: Bulk operation cancelled by user
)
STATE_KEY_FOR_EACH_CANCELLATION_REASON = (
    "cancellation_reason"  # For-each HITL: Reason for cancellation (for response_node context)
)

# Context resolution state keys
STATE_KEY_LAST_ACTION_TURN_ID = "last_action_turn_id"  # Last turn with agent execution
STATE_KEY_LAST_LIST_TURN_ID = (
    "last_list_turn_id"  # Last turn with LIST results (search/list tools) - for ordinal resolution
)
STATE_KEY_LAST_LIST_DOMAIN = (
    "last_list_domain"  # Domain of the last list/search action - for ordinal resolution by domain
)
STATE_KEY_TURN_TYPE = "turn_type"  # Turn type: action|reference|conversational
STATE_KEY_RESOLVED_CONTEXT = "resolved_context"  # Resolved reference context
STATE_KEY_DETECTED_INTENT = (
    "detected_intent"  # SemanticIntentDetector result (action/detail/search/list)
)

# Memory reference resolution state keys (Pre-Planner)
STATE_KEY_RESOLVED_REFERENCES = "resolved_references"  # ResolvedReferences from memory resolution

# ============================================================================
# TURN TYPES (for context resolution)
# ============================================================================

TURN_TYPE_ACTION = "action"  # Turn with agent execution
TURN_TYPE_REFERENCE = "reference"  # Follow-up referencing previous results (legacy)
TURN_TYPE_REFERENCE_PURE = "reference_pure"  # Pure detail query ("detail of the first")
TURN_TYPE_REFERENCE_ACTION = "reference_action"  # Action with reference ("envoie-lui")
TURN_TYPE_CONVERSATIONAL = "conversational"  # Pure conversation

# ============================================================================
# CONTEXT RESOLUTION DEFAULTS
# ============================================================================


def get_context_reference_confidence_threshold() -> float:
    """Get context reference confidence threshold from settings."""
    try:
        from src.core.config import get_settings

        return get_settings().context_reference_confidence_threshold
    except Exception:
        from src.core.constants import CONTEXT_REFERENCE_CONFIDENCE_THRESHOLD_DEFAULT

        return CONTEXT_REFERENCE_CONFIDENCE_THRESHOLD_DEFAULT


def _get_setting_with_fallback(setting_name: str, fallback_constant: str) -> float:
    """Get a settings value with fallback to constant."""
    try:
        from src.core.config import get_settings

        return float(getattr(get_settings(), setting_name))
    except Exception:
        from src.core import constants

        return float(getattr(constants, fallback_constant))


CONTEXT_REFERENCE_CONFIDENCE_THRESHOLD = (
    CONTEXT_REFERENCE_CONFIDENCE_THRESHOLD_DEFAULT  # Use constant, settings accessed at runtime
)

# ============================================================================
# LOGGING AND PREVIEW LIMITS
# ============================================================================

LOGGING_CONTENT_PREVIEW_CHARS = 300  # Max chars in log content previews
LOGGING_SUMMARY_PREVIEW_CHARS = 200  # Max chars in log summary previews
RESPONSE_LIST_PREVIEW_ITEMS = 5  # Items to preview before truncation
RESPONSE_MAX_ERRORS_DISPLAY = 3  # Max errors to display in response
PLANNER_ERROR_JSON_PREVIEW_CHARS = 1000  # Max chars of invalid JSON in errors
PLANNER_CONTEXT_ITEMS_PREVIEW = 5  # Context items in planner summary
PLANNER_EMAIL_SUBJECT_PREVIEW_CHARS = 50  # Max chars of email subject in preview

# ============================================================================
# METADATA KEYS (for metadata dictionary)
# ============================================================================

METADATA_KEY_RUN_ID = "run_id"
METADATA_KEY_USER_ID = "user_id"
METADATA_KEY_SESSION_ID = "session_id"
METADATA_KEY_CONVERSATION_ID = "conversation_id"
METADATA_KEY_INTENTION = "intention"
METADATA_KEY_CONFIDENCE = "confidence"

# ============================================================================
# AGENT RESULT KEYS (for agent_results dictionary composite keys)
# ============================================================================


def make_agent_result_key(turn_id: int, agent_name: str) -> str:
    """
    Create composite key for agent_results dictionary.

    Format: "turn_id:agent_name" (e.g., "3:contacts_agent")

    Args:
        turn_id: Conversation turn counter
        agent_name: Agent identifier

    Returns:
        Composite key string
    """
    return f"{turn_id}:{agent_name}"


def parse_agent_result_key(key: str) -> tuple[int, str]:
    """
    Parse composite agent result key.

    Args:
        key: Composite key (e.g., "3:contacts_agent")

    Returns:
        Tuple of (turn_id, agent_name)

    Raises:
        ValueError: If key format is invalid
    """
    parts = key.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid agent result key format: {key}")

    try:
        turn_id = int(parts[0])
    except ValueError as e:
        raise ValueError(f"Invalid turn_id in key {key}: {parts[0]}") from e

    agent_name = parts[1]
    return turn_id, agent_name


# ============================================================================
# HITL (Human-in-the-Loop) CONSTANTS
# ============================================================================

# Action request fields
HITL_ACTION_NAME = "name"
HITL_ACTION_ARGS = "args"


# ============================================================================
# LIMITS AND THRESHOLDS
# ============================================================================

# Agent results retention (memory management)
# These are DEFAULT values - actual values come from config/agents.py (overridable via .env)
MAX_AGENT_RESULTS_DEFAULT = 10  # Keep max 10 agent results in state
MAX_ROUTING_HISTORY_DEFAULT = 30  # Keep max 30 routing history entries in state

# Router confidence thresholds (defined in src/core/config.py Settings)
# ROUTER_CONFIDENCE_HIGH, ROUTER_CONFIDENCE_MEDIUM, ROUTER_CONFIDENCE_LOW removed
# Use Settings.router_confidence_high, Settings.router_confidence_medium, Settings.router_confidence_low

# ============================================================================
# RATE LIMITING (Tool execution limits)
# ============================================================================

# Rate limit scope options
RATE_LIMIT_SCOPE_USER = "user"  # Per-user isolation (recommended for security)
RATE_LIMIT_SCOPE_GLOBAL = "global"  # Shared across all users

# Default rate limits (calls per minute)
# Note: Individual tools can override these defaults via Settings
# Read operations (search, list, get) - Higher limit
RATE_LIMIT_DEFAULT_READ_CALLS = 20
RATE_LIMIT_DEFAULT_READ_WINDOW_SECONDS = 60

# Write operations (create, update, delete, send) - Lower limit
RATE_LIMIT_DEFAULT_WRITE_CALLS = 5
RATE_LIMIT_DEFAULT_WRITE_WINDOW_SECONDS = 60

# Expensive operations (export, bulk) - Very low limit
RATE_LIMIT_DEFAULT_EXPENSIVE_CALLS = 2
RATE_LIMIT_DEFAULT_EXPENSIVE_WINDOW_SECONDS = 300  # 5 minutes

# ============================================================================
# TOOL NAMES (for tool registry and orchestration)
# ============================================================================

# LocalQueryEngine tool (INTELLIA)
TOOL_LOCAL_QUERY_ENGINE = "local_query_engine_tool"

# ============================================================================
# ORCHESTRATION MODES (execution patterns)
# ============================================================================

EXECUTION_MODE_SEQUENTIAL = "sequential"  # V1: Sequential agent execution
EXECUTION_MODE_PARALLEL = "parallel"  # V2 (future): Parallel execution

# ============================================================================
# AGENT STATUS VALUES (agent result states)
# ============================================================================

STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_CONNECTOR_DISABLED = "connector_disabled"

ALL_AGENT_STATUSES = [
    STATUS_SUCCESS,
    STATUS_ERROR,
    STATUS_CONNECTOR_DISABLED,
]


# ============================================================================
# GRAPH EDGES (for routing logic)
# ============================================================================

# Special edges
EDGE_END = "__end__"
EDGE_START = "__start__"

# ============================================================================
# SSE EVENT TYPES (Server-Sent Events streaming)
# ============================================================================

SSE_EVENT_START = "start"
SSE_EVENT_CHUNK = "chunk"
SSE_EVENT_END = "end"
SSE_EVENT_ERROR = "error"
SSE_EVENT_HITL_REQUIRED = "hitl_required"

# ============================================================================
# PROMPT TEMPLATES (centralized for consistency)
# ============================================================================

# Note: Actual prompt templates are in prompts.py
# This section reserves space for template identifiers if needed

# ============================================================================
# HITL ACTION TYPES (Human-in-the-Loop classification)
# ============================================================================

# Action type identifiers (used in HITL classifier for contextual prompts)
ACTION_TYPE_SEARCH = "recherche"
ACTION_TYPE_SEND = "envoi"
ACTION_TYPE_DELETE = "suppression"
ACTION_TYPE_CREATE = "creation"
ACTION_TYPE_UPDATE = "modification"
ACTION_TYPE_LIST = "liste"
ACTION_TYPE_GET = "récupération"
ACTION_TYPE_FORWARD = "transfert"
ACTION_TYPE_REPLY = "réponse"
ACTION_TYPE_GENERIC = "action"
ACTION_TYPE_PLAN_APPROVAL = "plan_approval"  # Issue #61: Plan-level HITL approval
ACTION_TYPE_DRAFT_CRITIQUE = "draft_critique"  # Draft review before execution
ACTION_TYPE_FOR_EACH_CONFIRMATION = "for_each_confirmation"  # FOR_EACH bulk operation HITL

# HITL decision types (classifier output)
HITL_DECISION_APPROVE = "APPROVE"
HITL_DECISION_REJECT = "REJECT"
HITL_DECISION_EDIT = "EDIT"
HITL_DECISION_AMBIGUOUS = "AMBIGUOUS"
HITL_DECISION_NEW_REQUEST = "NEW_REQUEST"  # Stale HITL state - treat as new message


# ============================================================================
# REGISTRY ITEM TYPES (for registry storage)
# ============================================================================
# FIX 2026-01-11: Centralized registry item type constants to eliminate magic strings

REGISTRY_TYPE_CONTACT = "contact"
REGISTRY_TYPE_EMAIL = "email"
REGISTRY_TYPE_EVENT = "event"
REGISTRY_TYPE_FILE = "file"
REGISTRY_TYPE_TASK = "task"
REGISTRY_TYPE_DRAFT = "draft"

# ============================================================================
# GOOGLE PEOPLE API FIELD NAMES (contact data structure)
# ============================================================================
# FIX 2026-01-11: Centralized field names for Google People API responses

PEOPLE_API_FIELD_NAMES = "names"
PEOPLE_API_FIELD_DISPLAY_NAME = "displayName"
PEOPLE_API_FIELD_EMAIL_ADDRESSES = "emailAddresses"
PEOPLE_API_FIELD_VALUE = "value"

# Default values for contact parsing
DEFAULT_CONTACT_NAME = "Contact"

# ============================================================================
# DEPRECATION NOTICES
# ============================================================================

# None currently

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Node names
    "NODE_ROUTER",
    "NODE_RESPONSE",
    "NODE_TASK_ORCHESTRATOR",
    "NODE_PLANNER",
    "NODE_SEMANTIC_VALIDATOR",
    "NODE_CLARIFICATION",
    "NODE_APPROVAL_GATE",
    "NODE_COMPACTION",
    "NODE_DRAFT_CRITIQUE",
    "NODE_HITL_DISPATCH",
    "NODE_QUERY_AGENT",
    "NODE_WEATHER_AGENT",
    "NODE_WIKIPEDIA_AGENT",
    "NODE_PERPLEXITY_AGENT",
    "NODE_BRAVE_AGENT",
    "NODE_WEB_SEARCH_AGENT",
    "NODE_WEB_FETCH_AGENT",
    "NODE_BROWSER_AGENT",
    "NODE_HUE_AGENT",
    # Agent names (v3.2 convention: singular domain names)
    "AGENT_CONTACT",
    "AGENT_EMAIL",
    "AGENT_EVENT",
    "AGENT_FILE",
    "AGENT_TASK",
    "AGENT_QUERY",
    "AGENT_WEATHER",
    "AGENT_WIKIPEDIA",
    "AGENT_PERPLEXITY",
    "AGENT_PLACE",
    "AGENT_ROUTE",
    "AGENT_BRAVE",
    "AGENT_WEB_SEARCH",
    "AGENT_WEB_FETCH",
    "AGENT_MCP",
    "AGENT_BROWSER",
    "AGENT_HUE",
    "MCP_DOMAIN_PREFIX",
    "ALL_AGENTS",
    # Tool names
    "TOOL_LOCAL_QUERY_ENGINE",
    # Intentions (canonical - singular domain names)
    "INTENTION_CONVERSATION",
    "INTENTION_UNKNOWN",
    "INTENTION_COMPLEX_MULTI_STEP",
    "INTENTION_CONTACT",
    "INTENTION_CONTACT_SEARCH",
    "INTENTION_CONTACT_LIST",
    "INTENTION_CONTACT_DETAILS",
    "INTENTION_EMAIL",
    "INTENTION_EMAIL_SEARCH",
    "INTENTION_EMAIL_READ",
    "INTENTION_EMAIL_SEND",
    "INTENTION_EVENT",
    "INTENTION_EVENT_LIST",
    "INTENTION_EVENT_CREATE",
    "INTENTION_FILE",
    "INTENTION_FILE_SEARCH",
    "INTENTION_FILE_READ",
    "INTENTION_TASK",
    "INTENTION_TASK_LIST",
    "INTENTION_TASK_CREATE",
    "INTENTION_WEATHER",
    "INTENTION_WEATHER_CURRENT",
    "INTENTION_WEATHER_FORECAST",
    "INTENTION_WIKIPEDIA",
    "INTENTION_WIKIPEDIA_SEARCH",
    "INTENTION_WIKIPEDIA_ARTICLE",
    "INTENTION_PERPLEXITY",
    "INTENTION_PERPLEXITY_SEARCH",
    "INTENTION_PLACE",
    "INTENTION_PLACE_SEARCH",
    "INTENTION_ROUTE",
    "INTENTION_ROUTE_DIRECTIONS",
    "INTENTION_BRAVE",
    "INTENTION_BRAVE_SEARCH",
    "INTENTION_BRAVE_NEWS",
    "INTENTION_WEB_SEARCH",
    "INTENTION_WEB_FETCH",
    "INTENTION_BROWSER",
    "INTENTION_BROWSER_NAVIGATE",
    "INTENTION_BROWSER_INTERACT",
    "INTENTION_HUE",
    "INTENTION_HUE_CONTROL",
    "INTENTION_HUE_LIST",
    "INTENTION_HUE_SCENE",
    # Context types
    "CONTEXT_DOMAIN_CONTACTS",
    "CONTEXT_DOMAIN_WEATHER",
    "CONTEXT_DOMAIN_PLACES",
    "CONTEXT_DOMAIN_LOCATION",
    "CONTEXT_DOMAIN_ROUTES",
    "CONTEXT_DOMAIN_BRAVE",
    "CONTEXT_DOMAIN_WEB_SEARCH",
    "CONTEXT_DOMAIN_WEB_FETCH",
    "CONTEXT_DOMAIN_MCP",
    "CONTEXT_DOMAIN_MCP_APPS",
    "CONTEXT_DOMAIN_BROWSERS",
    "CONTEXT_DOMAIN_HUE",
    "WEB_SEARCH_SOURCE_PERPLEXITY",
    "WEB_SEARCH_SOURCE_BRAVE",
    "WEB_SEARCH_SOURCE_WIKIPEDIA",
    "WEB_SEARCH_ALL_SOURCES",
    "CONTEXT_TYPE_CONTACTS_LIST",
    "CONTEXT_TYPE_CONTACTS_ITEM",
    "ALL_CONTEXT_TYPES",
    # State keys
    "STATE_KEY_MESSAGES",
    "STATE_KEY_METADATA",
    "STATE_KEY_ROUTING_HISTORY",
    "STATE_KEY_AGENT_RESULTS",
    "STATE_KEY_ORCHESTRATION_PLAN",
    "STATE_KEY_CURRENT_TURN_ID",
    "STATE_KEY_USER_ID",
    "STATE_KEY_SESSION_ID",
    "STATE_KEY_EXECUTION_PLAN",
    "STATE_KEY_PLANNER_METADATA",
    "STATE_KEY_PLANNER_ERROR",
    "STATE_KEY_VALIDATION_RESULT",
    "STATE_KEY_SEMANTIC_VALIDATION",
    "STATE_KEY_CLARIFICATION_RESPONSE",
    "STATE_KEY_CLARIFICATION_FIELD",
    "STATE_KEY_PLANNER_ITERATION",
    "STATE_KEY_NEEDS_REPLAN",
    "STATE_KEY_REPLAN_INSTRUCTIONS",
    "STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS",
    "STATE_KEY_APPROVAL_EVALUATION",
    "STATE_KEY_PLAN_APPROVED",
    "STATE_KEY_PLAN_REJECTION_REASON",
    "STATE_KEY_FOR_EACH_CANCELLED",
    "STATE_KEY_FOR_EACH_CANCELLATION_REASON",
    # Metadata keys
    "METADATA_KEY_RUN_ID",
    "METADATA_KEY_USER_ID",
    "METADATA_KEY_SESSION_ID",
    "METADATA_KEY_CONVERSATION_ID",
    "METADATA_KEY_INTENTION",
    "METADATA_KEY_CONFIDENCE",
    # Agent result keys
    "make_agent_result_key",
    "parse_agent_result_key",
    # Limits
    "MAX_AGENT_RESULTS_DEFAULT",
    "MAX_ROUTING_HISTORY_DEFAULT",
    # Rate limiting
    "RATE_LIMIT_SCOPE_USER",
    "RATE_LIMIT_SCOPE_GLOBAL",
    "RATE_LIMIT_DEFAULT_READ_CALLS",
    "RATE_LIMIT_DEFAULT_READ_WINDOW_SECONDS",
    "RATE_LIMIT_DEFAULT_WRITE_CALLS",
    "RATE_LIMIT_DEFAULT_WRITE_WINDOW_SECONDS",
    "RATE_LIMIT_DEFAULT_EXPENSIVE_CALLS",
    "RATE_LIMIT_DEFAULT_EXPENSIVE_WINDOW_SECONDS",
    # Orchestration modes
    "EXECUTION_MODE_SEQUENTIAL",
    "EXECUTION_MODE_PARALLEL",
    # Agent statuses
    "STATUS_SUCCESS",
    "STATUS_ERROR",
    "STATUS_CONNECTOR_DISABLED",
    "ALL_AGENT_STATUSES",
    # Graph edges
    "EDGE_END",
    "EDGE_START",
    # SSE events
    "SSE_EVENT_START",
    "SSE_EVENT_CHUNK",
    "SSE_EVENT_END",
    "SSE_EVENT_ERROR",
    "SSE_EVENT_HITL_REQUIRED",
    # HITL action types
    "ACTION_TYPE_SEARCH",
    "ACTION_TYPE_SEND",
    "ACTION_TYPE_DELETE",
    "ACTION_TYPE_CREATE",
    "ACTION_TYPE_UPDATE",
    "ACTION_TYPE_LIST",
    "ACTION_TYPE_GET",
    "ACTION_TYPE_FORWARD",
    "ACTION_TYPE_REPLY",
    "ACTION_TYPE_GENERIC",
    "ACTION_TYPE_PLAN_APPROVAL",
    "ACTION_TYPE_DRAFT_CRITIQUE",
    "ACTION_TYPE_FOR_EACH_CONFIRMATION",
    # HITL decisions
    "HITL_DECISION_APPROVE",
    "HITL_DECISION_REJECT",
    "HITL_DECISION_EDIT",
    "HITL_DECISION_AMBIGUOUS",
    "HITL_DECISION_NEW_REQUEST",
    # Registry item types
    "REGISTRY_TYPE_CONTACT",
    "REGISTRY_TYPE_EMAIL",
    "REGISTRY_TYPE_EVENT",
    "REGISTRY_TYPE_FILE",
    "REGISTRY_TYPE_TASK",
    "REGISTRY_TYPE_DRAFT",
    # Google People API fields
    "PEOPLE_API_FIELD_NAMES",
    "PEOPLE_API_FIELD_DISPLAY_NAME",
    "PEOPLE_API_FIELD_EMAIL_ADDRESSES",
    "PEOPLE_API_FIELD_VALUE",
    "DEFAULT_CONTACT_NAME",
    # Context resolution
    "STATE_KEY_LAST_ACTION_TURN_ID",
    "STATE_KEY_LAST_LIST_TURN_ID",
    "STATE_KEY_TURN_TYPE",
    "STATE_KEY_RESOLVED_CONTEXT",
    "STATE_KEY_RESOLVED_REFERENCES",
    "STATE_KEY_DETECTED_INTENT",
    "TURN_TYPE_ACTION",
    "TURN_TYPE_REFERENCE",
    "TURN_TYPE_REFERENCE_PURE",
    "TURN_TYPE_REFERENCE_ACTION",
    "TURN_TYPE_CONVERSATIONAL",
    "CONTEXT_REFERENCE_CONFIDENCE_THRESHOLD",
    "get_context_reference_confidence_threshold",
    # Logging and preview limits
    "LOGGING_CONTENT_PREVIEW_CHARS",
    "LOGGING_SUMMARY_PREVIEW_CHARS",
    "RESPONSE_LIST_PREVIEW_ITEMS",
    "RESPONSE_MAX_ERRORS_DISPLAY",
    "PLANNER_ERROR_JSON_PREVIEW_CHARS",
    "PLANNER_CONTEXT_ITEMS_PREVIEW",
    "PLANNER_EMAIL_SUBJECT_PREVIEW_CHARS",
]
