"""
Response node.
Generates conversational response using higher-temperature LLM.

Data Registry LOT 5.4: Draft Execution Integration
    After draft_critique_node confirms a draft, response_node executes it
    before generating the response. The execution result is included in
    agent_results for synthesis.

Flow:
    draft_critique_node → state["draft_action_result"] = {action: "confirm", ...}
    → response_node → _execute_draft_if_confirmed()
    → execute_*_draft() (email, contact, event)
    → agent_results["draft_execution"] = {...}
    → Response synthesis includes execution result
"""

import asyncio
import time
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import (
    BRAVE_SEARCH_ENRICHMENT_TIMEOUT,
    DEFAULT_USER_DISPLAY_TIMEZONE,
    SCHEDULED_ACTIONS_SESSION_PREFIX,
)
from src.core.field_names import (
    FIELD_METADATA,
    FIELD_PLAN_ID,
    FIELD_RUN_ID,
    FIELD_SESSION_ID,
)
from src.core.i18n import _
from src.core.i18n_api_messages import (
    NO_EXTERNAL_AGENT_MESSAGES,
    APIMessages,
)
from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.constants import (
    LOGGING_SUMMARY_PREVIEW_CHARS,
    RESPONSE_MAX_ERRORS_DISPLAY,
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_MESSAGES,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_PLANNER_ERROR,
    STATE_KEY_RESOLVED_CONTEXT,
    STATE_KEY_RESOLVED_REFERENCES,
    STATE_KEY_SEMANTIC_VALIDATION,
    STATE_KEY_TURN_TYPE,
    TURN_TYPE_ACTION,
    TURN_TYPE_CONVERSATIONAL,
    TURN_TYPE_REFERENCE,
)
from src.domains.agents.context.store import get_tool_context_store

# V3 Display Architecture imports
from src.domains.agents.display.config import config_for_viewport

# ResponseFormatter removed - pure HTML mode only
from src.domains.agents.display.html_renderer import NestedData, get_html_renderer
from src.domains.agents.drafts.models import DraftAction

# Extracted modules (Phase 3 refactoring)
from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt
from src.domains.agents.formatters.resolved_context import (
    format_resolved_context_for_prompt as _format_resolved_context_for_prompt,
)
from src.domains.agents.formatters.resolved_context import (
    generate_html_for_resolved_context,
)
from src.domains.agents.formatters.text_summary import (
    generate_data_for_filtering,
)
from src.domains.agents.middleware.memory_injection import build_psychological_profile
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration.correlation_detector import detect_correlations
from src.domains.agents.prompts import (
    escape_braces,
    get_error_fallback_message,
    get_response_prompt,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.memory_extractor import extract_memories_background
from src.domains.agents.utils.message_filters import (
    filter_for_llm_context,
)
from src.domains.agents.utils.registry_filtering import (
    filter_registry_by_current_turn as _filter_registry_by_current_turn,
)
from src.domains.agents.utils.registry_filtering import (
    filter_registry_by_relevant_ids,
    parse_relevant_ids_from_response,
)
from src.domains.agents.utils.state_tracking import track_state_updates
from src.domains.interests.services import extract_interests_background
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics import graph_exceptions_total
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
)
from src.infrastructure.observability.token_efficiency import track_token_efficiency
from src.infrastructure.observability.tracing import trace_node

# LLM-Native Semantic Architecture: State key for tool results
STATE_KEY_TOOL_RESULTS = "tool_results"

# Data Registry LOT 5.4: State key for draft action result from draft_critique_node
STATE_KEY_DRAFT_ACTION_RESULT = "draft_action_result"

logger = get_logger(__name__)


# ============================================================================
# VIEWPORT DETECTION
# ============================================================================


def _extract_viewport_from_config(config: RunnableConfig) -> str:
    """
    Extract viewport from browser context in config.

    Browser context is passed via config.configurable["__browser_context"]
    from the orchestration service.

    Priority:
    1. viewport_width (pixels) -> uses env breakpoint via viewport_from_width()
    2. viewport (string) -> direct value
    3. default: "desktop"

    Breakpoint configured via:
    - V3_DISPLAY_VIEWPORT_MOBILE_MAX_WIDTH (default 430px)
    - <= 430px = mobile, > 430px = desktop

    Args:
        config: RunnableConfig with browser context

    Returns:
        Viewport string: "mobile" or "desktop" (default)
    """
    from src.domains.agents.display.config import viewport_from_width

    browser_context = (config.get("configurable") or {}).get("__browser_context")
    if not browser_context:
        return "desktop"

    # Priority 1: Use viewport_width if provided (env-driven breakpoints)
    viewport_width = None
    if hasattr(browser_context, "viewport_width"):
        viewport_width = browser_context.viewport_width
    elif isinstance(browser_context, dict):
        viewport_width = browser_context.get("viewport_width")

    if viewport_width is not None and isinstance(viewport_width, int) and viewport_width > 0:
        return viewport_from_width(viewport_width).value

    # Priority 2: Use viewport string if provided
    if hasattr(browser_context, "viewport"):
        viewport = browser_context.viewport
    elif isinstance(browser_context, dict):
        viewport = browser_context.get("viewport")
    else:
        viewport = None

    # Validate viewport value
    if viewport in ("mobile", "tablet", "desktop"):
        return viewport

    return "desktop"  # Default fallback


# ============================================================================
# SECURITY - PHOTO URL VALIDATION (XSS Prevention)
# ============================================================================

# Trusted domains for photo URLs (whitelist approach for security)
ALLOWED_PHOTO_DOMAINS: frozenset[str] = frozenset(
    {
        # Google services
        "lh3.googleusercontent.com",
        "lh4.googleusercontent.com",
        "lh5.googleusercontent.com",
        "lh6.googleusercontent.com",
        "maps.googleapis.com",
        "maps.gstatic.com",
        "places.googleapis.com",
        # Development
        "localhost",
        "127.0.0.1",
    }
)

# Internal API proxy path prefixes (relative URLs)
ALLOWED_PHOTO_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/connectors/google-places/photo/",
    "/api/v1/connectors/google-drive/thumbnail/",
    "/api/v1/connectors/",
)

# ============================================================================
# EMAIL LABELS MAPPING (Gmail → Human readable)
# ============================================================================


# Gmail system labels → Display names (translated via i18n)
def _get_gmail_label_mapping() -> dict[str, str]:
    """Get Gmail label mapping with translated names."""
    return {
        # Core folders
        "INBOX": _("Inbox"),
        "SENT": _("Sent"),
        "DRAFT": _("Drafts"),
        "TRASH": _("Trash"),
        "SPAM": _("Spam"),
        # Status labels
        "UNREAD": _("Unread"),
        "STARRED": _("Starred"),
        "IMPORTANT": _("Important"),
        # Category labels
        "CATEGORY_PERSONAL": _("Personal"),
        "CATEGORY_SOCIAL": _("Social"),
        "CATEGORY_PROMOTIONS": _("Promotions"),
        "CATEGORY_UPDATES": _("Updates"),
        "CATEGORY_FORUMS": _("Forums"),
        # Chat label
        "CHAT": _("Chat"),
    }


# Keep static reference for backwards compatibility (default language)
GMAIL_LABEL_MAPPING: dict[str, str] = _get_gmail_label_mapping()

# Labels to exclude from display (internal/redundant)
GMAIL_LABELS_HIDDEN: frozenset[str] = frozenset(
    {
        "UNREAD",  # Already shown via is_unread flag
        "CATEGORY_PERSONAL",  # Default category, not useful to display
    }
)


def _is_safe_photo_url(url: str | None) -> bool:
    """
    Validate photo URL against whitelist of trusted domains.

    Security measure preventing injection of images from malicious sources.
    Blocks javascript:, data:, and untrusted external domains.
    Allows Google domains and internal API proxy paths.

    Args:
        url: URL to validate (can be None)

    Returns:
        True if URL is from trusted source, False otherwise
    """
    if not url:
        return False

    # Internal proxy paths (relative URLs) - trusted
    if url.startswith(ALLOWED_PHOTO_PATH_PREFIXES):
        return True

    # Full URLs - validate scheme and domain
    try:
        parsed = urlparse(url)
        # Block dangerous schemes (javascript:, data:, vbscript:, etc.)
        if parsed.scheme not in ("http", "https", ""):
            return False
        # Empty scheme with path means relative URL (already handled above)
        if not parsed.scheme and not parsed.netloc:
            return url.startswith("/")  # Must start with / for relative paths
        # Check domain against whitelist
        return parsed.netloc in ALLOWED_PHOTO_DOMAINS
    except (ValueError, AttributeError):
        return False


# ============================================================================
# ANTI-HALLUCINATION - MESSAGE FILTERING FOR REJECTED PLANS
# ============================================================================

# Indicators that an AI message contains result data (should be filtered when plan rejected)
# i18n: All supported languages (fr, en, es, de, it, zh-CN)
_RESULT_INDICATORS_BY_LANG: dict[str, set[str]] = {
    "fr": {
        "trouvé",
        "voici",
        "résultat",
        "résultats",
        "contact",
        "événement",
        "email",
        "lieu",
        "fichier",
    },
    "en": {
        "found",
        "result",
        "results",
        "here is",
        "here are",
        "contact",
        "event",
        "email",
        "place",
        "file",
    },
    "es": {
        "encontrado",
        "aquí",
        "resultado",
        "resultados",
        "contacto",
        "evento",
        "correo",
        "lugar",
        "archivo",
    },
    "de": {
        "gefunden",
        "hier ist",
        "hier sind",
        "ergebnis",
        "ergebnisse",
        "kontakt",
        "termin",
        "e-mail",
        "ort",
        "datei",
    },
    "it": {
        "trovato",
        "ecco",
        "risultato",
        "risultati",
        "contatto",
        "evento",
        "email",
        "luogo",
        "file",
    },
    "zh-CN": {"找到", "结果", "这里是", "联系人", "事件", "邮件", "地点", "文件"},
}

# Build combined frozenset for all languages + JSON indicators
RESULT_CONTENT_INDICATORS: frozenset[str] = frozenset(
    indicator for indicators in _RESULT_INDICATORS_BY_LANG.values() for indicator in indicators
) | frozenset(
    {
        # JSON/data indicators (language-agnostic)
        "```json",
        "```",
        '"id":',
        '"name":',
    }
)


def _filter_messages_for_rejection_context(
    messages: list[BaseMessage],
    has_rejection: bool,
) -> list[BaseMessage]:
    """
    Filter messages to remove result-containing content when plan is rejected.

    Prevents LLM hallucination by removing historical results from context.
    Keeps user questions and conversational exchanges (HumanMessage).
    Filters AIMessage containing previous search results/data.

    Security 2025-12-19: Addresses P0.3 - LLM hallucination on plan rejection.
    Even with anti-hallucination directives, LLMs can use data from context.

    Args:
        messages: Conversation messages to filter
        has_rejection: Whether current plan was rejected by user

    Returns:
        Filtered messages safe for rejection context.
        If no rejection, returns original messages unchanged.
    """
    if not has_rejection:
        return messages

    def _contains_result_data(msg: BaseMessage) -> bool:
        """Check if message content contains result/data patterns."""
        content = getattr(msg, "content", "")
        if not isinstance(content, str):
            return False

        content_lower = content.lower()
        return any(indicator in content_lower for indicator in RESULT_CONTENT_INDICATORS)

    # Keep HumanMessages (user questions/instructions)
    # Filter AIMessages that contain result data
    filtered: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            # Always keep user messages
            filtered.append(msg)
        elif isinstance(msg, AIMessage):
            # Only keep AI messages that don't contain result data
            if not _contains_result_data(msg):
                filtered.append(msg)
            # else: skip AI messages with results (prevents hallucination)
        else:
            # Keep other message types (rare edge case)
            filtered.append(msg)

    return filtered


# ============================================================================
# HELPER FUNCTIONS - STATE TRACKING
# ============================================================================


# ============================================================================
# HELPER FUNCTIONS - DRAFT EXECUTION (LOT 5.4)
# ============================================================================


async def _execute_draft_if_confirmed(
    state: MessagesState,
    config: RunnableConfig,
    run_id: str,
) -> dict[str, Any] | None:
    """
    Execute draft if user confirmed via HITL.

    Data Registry LOT 5.4: After draft_critique_node confirms a draft, this function
    delegates to draft_executor service for execution.

    Args:
        state: Current graph state with draft_action_result
        config: Runnable config with __deps (ToolDependencies) and metadata
        run_id: Run ID for logging

    Returns:
        Agent result dict for draft execution (or None if no draft to execute)

    Note:
        - Uses lazy imports to avoid circular dependencies
        - Graceful degradation: execution failure doesn't crash response_node
        - Uses central draft_executor service with registry pattern
    """
    draft_action_result = state.get(STATE_KEY_DRAFT_ACTION_RESULT)

    if not draft_action_result:
        return None

    # Extract user_language from state for localized messages
    user_language = state.get("user_language", settings.default_language)

    try:
        # Lazy import to avoid circular dependencies
        from src.domains.agents.services.draft_executor import execute_draft_if_confirmed

        # Delegate to central executor service
        # Handles confirm/edit/cancel routing and metrics
        result = await execute_draft_if_confirmed(
            draft_action_result, config, run_id, user_language
        )

        if result:
            logger.info(
                "draft_execution_completed",
                run_id=run_id,
                draft_id=result.draft_id,
                success=result.success,
                action=result.action,
            )
            return result.to_agent_result()

        return None

    except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
        logger.error(
            "draft_execution_failed",
            run_id=run_id,
            draft_id=draft_action_result.get("draft_id"),
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        # Return error result for response synthesis (graceful degradation)
        return {
            "status": "error",
            "message": _("Error during execution: {error}").format(error=str(e)),
            "draft_id": draft_action_result.get("draft_id"),
            "draft_type": draft_action_result.get("draft_type"),
            "action": DraftAction.CONFIRM.value,
        }


# Field rendering config for post-HITL result display: (draft_key, emoji, label_key, is_datetime)
# Technical/internal fields (calendar_id, message_id, event_id, etc.) are excluded
_DRAFT_RESULT_FIELD_CONFIG: dict[str, list[tuple[str, str, str, bool]]] = {
    "event": [
        ("summary", "📅", "event", False),
        ("start_datetime", "🕐", "start", True),
        ("end_datetime", "🏁", "end", True),
        ("location", "📍", "location", False),
        ("attendees", "👥", "attendees", False),
        ("description", "📝", "body", False),
    ],
    "email": [
        ("to", "📧", "to", False),
        ("cc", "📋", "cc", False),
        ("subject", "📝", "subject", False),
        ("body", "💬", "body", False),
    ],
    "email_reply": [
        ("to", "📧", "to", False),
        ("subject", "📝", "subject", False),
        ("body", "💬", "body", False),
        ("original_from", "↩️", "from", False),
    ],
    "email_forward": [
        ("to", "📧", "to", False),
        ("cc", "📋", "cc", False),
        ("subject", "📝", "subject", False),
        ("body", "💬", "body", False),
    ],
    "contact": [
        ("name", "👤", "contact", False),
        ("email", "📧", "email", False),
        ("phone", "📱", "phone", False),
        ("organization", "🏢", "organization", False),
        ("address", "📍", "location", False),
        ("notes", "📝", "body", False),
    ],
    "task": [
        ("title", "✅", "task", False),
        ("due", "📅", "due", True),
        ("notes", "📝", "body", False),
    ],
}


def _format_draft_execution_result(result: dict[str, Any] | None) -> str:
    """
    Format draft execution result for LLM context.

    Produces a rich, structured summary with domain-specific emojis
    and key details extracted from the execution data.

    Args:
        result: Draft execution result dict with:
            - status: "success" | "cancelled" | "error"
            - message: Localized message
            - draft_type: Type of draft (contact, event, email, etc.)
            - data: Result data dict (may contain html_link, summary, etc.)

    Returns:
        Formatted markdown string for agent_results_summary
    """
    if not result:
        return ""

    from src.core.i18n_hitl import DRAFT_TYPE_EMOJIS

    status = result.get("status", "unknown")
    message = result.get("message", "")
    draft_type = result.get("draft_type", "action")
    data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}

    # Domain-specific emoji (fallback to generic status emoji)
    domain_emoji = DRAFT_TYPE_EMOJIS.get(draft_type, "")

    # Extract contextual details from execution data
    html_link = data.get("html_link")
    details: list[str] = []

    if status == "success":
        # Use draft_content for comprehensive attribute display
        draft = data.get("_draft_content", {}) if isinstance(data, dict) else {}

        # Get preview labels for user's language
        from src.core.i18n_drafts import get_draft_preview_labels
        from src.core.time_utils import format_datetime_for_display

        user_lang = draft.get("user_language") or "fr"
        user_tz = draft.get("user_timezone") or "Europe/Paris"
        labels = get_draft_preview_labels(user_lang)

        # Find matching field config (try exact match, then base domain)
        fields = _DRAFT_RESULT_FIELD_CONFIG.get(draft_type) or _DRAFT_RESULT_FIELD_CONFIG.get(
            draft_type.split("_")[0], []
        )

        for draft_key, emoji, label_key, is_dt in fields:
            value = draft.get(draft_key) or data.get(draft_key)
            if value and str(value).strip():
                label = labels.get(label_key, draft_key)
                str_value = str(value)
                # Format datetime fields to human-readable
                if is_dt and isinstance(value, str) and "T" in value:
                    try:
                        str_value = format_datetime_for_display(
                            value, user_tz, user_lang, include_time=True
                        )
                    except (ValueError, TypeError):
                        pass  # Keep raw ISO if formatting fails
                # Truncate long body content
                if draft_key in ("body", "description", "notes") and len(str_value) > 200:
                    str_value = str_value[:200] + "…"
                details.append(f"{emoji} **{label}** : {str_value}")

        if html_link:
            details.append(f"🔗 [{_('Link', user_lang)}]({html_link})")

        # Assemble
        header = f"\n\n{domain_emoji} ✅ {message}"
        if details:
            detail_block = "\n".join(details)
            return f"{header}\n{detail_block}"
        return header

    elif status == "cancelled":
        return f"\n\n{domain_emoji} 🚫 {message}"

    elif status == "error":
        return f"\n\n{domain_emoji} ❌ {message}"

    return ""


# ============================================================================
# REGISTRY FILTERING
# ============================================================================
# NOTE: Registry filtering functions extracted to:
# - src.domains.agents.utils.registry_filtering
# Imports at top of file provide: _build_registry_payload_index, _filter_registry_by_current_turn,
# filter_registry_by_relevant_ids, parse_relevant_ids_from_response


# ============================================================================
# PLAN REJECTION FORMATTING
# ============================================================================


def _format_rejection_details(rejection_reason: str) -> str:
    """
    Format plan rejection with EXPLICIT anti-hallucination directives.

    CRITICAL: Uses 🚫 prohibition signal and direct LLM instructions to prevent
    hallucination of fake results after user rejection.

    The formatted message includes:
    - Clear prohibition signal (🚫 not ✅)
    - Explicit "NO DATA AVAILABLE" statement
    - Direct instruction to LLM: "Do NOT invent any data"
    - Invalidation of conversation history context

    Args:
        rejection_reason: Reason for plan rejection from approval_gate_node

    Returns:
        Formatted rejection notice with anti-hallucination safeguards

    Example:
        >>> details = _format_rejection_details("User rejected plan")
        >>> # Returns formatted text starting with "🚫 PLAN REJECTED..."
    """
    # Format reason text (use provided reason or default)
    reason_text = (
        rejection_reason
        if rejection_reason != "User rejected plan"
        else "L'utilisateur a choisi de ne pas exécuter ce plan"
    )

    # CRITICAL: Use 🚫 (prohibition) not ✅ (success)
    # Include explicit anti-hallucination directives for LLM
    return (
        "🚫 PLAN REFUSÉ PAR L'UTILISATEUR (AUCUNE DONNÉE DISPONIBLE)\n\n"
        "ATTENTION: N'invente AUCUNE donnée. Le plan a été explicitement rejeté.\n"
        "AUCUNE opération n'a été exécutée. AUCUN résultat n'existe.\n\n"
        f"**Raison du refus:** {reason_text}\n"
        "**Statut:** Aucune action effectuée\n"
        "**Réponse attendue:** Accuse réception du refus et propose alternatives\n\n"
        "RÈGLE ABSOLUE: Ne mentionne AUCUN résultat de recherche, contact, ou donnée métier.\n"
        "Le contexte conversationnel précédent est CADUC (annulé par refus)."
    )


# ============================================================================
# V3 DISPLAY - Helper Functions
# ============================================================================


def _extract_payloads_from_registry(
    data_registry: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """
    Extract payload data from registry items, grouped by domain.

    Converts registry structure {id: {type, payload, meta}} to domain-grouped
    payloads that ResponseFormatter expects.

    Args:
        data_registry: Registry dict with items (id → RegistryItem)

    Returns:
        Dict mapping result keys (pluriel) to lists of payload dicts
    """
    from src.domains.agents.utils.type_domain_mapping import get_result_key_from_type

    domain_payloads: dict[str, list[dict[str, Any]]] = {}

    for _item_id, item in data_registry.items():
        # Handle both dict and Pydantic RegistryItem objects
        if hasattr(item, "type"):
            item_type = item.type.value if hasattr(item.type, "value") else str(item.type)
            payload = item.payload if hasattr(item, "payload") else {}
        else:
            item_type = item.get("type", "")
            payload = item.get("payload", {})

        # Skip DRAFT items (handled separately by HITL flow)
        if item_type == "DRAFT":
            continue

        # Get result key (pluriel) for HtmlRenderer compatibility
        domain = get_result_key_from_type(item_type)
        if not domain:
            domain = "other"

        # Add payload to domain group
        if domain not in domain_payloads:
            domain_payloads[domain] = []

        # Ensure payload is a dict
        if isinstance(payload, dict):
            domain_payloads[domain].append(payload)

    return domain_payloads


def _detect_primary_domain_from_registry(
    data_registry: dict[str, Any] | None,
) -> str:
    """
    Detect the primary (most common) domain in the registry.

    Used for v3 display to select appropriate formatting template.

    Args:
        data_registry: Registry dict with items (id → RegistryItem)

    Returns:
        Primary domain name (e.g., "contacts", "emails", "calendar")
    """
    if not data_registry:
        return "other"

    domain_payloads = _extract_payloads_from_registry(data_registry)

    if not domain_payloads:
        return "other"

    # Find domain with most items
    primary_domain = max(domain_payloads.keys(), key=lambda d: len(domain_payloads[d]))
    return primary_domain


def _detect_result_domains_from_registry(
    data_registry: dict[str, Any] | None,
) -> set[str]:
    """
    Detect which result keys are present in data registry.

    Used for metrics tracking and logging.

    Args:
        data_registry: Registry dict with items (id → RegistryItem)

    Returns:
        Set of result keys found (e.g., {"contacts"}, {"emails"}, {"contacts", "emails"})
    """
    from src.domains.agents.utils.type_domain_mapping import get_result_key_from_type

    if not data_registry:
        return set()

    domains = set()
    for item in data_registry.values():
        # Handle both dict and Pydantic RegistryItem objects
        if hasattr(item, "type"):
            item_type = item.type.value if hasattr(item.type, "value") else str(item.type)
        else:
            item_type = item.get("type", "")

        # Use centralized type-to-result_key mapping
        domain = get_result_key_from_type(item_type)
        if domain:
            domains.add(domain)
        else:
            domains.add("other")

    return domains


# ============================================================================
# RESOLVED CONTEXT & TEXT SUMMARY FORMATTING
# ============================================================================
# NOTE: These functions extracted to:
# - src.domains.agents.formatters.resolved_context
# - src.domains.agents.formatters.text_summary
# Imports at top of file provide: _format_resolved_context_for_prompt,
# _detect_domain_from_item, generate_html_for_resolved_context,
# _generate_text_summary_for_items, generate_text_summary_for_llm, generate_data_for_filtering


# NOTE: _format_item_for_filtering was removed - replaced by generic payload_to_text()
# from src.domains.agents.display.llm_serializer in generate_data_for_filtering()
# NOTE: parse_relevant_ids_from_response and filter_registry_by_relevant_ids
# are imported from src.domains.agents.utils.registry_filtering


def generate_html_for_registry(
    data_registry: dict[str, Any] | None,
    user_viewport: str = "desktop",
    user_language: str = settings.default_language,
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
) -> str:
    """
    Generate HTML for registry data using HtmlRenderer.

    Called AFTER LLM generation to inject structured HTML into the response.

    Supports correlated display: Items linked via FOR_EACH (e.g., Event + Route pairs)
    are rendered together in clusters instead of grouped by domain.

    Args:
        data_registry: Registry dict with items
        user_viewport: Device viewport (mobile/tablet/desktop)
        user_language: Language code
        user_timezone: User's IANA timezone for datetime formatting

    Returns:
        HTML string ready for injection into response
    """
    if not data_registry:
        return ""

    # Get display config
    config = config_for_viewport(user_viewport)
    config.language = user_language
    config.timezone = user_timezone

    html_renderer = get_html_renderer()

    # Try correlated display first (for FOR_EACH patterns like Event + Route)
    clusters, uncorrelated = detect_correlations(data_registry)

    if clusters:
        # Has correlated items - use render_correlated
        return html_renderer.render_correlated(clusters, uncorrelated, config)

    # Fallback: Standard domain grouping
    domain_payloads = _extract_payloads_from_registry(data_registry)

    if not domain_payloads:
        return ""

    # Check if multi-domain
    if len(domain_payloads) > 1:
        # Multi-domain: use render_multi
        domains_data = {
            domain: {"items": items} for domain, items in domain_payloads.items() if items
        }
        return html_renderer.render_multi(domains_data, config)
    else:
        # Single domain
        primary_domain = _detect_primary_domain_from_registry(data_registry)
        items = domain_payloads.get(primary_domain, [])
        if items:
            return html_renderer.render(primary_domain, {"items": items}, config)

    return ""


def format_nested_results_as_html(
    parent_domain: str,
    parent_items: list[dict[str, Any]],
    children_by_parent: dict[str, list[tuple[str, list[dict[str, Any]]]]],
    config: Any,
    relation: str = "",
) -> str:
    """
    Format hierarchical/nested results as HTML.

    Useful for complex queries like:
    - "Liste les contacts X et Y avec leurs 3 derniers emails"
    - "Montre les restaurants près de chaque lieu visité"

    Args:
        parent_domain: Domain of parent items (e.g., "contacts")
        parent_items: List of parent item dicts
        children_by_parent: Dict mapping parent_id -> list of (child_domain, child_items)
        config: DisplayConfig instance
        relation: Relation type (e.g., "emails_from", "places_nearby")

    Returns:
        HTML string with nested structure

    Example:
        >>> html = format_nested_results_as_html(
        ...     parent_domain="contacts",
        ...     parent_items=[{"id": "c1", "name": "Jean"}],
        ...     children_by_parent={"c1": [("emails", [{"subject": "Hello"}])]},
        ...     config=config_for_viewport("desktop"),
        ...     relation="emails_from",
        ... )
    """
    html_renderer = get_html_renderer()
    nested_items = []

    for parent_item in parent_items:
        parent_id = parent_item.get("id") or parent_item.get("resourceName", "")

        # Build children NestedData
        children = []
        if parent_id and parent_id in children_by_parent:
            for child_domain, child_items in children_by_parent[parent_id]:
                children.append(
                    NestedData(
                        domain=child_domain,
                        items=child_items,
                        relation=relation,
                    )
                )

        # Create nested data structure
        nested = NestedData(
            domain=parent_domain,
            items=[parent_item],
            children=children,
            relation=relation,
        )
        nested_items.append(nested)

    return html_renderer.render_nested_list(nested_items, config)


# ============================================================================
# AGENT RESULTS FORMATTING
# ============================================================================
# NOTE: Agent results formatting functions extracted to:
# - src.domains.agents.formatters.agent_results
# Import at top of file provides: format_agent_results_for_prompt


@trace_node("response")
@track_metrics(
    node_name="response",
    duration_metric=agent_node_duration_seconds,
    counter_metric=agent_node_executions_total,
)
async def response_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """
    Response node: Generates conversational response using higher-temperature LLM.
    Synthesizes agent results and streams tokens for real-time UX.

    Args:
        state: Current LangGraph state with messages and agent_results.
        config: Runnable config with metadata (run_id, etc.).

    Returns:
        Updated state with AI response message.

    Raises:
        Exception: If response generation fails, returns error fallback message.

    Note:
        - Streaming is handled by service layer via astream_events().
        - This node formats agent results for LLM context.
        - Basic metrics (duration, success/error counters) are tracked automatically
          by @track_metrics decorator. Only business logic error handling remains here.
    """
    run_id = config.get(FIELD_METADATA, {}).get(FIELD_RUN_ID, "unknown")

    logger.info(
        "response_node_started",
        run_id=run_id,
        message_count=len(state[STATE_KEY_MESSAGES]),
        agent_results_count=len(state.get(STATE_KEY_AGENT_RESULTS, {})),
    )

    try:
        # ✅ CRITICAL FIX: Clean previous turn's content replacement signal
        # Prevents persisted state from triggering replacement in conversational turns
        # Root cause: content_final_replacement persists in PostgreSQL checkpointer between turns
        # See: ROOT_CAUSE_STREAMING_REPLACEMENT_BUG.md
        if "content_final_replacement" in state:
            logger.debug(
                "cleaning_previous_content_replacement",
                run_id=run_id,
                current_turn_id=state.get(STATE_KEY_CURRENT_TURN_ID),
            )

        # Get user timezone and language from state (with fallbacks to i18n defaults)
        user_timezone = state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE)
        user_language = state.get("user_language", settings.default_language)
        user_viewport = _extract_viewport_from_config(config)

        logger.debug(
            "response_node_viewport_detected",
            run_id=run_id,
            viewport=user_viewport,
        )

        # === VISION LLM SWITCH (evolution F4 — File Attachments) ===
        # Detect if current turn has image attachments → use vision_analysis LLM
        current_turn_attachments = state.get("metadata", {}).get("current_turn_attachments")
        has_vision_content = False
        if current_turn_attachments:
            from src.domains.attachments.models import AttachmentContentType

            has_vision_content = any(
                a["content_type"] == AttachmentContentType.IMAGE for a in current_turn_attachments
            )
        llm = get_llm("vision_analysis") if has_vision_content else get_llm("response")

        # Dynamic Few-Shot: Detect domains and operations for targeted prompt loading
        # This reduces prompt size by ~80% by only loading relevant fewshot examples
        agent_results_raw = state.get(STATE_KEY_AGENT_RESULTS, {})

        # LLM-Native Semantic Architecture: Fallback to tool_results if agent_results is empty
        # The semantic architecture uses tool_executor_node which populates STATE_KEY_TOOL_RESULTS
        # while legacy architecture uses task_orchestrator_node which populates STATE_KEY_AGENT_RESULTS
        if not agent_results_raw:
            tool_results = state.get(STATE_KEY_TOOL_RESULTS, [])
            if tool_results:
                # Convert tool_results list to agent_results format for compatibility
                # tool_results is a list of dicts, we need to key by turn_id
                current_turn = state.get(STATE_KEY_CURRENT_TURN_ID, 0)
                agent_results_raw = {
                    f"{current_turn}:semantic_tools": {
                        "data": tool_results,
                        "registry_updates": state.get("registry", {}),
                    }
                }
                logger.info(
                    "response_node_using_tool_results_fallback",
                    run_id=run_id,
                    tool_count=len(tool_results),
                )

        full_registry = state.get("registry", {})
        current_turn_id = state.get(STATE_KEY_CURRENT_TURN_ID)
        resolved_context = state.get(STATE_KEY_RESOLVED_CONTEXT)

        # BugFix 2025-12-19: Filter registry by current turn BEFORE domain detection
        # Root cause: _detect_domain_operations was iterating ALL registry items from ALL turns
        # causing multi-domain fewshot loading (e.g., files + places) when only one domain was queried
        # Example: "detail du premier" (files) was loading places fewshots from previous turn
        # BugFix 2025-12-19 #2: For REFERENCE turns (e.g., "detail du premier" after email search),
        # pass resolved_context to filter by resolved items when no registry_updates exist
        # Security 2025-12-19: turn_type for strict REFERENCE filtering (prevents data leak)
        turn_type = state.get(STATE_KEY_TURN_TYPE)
        current_turn_registry = _filter_registry_by_current_turn(
            agent_results_raw, current_turn_id, full_registry, resolved_context, turn_type
        )

        # INTELLIA v10: Derive override_action for JSON formatting consistency
        # NOTE: "detail" and "list" intents removed (2026-01 simplification)
        # All retrieval now uses "search" with full content always returned
        detected_intent = state.get("detected_intent")
        override_action: str | None = None
        if detected_intent == "search":
            override_action = "search"
        # For action/full/None, let the formatting functions use tool_name analysis

        # Get personality instruction from state (populated during graph initialization)
        personality_instruction = state.get("personality_instruction")

        # Format conversation history for prompt injection
        # Architecture (2025-12-07): Uses explicit placeholder {conversation_history} in prompt
        from src.domains.agents.utils.conversation_context import format_conversation_history
        from src.domains.agents.utils.message_windowing import get_response_windowed_messages

        windowed_for_history = get_response_windowed_messages(state[STATE_KEY_MESSAGES])
        # Use filter_for_llm_context: keeps HumanMessage + ToolMessage (JSON) + simple AIMessage
        # Excludes AIMessage with HTML (lia-card) to prevent LLM reformulating as Markdown
        llm_context_for_history = filter_for_llm_context(windowed_for_history)

        # =====================================================================
        # INTELLIGENT FILTERING: Extract user query for semantic filtering
        # =====================================================================
        # Extract last user message for filtering context (also used by memory injection)
        last_user_message = ""
        for msg in reversed(state[STATE_KEY_MESSAGES]):
            if isinstance(msg, HumanMessage) and msg.content:
                last_user_message = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                break

        # =====================================================================
        # KNOWLEDGE ENRICHMENT: Launch Brave Search API (parallel with memory)
        # =====================================================================
        # Get query_intelligence for keyword extraction
        query_intelligence = state.get("query_intelligence")

        # Get ToolDependencies from config (injected at graph execution start)
        tool_deps = config.get("configurable", {}).get("__deps")

        # Launch knowledge enrichment task in parallel (non-blocking)
        # Track enrichment result for debug panel (even if enrichment wasn't executed)
        enrichment_task = None
        knowledge_enrichment_result: dict[str, Any] | None = None

        if not settings.knowledge_enrichment_enabled:
            knowledge_enrichment_result = {"skip_reason": "feature_disabled"}
        elif not query_intelligence:
            knowledge_enrichment_result = {"skip_reason": "no_query_intelligence"}
        elif not tool_deps:
            knowledge_enrichment_result = {"skip_reason": "no_tool_deps"}
        else:
            from src.domains.agents.services import get_knowledge_enrichment_service

            # Parse user_id from config (langgraph_user_id is the standard key)
            user_id_str = config.get("configurable", {}).get("langgraph_user_id")
            user_id = UUID(user_id_str) if user_id_str else None

            if not user_id:
                knowledge_enrichment_result = {"skip_reason": "no_user_id"}
            else:
                service = get_knowledge_enrichment_service()
                # Extract fields from query_intelligence dict (serialized by router_node)
                encyclopedia_keywords = query_intelligence.get("encyclopedia_keywords") or []
                is_news_query = query_intelligence.get("is_news_query", False)
                qi_language = query_intelligence.get("user_language", user_language)
                primary_domain = query_intelligence.get("primary_domain")

                # Skip Brave enrichment for domains that already have their own
                # content source (web_search includes Brave, web_fetch is self-contained)
                # and MCP domains (data comes from MCP tools, not web search)
                from src.domains.agents.utils.type_domain_mapping import (
                    SKIP_ENRICHMENT_DOMAINS,
                )

                if primary_domain in SKIP_ENRICHMENT_DOMAINS:
                    knowledge_enrichment_result = {"skip_reason": f"{primary_domain}_domain"}
                elif primary_domain and primary_domain.startswith("mcp"):
                    knowledge_enrichment_result = {"skip_reason": "mcp_domain"}
                elif not encyclopedia_keywords:
                    knowledge_enrichment_result = {"skip_reason": "no_keywords"}
                else:
                    enrichment_task = asyncio.create_task(
                        service.enrich(
                            keywords=encyclopedia_keywords,
                            is_news_query=is_news_query,
                            user_id=user_id,
                            language=qi_language,
                            tool_deps=tool_deps,
                        )
                    )
                    logger.debug(
                        "knowledge_enrichment_started",
                        run_id=run_id,
                        keywords=encyclopedia_keywords[:3],
                        is_news_query=is_news_query,
                    )

        # HITL FIX 2026-01-22: Use original_query from QueryIntelligence for prompt
        # For HITL resumptions (e.g., user says "ok"), last_user_message is just "ok"
        # but original_query contains the actual intent ("Create a reminder for...")
        # This prevents the LLM from being confused by the short confirmation message.
        user_query_for_prompt = get_qi_attr(state, "original_query", default=None)
        if not user_query_for_prompt:
            user_query_for_prompt = last_user_message

        # Exclude the user_query_for_prompt from history - it's passed separately via {user_query}
        # This prevents the current query from appearing twice in the prompt.
        # HITL FIX 2026-01-22: In HITL resumption, last HumanMessage is "ok" but original_query
        # (from QueryIntelligence) is the real intent. We exclude the ORIGINAL query from history
        # to avoid duplication with {user_query}. HITL confirmations ("ok", etc.) are left in
        # history - they're short and the LLM understands conversational context.
        query_to_exclude = user_query_for_prompt.strip().lower() if user_query_for_prompt else ""
        history_messages = [
            msg
            for msg in llm_context_for_history
            if not (
                isinstance(msg, HumanMessage)
                and isinstance(msg.content, str)
                and msg.content.strip().lower() == query_to_exclude
            )
        ]
        conversation_history = format_conversation_history(history_messages)

        # Generate enriched data for intelligent filtering
        # This includes item IDs and filterable fields (addresses, locations, etc.)
        data_for_filtering = ""
        if current_turn_registry:
            try:
                data_for_filtering = generate_data_for_filtering(
                    current_turn_registry, user_language
                )
                logger.debug(
                    "intelligent_filtering_data_generated",
                    run_id=run_id,
                    item_count=len(current_turn_registry),
                    data_preview=data_for_filtering[:200] if data_for_filtering else "",
                )
            except (ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
                # Log error but continue without filtering data
                logger.warning(
                    "intelligent_filtering_data_generation_error",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                data_for_filtering = "(erreur de génération des données)"

        # Long-term memory injection: Build psychological profile from semantic memory
        # Phase 4 LangMem: Inject user context and emotional nuances into response prompt
        # NOTE: Memory features are always enabled; check only user preference
        psychological_profile: str | None = None
        memory_injection_debug: dict[str, Any] | None = None
        user_memory_enabled = config.get("configurable", {}).get("user_memory_enabled", True)
        if user_memory_enabled:
            user_id = config.get("configurable", {}).get("langgraph_user_id")
            # LangGraph v1.0: Store is NOT accessible via config in nodes
            # Must use the global singleton - same pattern as planner_node.py
            store = await get_tool_context_store()

            # Use last_user_message already extracted above for intelligent filtering
            if user_id and store and last_user_message:
                try:
                    # Get thread_id for embedding token tracking
                    thread_id_for_memory = config.get("configurable", {}).get("thread_id")
                    profile_result, emotional_state, memory_debug_details = (
                        await build_psychological_profile(
                            store=store,
                            user_id=user_id,
                            query=last_user_message,
                            limit=settings.memory_max_results,
                            min_score=settings.memory_min_search_score,
                            session_id=thread_id_for_memory,
                            conversation_id=thread_id_for_memory,
                            include_debug=True,
                        )
                    )
                    psychological_profile = profile_result
                    # Store debug details for debug panel (memory tuning)
                    memory_injection_debug = {
                        "memory_count": len(memory_debug_details) if memory_debug_details else 0,
                        "emotional_state": emotional_state.value,
                        "settings": {
                            "max_results": settings.memory_max_results,
                            "min_score": settings.memory_min_search_score,
                            "hybrid_enabled": getattr(settings, "memory_hybrid_enabled", False),
                        },
                        "memories": memory_debug_details or [],
                    }
                    logger.info(
                        "memory_injection_completed",
                        run_id=run_id,
                        user_id=user_id,
                        has_profile=profile_result is not None,
                        emotional_state=emotional_state.value if profile_result else None,
                    )
                except (ValueError, KeyError, RuntimeError, AttributeError, OSError) as e:
                    logger.warning(
                        "memory_injection_failed",
                        run_id=run_id,
                        user_id=user_id,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

        # =====================================================================
        # RAG SPACES CONTEXT INJECTION
        # =====================================================================
        rag_context: str | None = None
        rag_injection_debug: dict[str, Any] | None = None
        if getattr(settings, "rag_spaces_enabled", False):
            try:
                from uuid import UUID as _UUID

                from src.domains.rag_spaces.retrieval import retrieve_rag_context
                from src.infrastructure.database.session import get_db_context

                user_id_for_rag = config.get("configurable", {}).get("langgraph_user_id")
                thread_id_for_rag = config.get("configurable", {}).get("thread_id")
                if user_id_for_rag and last_user_message:
                    async with get_db_context() as rag_db:
                        rag_result = await retrieve_rag_context(
                            user_id=_UUID(user_id_for_rag),
                            query=last_user_message,
                            db=rag_db,
                            session_id=thread_id_for_rag,
                            conversation_id=thread_id_for_rag,
                            run_id=run_id,
                        )
                    if rag_result and rag_result.chunks:
                        rag_context = rag_result.to_prompt_context()
                        rag_injection_debug = {
                            "spaces_searched": rag_result.spaces_searched,
                            "chunks_found": rag_result.total_results,
                            "chunks_injected": len(rag_result.chunks),
                            "chunks": [
                                {
                                    "space": c.space_name,
                                    "file": c.original_filename,
                                    "score": c.score,
                                }
                                for c in rag_result.chunks
                            ],
                        }
                        logger.info(
                            "rag_injection_completed",
                            run_id=run_id,
                            user_id=user_id_for_rag,
                            chunks_injected=len(rag_result.chunks),
                            spaces_searched=rag_result.spaces_searched,
                        )
            except Exception as e:
                logger.warning(
                    "rag_injection_failed",
                    run_id=run_id,
                    error=str(e),
                )

        # =====================================================================
        # SYSTEM RAG CONTEXT (App FAQ) — Lazy loading based on is_app_help_query
        # =====================================================================
        # When is_app_help_query=True, we ALWAYS inject the app identity prompt
        # (describing LIA's capabilities). System RAG chunks are added on top if available.
        app_knowledge_context = ""
        is_app_help = get_qi_attr(state, "is_app_help_query", default=False)
        if is_app_help:
            # Mark as app help so get_response_prompt() loads app_identity_prompt
            app_knowledge_context = "APP_HELP_QUERY"

            # Optionally enrich with system RAG chunks (FAQ search results)
            if getattr(settings, "rag_spaces_system_enabled", False) and last_user_message:
                try:
                    from src.domains.rag_spaces.retrieval import (
                        retrieve_rag_context as _sys_retrieve,
                    )
                    from src.infrastructure.database.session import (
                        get_db_context as _sys_get_db,
                    )

                    async with _sys_get_db() as sys_db:
                        sys_result = await _sys_retrieve(
                            user_id=None,
                            query=last_user_message,
                            db=sys_db,
                            system_only=True,
                        )
                    if sys_result and sys_result.chunks:
                        app_knowledge_context = sys_result.to_prompt_context()
                        logger.info(
                            "system_rag_injection_completed",
                            run_id=run_id,
                            chunks_injected=len(sys_result.chunks),
                        )
                except Exception as e:
                    logger.warning(
                        "system_rag_injection_failed",
                        run_id=run_id,
                        error=str(e),
                    )

        # =====================================================================
        # AWAIT KNOWLEDGE ENRICHMENT (if task was launched)
        # =====================================================================
        knowledge_context = ""
        # Note: knowledge_enrichment_result is already initialized above with skip_reason if applicable

        if enrichment_task:
            try:
                context_obj = await asyncio.wait_for(
                    enrichment_task,
                    timeout=BRAVE_SEARCH_ENRICHMENT_TIMEOUT,
                )
                if context_obj:
                    knowledge_context = context_obj.to_prompt_context()
                    # Store result for debug panel (include actual results for debugging)
                    knowledge_enrichment_result = {
                        "endpoint": context_obj.endpoint,
                        "keyword_used": context_obj.keyword,
                        "results_count": len(context_obj.results),
                        "from_cache": context_obj.from_cache,
                        # Include actual results for debug panel inspection
                        "results": list(context_obj.results),
                        # Include the formatted context injected into prompt
                        "prompt_context": knowledge_context,
                    }
                    logger.info(
                        "knowledge_enrichment_injected",
                        run_id=run_id,
                        keyword=context_obj.keyword,
                        endpoint=context_obj.endpoint,
                        from_cache=context_obj.from_cache,
                        results_count=len(context_obj.results),
                    )
                else:
                    # Enrichment was attempted but returned None (connector not configured, etc.)
                    knowledge_enrichment_result = {
                        "skip_reason": "no_result",
                    }
            except TimeoutError:
                knowledge_enrichment_result = {
                    "error": "timeout",
                    "timeout_seconds": BRAVE_SEARCH_ENRICHMENT_TIMEOUT,
                }
                logger.warning(
                    "knowledge_enrichment_timeout",
                    run_id=run_id,
                    timeout=BRAVE_SEARCH_ENRICHMENT_TIMEOUT,
                )
            except Exception as e:
                knowledge_enrichment_result = {
                    "error": str(e),
                }
                logger.warning(
                    "knowledge_enrichment_await_error",
                    run_id=run_id,
                    error=str(e),
                )

        # Extract resolved references for natural response phrasing
        # Example: {"ma femme": "jean dupond"} enables "ta femme (jean dupond)" in response
        resolved_references_raw = state.get(STATE_KEY_RESOLVED_REFERENCES)
        resolved_references: dict[str, str] | None = None
        if resolved_references_raw and isinstance(resolved_references_raw, dict):
            # Extract mappings from resolved_references structure
            resolved_references = resolved_references_raw.get("mappings") or resolved_references_raw
            if resolved_references:
                logger.info(
                    "response_node_resolved_references",
                    run_id=run_id,
                    mappings=resolved_references,
                )

        # Extract enriched query from QueryIntelligence for context-aware filtering
        # Example: "I want the details" + history "where do the duponds live"
        #   → enriched_query: "get contact details for the dupond family"
        # This gives the Response LLM full context for intelligent filtering
        enriched_query = get_qi_attr(state, "english_enriched_query", default=None)
        if not enriched_query:
            enriched_query = get_qi_attr(state, "english_query", default=None)
        if enriched_query:
            logger.debug(
                "response_node_enriched_query",
                run_id=run_id,
                enriched_query_preview=enriched_query[:100] if enriched_query else "",
            )

        # Extract anticipated needs for proactive suggestions
        # Example: ["may want reminder", "may want to reschedule"]
        # LIA will use these to provide proactive suggestions in her response
        anticipated_needs = get_qi_attr(state, "anticipated_needs", default=None)
        if anticipated_needs:
            logger.debug(
                "response_node_anticipated_needs",
                run_id=run_id,
                anticipated_needs=anticipated_needs[:4] if anticipated_needs else [],
            )

        # Skills L2 injection — structured wrapping per agentskills.io standard
        skills_context = ""
        if getattr(settings, "skills_enabled", False):
            from src.core.context import active_skills_ctx
            from src.domains.skills.activation import activate_skill
            from src.domains.skills.cache import SkillsCache

            skill_sections: list[str] = []
            activated_names: set[str] = set()
            skill_user_id = config.get("configurable", {}).get("langgraph_user_id")
            active = active_skills_ctx.get()

            # 1. Planner-activated skill (from plan.metadata) → L2 structured wrapping
            execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
            if execution_plan and execution_plan.metadata:
                plan_skill_name = execution_plan.metadata.get("skill_name")
                if plan_skill_name and (active is None or plan_skill_name in active):
                    skill_content = activate_skill(plan_skill_name, user_id=skill_user_id)
                    if skill_content:
                        skill_sections.append(skill_content)
                        activated_names.add(plan_skill_name)

            # 2. Always-loaded skills (additive, deduplicated per standard)
            for s in SkillsCache.get_always_loaded(skill_user_id):
                if s["name"] not in activated_names and (active is None or s["name"] in active):
                    skill_content = activate_skill(s["name"], user_id=skill_user_id)
                    if skill_content:
                        skill_sections.append(skill_content)
                        activated_names.add(s["name"])

            # 3. Conversation-fallback: L1 catalogue only (per agentskills.io standard)
            #    For queries not routed through planner (intent=conversation), inject
            #    the L1 catalogue. The LLM calls activate_skill_tool if a skill matches.
            #    This is the standard model-driven approach — no L2 mass-loading.
            if not skill_sections:
                from src.domains.skills.injection import build_skills_catalog

                catalog = build_skills_catalog(skill_user_id or "", active_skills=active)
                if catalog:
                    skills_context = (
                        catalog + "\n\nIf a skill above matches the current request, "
                        "call activate_skill_tool with the skill name to load its full "
                        "instructions, then respond using those instructions."
                    )

            if skill_sections:
                skills_context = "\n\n".join(skill_sections)

        # ===================================================================
        # JOURNAL CONTEXT INJECTION (semantic relevance search)
        # ===================================================================
        journal_context = ""
        journal_injection_debug: dict | None = None
        user_journals_enabled = config.get("configurable", {}).get("user_journals_enabled", False)
        if settings.journals_enabled and user_journals_enabled:
            try:
                user_id_for_journal = config.get("configurable", {}).get("langgraph_user_id")
                if user_id_for_journal and last_user_message:
                    from src.domains.journals.context_builder import (
                        build_journal_context,
                    )
                    from src.infrastructure.database.session import get_db_context

                    thread_id_for_journal = config.get("configurable", {}).get("thread_id")
                    async with get_db_context() as journal_db:
                        journal_context_result, journal_debug = await build_journal_context(
                            user_id=user_id_for_journal,
                            query=last_user_message,
                            db=journal_db,
                            include_debug=True,
                            run_id=run_id,
                            session_id=thread_id_for_journal,
                        )
                        journal_context = journal_context_result or ""
                        journal_injection_debug = journal_debug
            except Exception as e:
                logger.warning(
                    "journal_context_injection_failed",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # Get timezone-aware prompt with personality, history, and memory injection
        # V3 Architecture: LLM generates conversational response only
        # Data formatting handled by HTML components, injected post-LLM via HtmlRenderer
        # Intelligent Filtering: Pass user_query and data_for_filtering for semantic filtering
        base_system_prompt = get_response_prompt(
            user_timezone=user_timezone,
            user_language=user_language,
            personality_instruction=personality_instruction,
            conversation_history=conversation_history,
            window_size=settings.response_message_window_size,
            psychological_profile=psychological_profile,
            knowledge_context=knowledge_context,  # Brave Search enrichment
            rag_context=rag_context or "",  # RAG Spaces user documents
            user_query=user_query_for_prompt,
            enriched_query=enriched_query,
            data_for_filtering=data_for_filtering,
            resolved_references=resolved_references,
            anticipated_needs=anticipated_needs,
            skills_context=skills_context,
            app_knowledge_context=app_knowledge_context,
            journal_context=journal_context,  # Personal journal context
        )

        logger.debug(
            "response_node_prompt_loaded",
            run_id=run_id,
            viewport=user_viewport,
            has_filtering_data=bool(data_for_filtering),
            user_query_for_prompt=user_query_for_prompt[:80] if user_query_for_prompt else "",
            last_user_message=last_user_message[:80] if last_user_message else "",
            used_original_query=user_query_for_prompt != last_user_message,
        )

        # === CONTEXT RESOLUTION: Determine which results to show ===
        turn_type = state.get(STATE_KEY_TURN_TYPE, TURN_TYPE_ACTION)
        # Note: resolved_context and current_turn_id already retrieved above (lines 2103-2104)

        # V3 HTML: Track resolved_context for HTML injection post-LLM
        # Used when REFERENCE turn uses resolved_context directly (no current_turn_registry)
        resolved_context_for_html: dict[str, Any] | None = None

        # Format agent results based on turn type
        if turn_type == TURN_TYPE_REFERENCE and resolved_context and resolved_context.get("items"):
            # Reference turn: Check if current turn has agent_results (e.g., from get_email_details)
            # If so, use them (they contain enriched data like body) instead of resolved_context items
            current_turn_agent_results = {
                k: v
                for k, v in state.get(STATE_KEY_AGENT_RESULTS, {}).items()
                if k.startswith(f"{current_turn_id}:")
            }

            if current_turn_agent_results:
                # Current turn has results - use them (they have body, full details, etc.)
                # INTELLIA v6: Pass registry for Markdown formatting
                # BugFix 2025-12-19: Use current_turn_registry (already filtered) instead of full registry
                agent_results_summary = format_agent_results_for_prompt(
                    state.get(STATE_KEY_AGENT_RESULTS, {}),
                    current_turn_id=current_turn_id,
                    data_registry=current_turn_registry if current_turn_registry else None,
                    user_timezone=user_timezone,
                    user_language=user_language,
                    override_action=override_action,
                    user_viewport=user_viewport,
                    use_text_summary=True,  # NOTE: V3 HTML rendering is always enabled
                )
                logger.info(
                    "response_node_using_current_turn_results_for_reference",
                    run_id=run_id,
                    source_turn_id=resolved_context.get("source_turn_id"),
                    current_turn_id=current_turn_id,
                    current_turn_results_count=len(current_turn_agent_results),
                    registry_mode=bool(current_turn_registry),
                )
            else:
                # No current turn results - use resolved context items
                # V3 HTML: Use text summary for LLM, HTML injected post-LLM
                agent_results_summary = _format_resolved_context_for_prompt(
                    resolved_context,
                    use_text_summary=True,  # NOTE: V3 HTML rendering is always enabled
                    user_viewport=user_viewport,
                    user_language=user_language,
                )
                # Store resolved_context for HTML injection post-LLM
                # (only when using HTML mode and no current_turn_registry)
                # NOTE: V3 HTML rendering is always enabled
                resolved_context_for_html = resolved_context
                logger.info(
                    "response_node_using_resolved_context",
                    run_id=run_id,
                    source_turn_id=resolved_context.get("source_turn_id"),
                    items_count=len(resolved_context.get("items", [])),
                    html_mode=True,  # NOTE: V3 HTML rendering is always enabled
                )
        elif turn_type == TURN_TYPE_CONVERSATIONAL:
            # Conversational turn: no agent results
            agent_results_summary = ""
        else:
            # Action turn: use current turn results (standard behavior)
            # INTELLIA v6: Pass registry for Markdown formatting
            # BugFix 2025-12-19: Use current_turn_registry (already filtered) instead of full registry
            agent_results_summary = format_agent_results_for_prompt(
                state.get(STATE_KEY_AGENT_RESULTS, {}),
                current_turn_id=current_turn_id,
                data_registry=current_turn_registry if current_turn_registry else None,
                user_timezone=user_timezone,
                user_language=user_language,
                override_action=override_action,
                user_viewport=user_viewport,
                use_text_summary=True,  # NOTE: V3 HTML rendering is always enabled
            )
            if current_turn_registry:
                logger.info(
                    "response_node_registry_mode_enabled",
                    run_id=run_id,
                    registry_items_count=len(current_turn_registry),
                )

        # =====================================================================
        # Data Registry LOT 5.4: Execute draft if user confirmed
        # =====================================================================
        # After draft_critique_node confirms a draft, execute it and include
        # the result in the response synthesis.
        draft_execution_result = await _execute_draft_if_confirmed(state, config, run_id)

        if draft_execution_result:
            # Format draft execution result for response synthesis
            draft_summary = _format_draft_execution_result(draft_execution_result)
            if draft_summary:
                # After HITL confirmation, REPLACE the entire agent_results_summary
                # with only the execution result. The user already saw intermediate results
                # (search results, draft preview) during the HITL critique streaming flow.
                # Keeping them would produce noise like "[search] N event(s): ..." above
                # the confirmation message.
                agent_results_summary = draft_summary.strip()

            logger.info(
                "draft_execution_result_added_to_summary",
                run_id=run_id,
                draft_id=draft_execution_result.get("draft_id"),
                status=draft_execution_result.get("status"),
                action=draft_execution_result.get("action"),
            )

        # PHASE 8: Handle plan rejection via HITL
        # Router node clears state fields each turn, so rejection_reason is always current-turn only.
        # Coherence validation: Ensure rejection_reason and plan_approved are not contradictory.
        plan_approved = state.get(STATE_KEY_PLAN_APPROVED)
        plan_rejection_reason = state.get(STATE_KEY_PLAN_REJECTION_REASON)

        # State coherence check: Discard stale rejection if plan was approved
        if plan_approved is True and plan_rejection_reason:
            logger.warning(
                "response_node_state_coherence_violation",
                run_id=run_id,
                action="Discarding stale rejection_reason",
            )
            plan_rejection_reason = None

        # If plan was rejected, format rejection as structured agent result
        if plan_rejection_reason:
            agent_results_summary = _format_rejection_details(plan_rejection_reason)
            logger.info("response_node_plan_rejection", run_id=run_id)

        # Check if planner encountered an error (Phase 5)
        planner_error = state.get(STATE_KEY_PLANNER_ERROR)
        if planner_error:
            error_message = planner_error.get(
                "message", APIMessages.plan_validation_failed(user_language)
            )
            errors = planner_error.get("errors", [])

            # Build user-friendly error explanation with i18n
            error_details = APIMessages.planner_error_header(error_message, user_language)

            if errors:
                error_details += APIMessages.planner_technical_details(user_language)
                for err in errors[:RESPONSE_MAX_ERRORS_DISPLAY]:
                    err_msg = err.get("message") or APIMessages.planner_unknown_error(user_language)
                    error_details += f"- {err_msg}\n"

                error_details += APIMessages.planner_explanation(user_language)

            # Prepend error to agent results summary
            agent_results_summary = error_details + "\n\n" + agent_results_summary

            logger.warning(
                "response_node_planner_error_included",
                run_id=run_id,
                plan_id=planner_error.get(FIELD_PLAN_ID),
                error_count=len(errors),
            )

        # Detect if this is a conversational turn based on turn_type from context resolution
        # This replaces the previous heuristic-based detection
        # Use cached i18n-aware set for all supported languages (performance)
        is_conversational_turn = (
            turn_type == TURN_TYPE_CONVERSATIONAL
            or (
                agent_results_summary in NO_EXTERNAL_AGENT_MESSAGES
                and turn_type != TURN_TYPE_REFERENCE
            )
            or (not agent_results_summary.strip() and turn_type != TURN_TYPE_REFERENCE)
        )

        # Detect mono vs multi-domain for metrics and logging
        # BugFix 2025-12-19: Use current_turn_registry (filtered) instead of full_registry
        result_domains = _detect_result_domains_from_registry(current_turn_registry)
        is_mono_domain = len(result_domains) == 1 and "other" not in result_domains

        logger.info(
            "response_node_domain_detection",
            run_id=run_id,
            agent_results_summary=agent_results_summary[:LOGGING_SUMMARY_PREVIEW_CHARS],
            is_conversational_turn=is_conversational_turn,
            result_domains=list(result_domains),
            is_mono_domain=is_mono_domain,
            agent_results_keys=list(agent_results_raw.keys()),
        )

        # Phase: Performance Optimization - Message Windowing
        # Apply windowing BEFORE filtering to reduce token count
        # Response needs rich context for creative synthesis (20 turns default)
        from src.domains.agents.utils.message_windowing import get_response_windowed_messages

        windowed_messages = get_response_windowed_messages(state[STATE_KEY_MESSAGES])

        # Filter messages for LLM context
        # Keeps: HumanMessage + ToolMessage (JSON) + AIMessage without HTML
        # Excludes: AIMessage with HTML (lia-card) to prevent LLM reformulating as Markdown
        # Uses centralized filter from utils/message_filters.py
        conversational_messages = filter_for_llm_context(windowed_messages)

        # Security 2025-12-19: Anti-hallucination for rejected plans (P0.3)
        # Remove result-containing AI messages when plan is rejected
        # This prevents LLM from using historical results to hallucinate
        pre_rejection_filter_count = len(conversational_messages)
        if plan_rejection_reason:
            conversational_messages = _filter_messages_for_rejection_context(
                conversational_messages, has_rejection=True
            )
            logger.info(
                "response_node_rejection_filter_applied",
                run_id=run_id,
                before_count=pre_rejection_filter_count,
                after_count=len(conversational_messages),
                messages_removed=pre_rejection_filter_count - len(conversational_messages),
            )

        logger.debug(
            "response_node_messages_filtered",
            run_id=run_id,
            original_count=len(state[STATE_KEY_MESSAGES]),
            windowed_count=len(windowed_messages),
            filtered_count=len(conversational_messages),
        )

        # === VISION: Substitute last HumanMessage with multimodal content (evolution F4) ===
        # Late resolution: base64 images loaded from disk just before LLM call
        # Only affects the local copy (conversational_messages), NOT the graph state
        if current_turn_attachments:
            from src.domains.attachments.llm_content import (
                ATTACHMENT_HINT_MARKER,
                build_vision_message,
            )

            # Extract clean user text (without annotation hint)
            clean_user_text = last_user_message
            # Remove the annotation hint using unique marker prefix
            marker_prefix = f"\n\n{ATTACHMENT_HINT_MARKER}"
            if clean_user_text and marker_prefix in clean_user_text:
                clean_user_text = clean_user_text[: clean_user_text.rfind(marker_prefix)]

            multimodal_msg = build_vision_message(
                text=clean_user_text,
                attachments=current_turn_attachments,
                storage_path=settings.attachments_storage_path,
            )
            # Replace last HumanMessage in conversational_messages (local copy)
            for i in range(len(conversational_messages) - 1, -1, -1):
                if isinstance(conversational_messages[i], HumanMessage):
                    conversational_messages[i] = multimodal_msg
                    break

            logger.info(
                "response_node_vision_content_injected",
                run_id=run_id,
                attachment_count=len(current_turn_attachments),
                has_images=has_vision_content,
            )

        # CRITICAL: Build SYSTEM-level anti-hallucination directive for rejected plans
        # Response directives are injected as SYSTEM messages to enforce behavior
        # Prompts are loaded from versioned files and formatted with user_language
        rejection_override = ""
        if plan_rejection_reason:
            # Directive when user rejects an execution plan
            rejection_override = load_prompt(
                "response_directive_plan_rejection",
                version=settings.response_prompt_version,
            ).format(user_language=user_language)
        # NOTE: Conversational turns are now handled by the base prompt (conditional "if agent result(s)")

        # HITL DRAFT CANCELLATION: Directive when user cancels a draft
        draft_action_result = state.get(STATE_KEY_DRAFT_ACTION_RESULT)
        if draft_action_result and draft_action_result.get("action") == DraftAction.CANCEL.value:
            draft_type = draft_action_result.get("draft_type", "action")
            rejection_override = load_prompt(
                "response_directive_draft_cancelled",
                version=settings.response_prompt_version,
            ).format(user_language=user_language, draft_type=draft_type)

        # Build ChatPromptTemplate dynamically — only include non-empty system blocks.
        # Anthropic (and potentially other providers) reject empty system content blocks.
        # By constructing the template after knowing the values, we avoid sending
        # ("system", "") which causes 400 errors with strict providers.
        safe_rejection_override = escape_braces(rejection_override)
        safe_agent_results = escape_braces(agent_results_summary)

        prompt_messages: list[Any] = [("system", base_system_prompt)]
        if safe_rejection_override:
            prompt_messages.append(("system", safe_rejection_override))
        if safe_agent_results:
            prompt_messages.append(("system", safe_agent_results))
        prompt_messages.append(MessagesPlaceholder(variable_name="messages"))

        prompt = ChatPromptTemplate.from_messages(prompt_messages)

        # Create chain
        chain = prompt | llm

        # Enrich config with node metadata for observability (Prometheus metrics)
        enriched_config = enrich_config_with_node_metadata(config, "response")

        # DEBUG: Log exactly what goes to the LLM
        logger.info(
            "response_node_llm_input_debug",
            run_id=run_id,
            agent_results_summary=(
                agent_results_summary[:1000] if agent_results_summary else "(empty)"
            ),
            conversational_messages_count=len(conversational_messages),
            conversational_messages_types=[type(m).__name__ for m in conversational_messages],
            conversational_messages_preview=[
                {
                    "type": type(m).__name__,
                    "content_preview": (
                        getattr(m, "content", "")[:300]
                        if getattr(m, "content", None)
                        else "(no content)"
                    ),
                }
                for m in conversational_messages[:5]
            ],
        )

        # =====================================================================
        # FAST PATH: Skip LLM for draft confirmation/cancellation
        # =====================================================================
        # When user confirms or cancels a draft, generate a short response directly
        # without calling the LLM. This avoids verbose "chat" responses.
        draft_action_result = state.get(STATE_KEY_DRAFT_ACTION_RESULT)
        if draft_action_result:
            draft_action = draft_action_result.get("action")
            if draft_action in (DraftAction.CONFIRM.value, DraftAction.CANCEL.value):
                # Generate short confirmation/cancellation message (i18n)
                if draft_action == DraftAction.CONFIRM.value:
                    # Use the formatted draft execution result (already set in agent_results_summary)
                    short_response = agent_results_summary or APIMessages.draft_action_completed(
                        user_language
                    )
                else:
                    short_response = APIMessages.draft_cancelled(user_language)

                logger.info(
                    "response_node_draft_fast_path",
                    run_id=run_id,
                    action=draft_action,
                    response_length=len(short_response),
                )

                result_message = AIMessage(content=short_response)
                draft_state_update: dict[str, Any] = {
                    STATE_KEY_MESSAGES: [result_message],
                    STATE_KEY_DRAFT_ACTION_RESULT: None,
                    "current_turn_registry": current_turn_registry,
                }
                track_state_updates(state, draft_state_update, "response", run_id)
                return draft_state_update

        # LangGraph 1.1 Best Practice: Add timeout to prevent indefinite hangs
        _vision_start = time.perf_counter() if has_vision_content else 0.0
        try:
            result = await asyncio.wait_for(
                chain.ainvoke(
                    {
                        STATE_KEY_MESSAGES: conversational_messages,
                    },
                    config=enriched_config,
                ),
                timeout=settings.response_llm_timeout_seconds,
            )
        except TimeoutError:
            logger.error(
                "response_llm_timeout",
                run_id=run_id,
                timeout_seconds=settings.response_llm_timeout_seconds,
            )
            # Return graceful timeout error
            error_message = AIMessage(
                content=get_error_fallback_message("TimeoutError", language=user_language)
            )
            error_state = {STATE_KEY_MESSAGES: [error_message]}
            track_state_updates(state, error_state, "response", run_id)
            return error_state

        # === VISION METRICS (evolution F4) ===
        if has_vision_content:
            from src.infrastructure.observability.metrics_attachments import (
                vision_llm_duration_seconds,
                vision_llm_requests_total,
            )

            vision_model = getattr(llm, "model_name", "unknown")
            vision_llm_requests_total.labels(model=vision_model).inc()
            vision_llm_duration_seconds.labels(model=vision_model).observe(
                time.perf_counter() - _vision_start
            )

        # Phase 3.2 - Business Metrics: Track token efficiency ratio
        # Extract agent_type from detected result domains for metrics labeling
        # Response handles both mono-domain (contacts, emails) and multi-domain queries
        if len(result_domains) > 1 and "other" not in result_domains:
            agent_type_for_metrics = "multi"  # Multi-domain response (contacts + emails)
        elif len(result_domains) == 1 and "other" not in result_domains:
            agent_type_for_metrics = list(result_domains)[0]  # Mono-domain (contacts, emails, etc.)
        else:
            agent_type_for_metrics = "generic"  # Conversational or unknown domain

        track_token_efficiency(
            config=enriched_config,
            node_name="response",
            agent_type=agent_type_for_metrics,
        )

        logger.info(
            "response_node_completed",
            run_id=run_id,
            response_length=len(result.content),
        )

        # =====================================================================
        # CURRENT TURN REGISTRY (already filtered at start of function)
        # =====================================================================
        # BugFix 2025-12-18: Photo injection fix
        # BugFix 2025-12-19: Moved filtering to start of function (before domain detection)
        #
        # current_turn_registry is already available from earlier in this function
        # (lines ~2008-2010) - no need to re-filter here

        # Post-processing: Inject place photo if LLM didn't include it
        # LLMs sometimes omit images despite fewshot instructions
        final_content = result.content

        # =====================================================================
        # INTELLIGENT FILTERING: Parse relevant_ids and filter registry
        # =====================================================================
        # The LLM may have returned <relevant_ids>...</relevant_ids> to filter results
        # based on user criteria that couldn't be filtered by the API
        try:
            relevant_ids, final_content = parse_relevant_ids_from_response(final_content)

            if relevant_ids:
                # Filter the registry to only include relevant items
                original_registry_count = len(current_turn_registry) if current_turn_registry else 0
                current_turn_registry = filter_registry_by_relevant_ids(
                    current_turn_registry, relevant_ids
                )
                logger.info(
                    "intelligent_filtering_completed",
                    run_id=run_id,
                    relevant_ids_count=len(relevant_ids),
                    original_count=original_registry_count,
                    filtered_count=len(current_turn_registry) if current_turn_registry else 0,
                    user_query_preview=last_user_message[:50] if last_user_message else "",
                )
            elif relevant_ids == []:
                # Empty list explicitly returned - LLM found no matches
                # Check if there was a filtering tag (meaning LLM tried to filter)
                if "<relevant_ids>" in result.content.lower():
                    # Skip filtering for domains where it doesn't make sense
                    # Weather: temporal references ("vendredi") shouldn't empty results
                    # Search/fetch/MCP: results are always relevant to user's query
                    from src.domains.agents.registry.domain_taxonomy import is_mcp_domain
                    from src.domains.agents.utils.type_domain_mapping import (
                        SKIP_FILTER_RESULT_KEYS,
                    )

                    should_skip = result_domains and (
                        result_domains.intersection(SKIP_FILTER_RESULT_KEYS)
                        or any(is_mcp_domain(d) for d in result_domains)
                    )
                    if should_skip:
                        logger.info(
                            "intelligent_filtering_skipped_for_domain",
                            run_id=run_id,
                            domains=list(result_domains),
                            user_query_preview=last_user_message[:50] if last_user_message else "",
                        )
                    else:
                        current_turn_registry = {}
                        logger.info(
                            "intelligent_filtering_no_matches",
                            run_id=run_id,
                            user_query_preview=last_user_message[:50] if last_user_message else "",
                        )
        except (ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
            # Log error but continue with unfiltered registry
            logger.warning(
                "intelligent_filtering_error",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Keep original content and registry (no filtering applied)

        # Debug: Log injection preconditions
        logger.info(
            "photo_injection_check",
            has_registry=bool(current_turn_registry),
            registry_count=len(current_turn_registry) if current_turn_registry else 0,
            full_registry_count=len(full_registry) if full_registry else 0,
            result_domains=list(result_domains),
            places_in_domains="places" in result_domains,
        )

        # =====================================================================
        # V3 HTML RENDERING: Inject structured HTML after LLM response
        # =====================================================================
        # NOTE: V3 HTML rendering is always enabled
        # - LLM received text summary (not formatted Markdown)
        # - LLM generated conversational response
        # - Now we inject the structured HTML for data display
        #
        # Two sources of data:
        # 1. current_turn_registry: Standard tool results (ACTION turns, REFERENCE with enriched data)
        # 2. resolved_context_for_html: REFERENCE turns using resolved_context directly
        html_content = ""
        source = ""

        try:
            if current_turn_registry:
                # Primary: Use registry data from tool results
                html_content = generate_html_for_registry(
                    data_registry=current_turn_registry,
                    user_viewport=user_viewport,
                    user_language=user_language,
                    user_timezone=user_timezone,
                )
                source = "registry"
            elif resolved_context_for_html:
                # Fallback: Use resolved_context for REFERENCE turns
                html_content = generate_html_for_resolved_context(
                    resolved_context=resolved_context_for_html,
                    user_viewport=user_viewport,
                    user_language=user_language,
                    user_timezone=user_timezone,
                )
                source = "resolved_context"

            if html_content:
                # Inject HTML cards at the end of the LLM response
                # Order: LLM response (text + suggestions) → HTML cards
                final_content = final_content + "\n\n" + html_content
                logger.info(
                    "html_injected_post_llm",
                    html_length=len(html_content),
                    source=source,
                    registry_items=(len(current_turn_registry) if current_turn_registry else 0),
                    resolved_items=(
                        len(resolved_context_for_html.get("items", []))
                        if resolved_context_for_html
                        else 0
                    ),
                )
        except (ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
            # Fallback: Log error but don't break the response
            logger.warning(
                "html_injection_failed",
                error=str(e),
                error_type=type(e).__name__,
                source=source or "unknown",
            )
            # Response continues with LLM output only (no HTML)

        # Update result content if modified
        content_was_modified = final_content != result.content
        if content_was_modified:
            result = AIMessage(content=final_content)

        state_update: dict[str, Any] = {STATE_KEY_MESSAGES: [result]}
        # STREAMING FIX: Signal content replacement to frontend when post-processing occurred
        # - If content was modified (photo/HTML injection): set final_content for replacement chunk
        # - Otherwise: set None to clear persisted value from previous turns
        state_update["content_final_replacement"] = final_content if content_was_modified else None
        # Data Registry LOT 5.4: Clear draft_action_result after processing to prevent persistence
        state_update[STATE_KEY_DRAFT_ACTION_RESULT] = None
        # BugFix 2025-12-18: Store filtered registry for SSE streaming
        # The streaming service should send only current turn items, not the full merged registry
        state_update["current_turn_registry"] = current_turn_registry
        # Knowledge Enrichment (Brave Search): Store result for debug panel
        state_update["knowledge_enrichment_result"] = knowledge_enrichment_result
        # Memory Injection: Store debug details for debug panel (memory tuning)
        state_update["memory_injection_debug"] = memory_injection_debug
        # RAG Spaces: Store debug details for debug panel
        state_update["rag_injection_debug"] = rag_injection_debug
        # Journals: Store debug details for debug panel
        state_update["journal_injection_debug"] = journal_injection_debug

        # ===================================================================
        # PHASE 3.2 - BUSINESS METRICS INSTRUMENTATION
        # ===================================================================
        # Track business-level KPIs for conversation (cost, tokens, success rate, etc.)
        # Graceful degradation: metrics failures don't crash response_node
        try:
            from src.domains.agents.services.business_metrics import (
                calculate_conversation_metrics_async,
            )
            from src.infrastructure.database import get_db_context
            from src.infrastructure.observability.metrics_business import (
                agent_success_rate_total,
                conversation_cost_usd,
                conversation_tokens_total,
                conversation_turns_total,
                cost_per_successful_conversation_usd,
            )

            # Calculate all metrics via dedicated service (async with DB pricing)
            async with get_db_context() as db:
                metrics = await calculate_conversation_metrics_async(state, config, db)

            # Instrument Prometheus metrics (P0 - Critical)
            conversation_cost_usd.labels(agent_type=metrics.agent_type).observe(metrics.cost_usd)
            conversation_tokens_total.labels(agent_type=metrics.agent_type).observe(
                metrics.tokens_total
            )
            agent_success_rate_total.labels(
                agent_type=metrics.agent_type, outcome=metrics.outcome
            ).inc()
            conversation_turns_total.labels(agent_type=metrics.agent_type).observe(metrics.turns)

            # Cost per successful conversation (only if outcome=success)
            if metrics.outcome == "success":
                cost_per_successful_conversation_usd.labels(agent_type=metrics.agent_type).observe(
                    metrics.cost_usd
                )

            logger.debug(
                "business_metrics_instrumented",
                run_id=run_id,
                agent_type=metrics.agent_type,
                cost_usd=metrics.cost_usd,
                tokens_total=metrics.tokens_total,
                turns=metrics.turns,
                outcome=metrics.outcome,
            )
        except (ValueError, KeyError, RuntimeError, AttributeError, ImportError) as e:
            # Graceful degradation - business metrics failure must not break response_node
            logger.error(
                "business_metrics_instrumentation_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=False,  # Don't spam logs with full stack trace
            )

        # PHASE 2.5 - LangGraph Observability: Track state updates
        track_state_updates(state, state_update, "response", run_id)

        # ===================================================================
        # PLAN PATTERN LEARNING (fire-and-forget, post-execution)
        # ===================================================================
        # Record plan execution success/failure for pattern learning.
        # Complements semantic_validator_node recording by capturing:
        # - Patterns that bypassed semantic validation (simple read queries)
        # - Execution outcomes (not just validation outcomes)
        #
        # Only records if:
        # 1. turn_type is ACTION (not CONVERSATIONAL/REFERENCE)
        # 2. execution_plan exists (planner was invoked)
        # 3. semantic_validation NOT in state (avoid double-recording)
        # ===================================================================
        try:
            # Lazy imports for functions only (constants imported at module level)
            from src.domains.agents.analysis.query_intelligence_helpers import (
                get_query_intelligence_from_state,
            )
            from src.domains.agents.services.plan_pattern_learner import (
                record_plan_failure,
                record_plan_success,
            )

            execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
            semantic_validation = state.get(STATE_KEY_SEMANTIC_VALIDATION)

            # Only record if: ACTION turn + plan exists + not already recorded by semantic_validator
            # Note: turn_type from QueryIntelligence is uppercase "ACTION", constant is lowercase
            if (
                (turn_type or "").upper() == TURN_TYPE_ACTION.upper()
                and execution_plan
                and semantic_validation is None
            ):
                qi_object = get_query_intelligence_from_state(state)

                if qi_object:
                    # Determine success/failure based on execution outcome
                    planner_error = state.get(STATE_KEY_PLANNER_ERROR)
                    plan_rejected = state.get(STATE_KEY_PLAN_REJECTION_REASON)

                    if planner_error or plan_rejected:
                        # Execution failed - record as failure
                        record_plan_failure(execution_plan, qi_object)
                        logger.info(
                            "pattern_learning_recorded_failure_post_execution",
                            run_id=run_id,
                            reason="planner_error" if planner_error else "plan_rejected",
                        )
                    else:
                        # Execution succeeded - record as success
                        record_plan_success(execution_plan, qi_object)
                        logger.info(
                            "pattern_learning_recorded_success_post_execution",
                            run_id=run_id,
                            turn_type=turn_type,
                        )
                else:
                    logger.debug(
                        "pattern_learning_skipped_no_qi",
                        run_id=run_id,
                        reason="qi_object is None",
                    )
            else:
                # Log why pattern learning was skipped (for debugging)
                logger.debug(
                    "pattern_learning_skipped_conditions_not_met",
                    run_id=run_id,
                    turn_type=turn_type,
                    has_execution_plan=execution_plan is not None,
                    has_semantic_validation=semantic_validation is not None,
                    reason=(
                        "already_recorded_by_semantic_validator"
                        if semantic_validation
                        else "not_action_turn_or_no_plan"
                    ),
                )
        except (ValueError, KeyError, RuntimeError, AttributeError, ImportError) as e:
            # Graceful degradation - pattern learning failure must not break response_node
            logger.warning(
                "pattern_learning_recording_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )

        # ===================================================================
        # PHASE 4 - LONG-TERM MEMORY EXTRACTION (Background)
        # ===================================================================
        # Extract psychological profile data from conversation asynchronously.
        # Uses safe_fire_and_forget to prevent GC issues with background tasks.
        # Non-blocking: extraction runs after response is returned to user.
        # Check user memory preference before scheduling extraction
        #
        # GUARD: Skip extraction for automated sources (scheduled actions).
        # Only direct user-typed messages should feed long-term memory.
        # Proactive notifications (heartbeat, interests) are AIMessage and
        # naturally excluded by the extractor's HumanMessage filter.
        _session_id = config.get(FIELD_METADATA, {}).get(FIELD_SESSION_ID, "")
        _is_automated_source = isinstance(_session_id, str) and _session_id.startswith(
            SCHEDULED_ACTIONS_SESSION_PREFIX
        )

        try:
            # user_memory_enabled already defined above for injection
            if _is_automated_source:
                logger.info(
                    "memory_extraction_skipped_automated_source",
                    run_id=run_id,
                    session_id=_session_id,
                )
            elif not user_memory_enabled:
                logger.info(
                    "memory_extraction_skipped_user_disabled",
                    run_id=run_id,
                    user_memory_enabled=user_memory_enabled,
                )
            else:
                user_id = config.get("configurable", {}).get("langgraph_user_id")
                thread_id = config.get("configurable", {}).get("thread_id", "unknown")

                if user_id:
                    # LangGraph v1.0: Store is NOT accessible via config in nodes
                    # Must use the global singleton - same pattern as planner_node.py
                    store = await get_tool_context_store()

                    if store:
                        # Count messages for logging
                        msg_count = len(state.get(STATE_KEY_MESSAGES, []))
                        safe_fire_and_forget(
                            extract_memories_background(
                                store=store,
                                user_id=user_id,
                                messages=state[STATE_KEY_MESSAGES],
                                session_id=thread_id,
                                personality_instruction=personality_instruction,
                                conversation_id=thread_id,  # For token cost linking to conversation
                                parent_run_id=run_id,  # UPSERT into originating message's token summary
                            ),
                            name=f"memory_extraction_{user_id}_{thread_id[:8]}",
                            run_id=run_id,  # Register for awaiting before SSE done
                        )
                        logger.info(
                            "memory_extraction_scheduled",
                            run_id=run_id,
                            user_id=user_id,
                            thread_id=thread_id,
                            message_count=msg_count,
                        )
                    else:
                        logger.warning(
                            "memory_extraction_skipped_no_store",
                            run_id=run_id,
                            user_id=user_id,
                            store_available=store is not None,
                        )
                else:
                    logger.warning(
                        "memory_extraction_skipped_no_user",
                        run_id=run_id,
                        has_configurable="configurable" in config,
                    )
        except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
            # Graceful degradation - memory extraction failure must not break response_node
            logger.error(
                "memory_extraction_scheduling_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

        # ===================================================================
        # INTEREST EXTRACTION (Background)
        # ===================================================================
        # Extract user interests from conversation asynchronously.
        # Uses safe_fire_and_forget to prevent GC issues with background tasks.
        # Non-blocking: extraction runs after response is returned to user.
        # GUARD: Same automated source filter as memory extraction above.
        try:
            if _is_automated_source:
                logger.info(
                    "interest_extraction_skipped_automated_source",
                    run_id=run_id,
                    session_id=_session_id,
                )
            elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
                logger.debug(
                    "interest_extraction_skipped_no_user",
                    run_id=run_id,
                )
            else:
                thread_id = config.get("configurable", {}).get("thread_id", "unknown")
                msg_count = len(state.get(STATE_KEY_MESSAGES, []))
                safe_fire_and_forget(
                    extract_interests_background(
                        user_id=user_id,
                        messages=state[STATE_KEY_MESSAGES],
                        session_id=thread_id,
                        conversation_id=thread_id,
                        user_language=user_language,
                        parent_run_id=run_id,  # UPSERT into originating message's token summary
                    ),
                    name=f"interest_extraction_{user_id}_{thread_id[:8]}",
                    run_id=run_id,  # Register for awaiting before SSE done
                )
                logger.info(
                    "interest_extraction_scheduled",
                    run_id=run_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    message_count=msg_count,
                )
        except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
            # Graceful degradation - interest extraction failure must not break response_node
            logger.error(
                "interest_extraction_scheduling_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

        # ===================================================================
        # JOURNAL ENTRY EXTRACTION (Background)
        # ===================================================================
        # Extract journal entries from conversation asynchronously.
        # Uses safe_fire_and_forget to prevent GC issues with background tasks.
        # Non-blocking: extraction runs after response is returned to user.
        # GUARD: Same automated source filter as memory/interest extraction.
        try:
            user_journals_enabled = config.get("configurable", {}).get(
                "user_journals_enabled", False
            )
            if _is_automated_source:
                logger.info(
                    "journal_extraction_skipped_automated_source",
                    run_id=run_id,
                    session_id=_session_id,
                )
            elif not user_journals_enabled:
                logger.debug(
                    "journal_extraction_skipped_user_disabled",
                    run_id=run_id,
                )
            elif not (user_id := config.get("configurable", {}).get("langgraph_user_id")):
                logger.debug(
                    "journal_extraction_skipped_no_user",
                    run_id=run_id,
                )
            else:
                from src.domains.journals.extraction_service import (
                    extract_journal_entry_background,
                )

                thread_id = config.get("configurable", {}).get("thread_id", "unknown")
                msg_count = len(state.get(STATE_KEY_MESSAGES, []))
                safe_fire_and_forget(
                    extract_journal_entry_background(
                        user_id=user_id,
                        messages=state[STATE_KEY_MESSAGES],
                        session_id=thread_id,
                        personality_instruction=personality_instruction,
                        conversation_id=thread_id,
                        user_language=user_language,
                        parent_run_id=run_id,
                        assistant_response=final_content,
                    ),
                    name=f"journal_extraction_{user_id}_{thread_id[:8]}",
                    run_id=run_id,
                )
                logger.info(
                    "journal_extraction_scheduled",
                    run_id=run_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    message_count=msg_count,
                )
        except (ValueError, KeyError, RuntimeError, AttributeError, ImportError, OSError) as e:
            # Graceful degradation - journal extraction failure must not break response_node
            logger.error(
                "journal_extraction_scheduling_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

        # Return updated messages (will be merged by add_messages_with_truncate reducer)
        return state_update

    except (RuntimeError, ValueError, KeyError, TypeError, AttributeError) as e:
        # Business logic error handling (fallback message)
        # Note: Basic error metrics/logs already tracked by @track_metrics decorator
        logger.error(
            "response_node_exception",
            run_id=run_id,
            exception_type=type(e).__name__,
            exception_message=str(e),
            exc_info=True,  # Include stack trace in logs
        )

        graph_exceptions_total.labels(
            node_name="response",
            exception_type=type(e).__name__,
        ).inc()

        # Fallback: return error message
        # BUG FIX: Use AIMessage (not HumanMessage) for error responses from assistant
        error_message = AIMessage(content=get_error_fallback_message(type(e).__name__))

        error_state = {STATE_KEY_MESSAGES: [error_message]}
        track_state_updates(state, error_state, "response", run_id)
        return error_state
