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
from contextlib import suppress
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from src.domains.agents.data_registry.models import RegistryItemType
    from src.domains.agents.drafts.display import DraftDisplayConfig
from urllib.parse import urlparse
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    RESPONSE_DISPLAY_MODE_CARDS,
    RESPONSE_DISPLAY_MODE_HTML,
)
from src.core.field_names import (
    FIELD_METADATA,
    FIELD_PLAN_ID,
    FIELD_REACT_SYNTHESIS,
    FIELD_RUN_ID,
)
from src.core.i18n import _
from src.core.i18n_api_messages import (
    NO_EXTERNAL_AGENT_MESSAGES,
    APIMessages,
)
from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.constants import (
    DATA_FILTERING_GENERATION_ERROR_MARKER,
    LOGGING_SUMMARY_PREVIEW_CHARS,
    RESPONSE_MAX_ERRORS_DISPLAY,
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_COMPLETED_STEPS,
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
    STATE_KEY_VALIDATION_RESULT,
    TURN_TYPE_ACTION,
    make_agent_result_key,
)
from src.domains.agents.context.recent_entities import (
    build_recent_entities_context,
    should_ground_from_recent_entities,
)

# V3 Display Architecture imports
from src.domains.agents.display.config import config_for_viewport

# ResponseFormatter removed - pure HTML mode only
from src.domains.agents.display.html_renderer import NestedData, get_html_renderer
from src.domains.agents.display.sentinel_filter import strip_widget_sentinels
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
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.post_response_extractions import (
    _schedule_post_response_extractions,
)
from src.domains.agents.orchestration.correlation_detector import detect_correlations
from src.domains.agents.prompts import (
    escape_braces,
    get_error_fallback_message,
    get_response_prompt,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.plan_blockers import (
    executed_tool_names,
    format_plan_blockers,
    summarize_plan_blockers,
)
from src.domains.agents.utils.message_filters import (
    drop_current_turn_responses,
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
from src.domains.agents.utils.turn_type import (
    is_action_turn as _is_action_turn,
)
from src.domains.agents.utils.turn_type import (
    is_conversational_turn as _is_conversational_turn,
)
from src.domains.agents.utils.turn_type import (
    is_reference_turn as _is_reference_turn,
)
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics import graph_exceptions_total
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
)
from src.infrastructure.observability.metrics_registry import (
    widget_sentinels_stripped_total,
)
from src.infrastructure.observability.token_efficiency import track_token_efficiency
from src.infrastructure.observability.tracing import trace_node

# LLM-Native Semantic Architecture: State key for tool results
STATE_KEY_TOOL_RESULTS = "tool_results"

# Data Registry LOT 5.4: State key for draft action result from draft_critique_node
STATE_KEY_DRAFT_ACTION_RESULT = "draft_action_result"

logger = get_logger(__name__)


def _plan_execution_failed(state: dict[str, Any]) -> bool:
    """Return True when the current turn's execution plan totally failed.

    Audit D3: the planner-route skill activation must not fire on the back of
    a failed plan. In the incident, a plan whose only step (an MCP task) timed
    out still activated the plan's ``skill_name`` and synthesized a confident
    "success" answer from an unrelated skill. When the plan executor reports
    failure the response should reflect it (or fall back to the authoritative
    QueryAnalyzer detection) instead of masking it.

    Only the ``plan_executor`` aggregate is inspected: its ``status`` is
    "failed" only when EVERY step failed (see
    ``map_execution_result_to_agent_result``). A partially successful plan is
    not treated as a failure here.

    Args:
        state: The LangGraph message state.

    Returns:
        True only when a ``plan_executor`` result exists for the current turn
        and its status is "failed".
    """
    agent_results = state.get(STATE_KEY_AGENT_RESULTS) or {}
    turn_id = state.get(STATE_KEY_CURRENT_TURN_ID, 0)
    key = make_agent_result_key(turn_id, "plan_executor")
    entry = agent_results.get(key)
    if not isinstance(entry, dict):
        return False
    return entry.get("status") == "failed"


def _should_inject_html_directive(display_mode: str | None, route_to: str | None) -> bool:
    """Whether the rich HTML response directive should be injected this turn.

    Rich HTML enrichment is only pertinent for tool/data turns — those the
    router sends to the planner (``route_to == "planner"``, which is exactly
    how the router derives intention ``"action"``). For a conversational turn
    (any other ``route_to``) the reply is streamed verbatim to the TTS engine
    via the progressive chat path; emitting HTML there would make the voice
    speak tags and CSS aloud. Suppressing the directive keeps conversational
    replies in Markdown, rendered identically by the frontend (ReactMarkdown +
    rehypeRaw) in every display mode. Keying on ``route_to`` mirrors the exact
    source the voice path uses, so the display gate can never desync from it.

    Args:
        display_mode: The user's response display mode preference.
        route_to: The router's routing target for the current turn
            (``"planner"`` for action turns; anything else — or ``None`` on a
            fallback / missing query intelligence — is treated as
            conversational and suppresses the directive).

    Returns:
        ``True`` only when HTML display mode is active AND the turn routed to
        the planner.
    """
    return display_mode == RESPONSE_DISPLAY_MODE_HTML and route_to == "planner"


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
    "/api/v1/attachments/",  # Generated images (AI Image Generation)
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
        # Never expose raw exception details — they could leak to the user via LLM synthesis
        return {
            "status": "error",
            "message": _("The action could not be completed. Please try again."),
            "draft_id": draft_action_result.get("draft_id"),
            "draft_type": draft_action_result.get("draft_type"),
            "action": DraftAction.CONFIRM.value,
        }


def _format_draft_execution_result(result: dict[str, Any] | None) -> str:
    """
    Format draft execution result for LLM context.

    Reads ``DRAFT_DISPLAY_REGISTRY`` (see ADR-085) for the per-``DraftType``
    display configuration: domain emoji, label fields, optional contextual
    datetime, detailed-view fields, plus the noun/verb keys used to compose
    a localized header like ``"3 rappels supprimés"`` (with proper
    gender/number agreement per language).

    Args:
        result: Draft execution result dict with:
            - status: "success" | "cancelled" | "error" | "partial_error"
            - message: Localized message
            - draft_type: Type of draft (contact, event, email, reminder_delete...)
            - action: Optional, e.g. ``"confirm_batch"``
            - data: Result data dict (may contain ``html_link``, ``_draft_content``,
                ``batch_results``, ``success_count``, ``total_count``)

    Returns:
        Formatted markdown string for ``agent_results_summary``.
    """
    if not result:
        return ""

    from src.core.i18n_drafts import get_draft_preview_labels
    from src.core.time_utils import format_datetime_for_display
    from src.domains.agents.drafts.display import (
        get_draft_display_config,
        resolve_nested_value,
    )

    status = result.get("status", "unknown")
    message = result.get("message", "")
    draft_type = result.get("draft_type", "action")
    data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
    action = result.get("action", "")

    config = get_draft_display_config(draft_type)
    domain_emoji = config.emoji if config else ""

    # ------------------------------------------------------------------ Batch
    if action == DraftAction.CONFIRM_BATCH.value and status in ("success", "partial_error"):
        return _format_batch_result(
            status=status,
            draft_type=draft_type,
            domain_emoji=domain_emoji,
            config=config,
            data=data,
        )

    # ------------------------------------------------------------- Single OK
    if status == "success":
        draft = data.get("_draft_content", {}) if isinstance(data, dict) else {}
        user_lang = draft.get("user_language") or "fr"
        user_tz = draft.get("user_timezone") or DEFAULT_USER_DISPLAY_TIMEZONE
        labels = get_draft_preview_labels(user_lang)

        details: list[str] = []
        if config:
            for field in config.detail_fields:
                value = (
                    resolve_nested_value(draft, field.content_key)
                    if "." in field.content_key
                    else (draft.get(field.content_key) or data.get(field.content_key))
                )
                if value is None or not str(value).strip():
                    continue

                label = labels.get(field.label_key, field.content_key)
                str_value = str(value)
                if field.is_datetime and isinstance(value, str) and "T" in value:
                    # Keep raw ISO if formatting fails.
                    with suppress(ValueError, TypeError):
                        str_value = format_datetime_for_display(
                            value, user_tz, user_lang, include_time=True
                        )
                # Truncate long body-like fields (last path segment for nested keys).
                last_key = field.content_key.rsplit(".", 1)[-1]
                if last_key in ("body", "description", "notes") and len(str_value) > 200:
                    str_value = str_value[:200] + "…"
                # Explicit <br/> per field: the response LLM re-emits this block
                # inside its HTML answer, where bare "\n" soft-wraps and markdown
                # "-" bullets get half-copied (observed: two fields merged with a
                # stray dash). <br/> survives the copy verbatim and renders as a
                # hard break in every display mode (sanitize schema keeps `br`,
                # same convention as the draft preview_renderer).
                details.append(f"<br/>{field.emoji} **{label}** : {str_value}")

        html_link = data.get("html_link")
        if html_link:
            details.append(f"<br/>🔗 [{_('Link', user_lang)}]({html_link})")

        header = f"\n\n{domain_emoji} ✅ {message}"
        if details:
            return f"{header}\n" + "\n".join(details)
        return header

    if status == "cancelled":
        return f"\n\n{domain_emoji} 🚫 {message}"

    if status == "partial_error":
        # Non-batch partial_error fallback (defensive — batch is handled above).
        success_count = data.get("success_count", 0)
        total_count = data.get("total_count", 0)
        return f"\n\n{domain_emoji} ⚠️ {message} ({success_count}/{total_count})"

    if status == "error":
        return f"\n\n{domain_emoji} ❌ {message}"

    return ""


def _format_batch_result(
    status: str,
    draft_type: str,
    domain_emoji: str,
    config: "DraftDisplayConfig | None",
    data: dict[str, Any],
) -> str:
    """Render the batch (``CONFIRM_BATCH``) execution result block.

    Builds a localized header (``"3 rappels supprimés"``) plus one row per
    item with the configured ``item_label_fields`` and optional secondary
    datetime context. Falls back gracefully if the registry has no entry
    (defensive — startup assertion should make this impossible).

    Args:
        status: Either ``"success"`` or ``"partial_error"``.
        draft_type: Draft type string from the execution result.
        domain_emoji: Pre-resolved emoji from the registry (or ``""``).
        config: Display config for the draft type, or ``None`` if unknown.
        data: Execution data dict containing ``batch_results``,
            ``success_count``, ``total_count``.

    Returns:
        Formatted markdown block ready for ``agent_results_summary``.
    """
    from src.core.i18n_drafts import compose_result_header
    from src.core.time_utils import format_value_if_datetime_string
    from src.domains.agents.drafts.display import resolve_nested_value

    batch_results = data.get("batch_results", [])
    success_count = data.get("success_count", 0)
    total_count = data.get("total_count", 0)

    # Resolve user locale/timezone from any item that carries them.
    user_lang = "fr"
    user_tz = DEFAULT_USER_DISPLAY_TIMEZONE
    for br in batch_results:
        br_data = br.get("data", {}) if isinstance(br.get("data"), dict) else {}
        br_draft = br_data.get("_draft_content", {}) or {}
        if br_draft.get("user_language"):
            user_lang = br_draft["user_language"]
        if br_draft.get("user_timezone"):
            user_tz = br_draft["user_timezone"]
        if user_lang and user_tz:
            break

    lines: list[str] = []
    for br in batch_results:
        br_data = br.get("data", {}) if isinstance(br.get("data"), dict) else {}
        draft_content = br_data.get("_draft_content", {}) or {}
        br_status = br.get("status", "")
        row_emoji = "✅" if br_status == "success" else "❌"

        # Extract human-readable label using the registry-declared fields.
        item_label = ""
        if config:
            for key in config.item_label_fields:
                value = (
                    resolve_nested_value(draft_content, key)
                    if "." in key
                    else draft_content.get(key)
                )
                if value:
                    item_label = " ".join(str(value).split())
                    break
        if len(item_label) > 60:
            item_label = item_label[:57] + "..."

        # Optional contextual datetime appended to the row.
        secondary = ""
        if config and config.item_secondary_datetime_key:
            dt_value = (
                resolve_nested_value(draft_content, config.item_secondary_datetime_key)
                if "." in config.item_secondary_datetime_key
                else draft_content.get(config.item_secondary_datetime_key)
            )
            if dt_value and isinstance(dt_value, str):
                formatted = format_value_if_datetime_string(
                    dt_value,
                    user_timezone=user_tz,
                    locale=user_lang,
                    include_time=True,
                    include_day_name=False,
                )
                if formatted != dt_value:
                    secondary = f" — {formatted}"

        if item_label:
            lines.append(f"{row_emoji} **{item_label}**{secondary}")
        else:
            logger.warning(
                "draft_result_format_empty_label",
                draft_type=draft_type,
                available_keys=sorted(draft_content.keys()),
            )
            lines.append(f"{row_emoji} {br.get('message', '')}")

    items_block = "\n".join(lines)
    status_emoji = "✅" if status == "success" else "⚠️"

    # Localized header with noun + verb agreement when the registry knows the type.
    if config:
        header_text = compose_result_header(
            success_count=success_count,
            total_count=total_count,
            noun_key=config.noun_key,
            verb_past_key=config.verb_past_key,
            language=user_lang,
        )
        return f"\n\n{domain_emoji} {status_emoji} {header_text}\n{items_block}"

    # Unknown draft type — preserve the legacy bare "X/Y" header as a fallback.
    return f"\n\n{domain_emoji} {status_emoji} {success_count}/{total_count}\n{items_block}"


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


def _filter_registry_by_types(
    data_registry: dict[str, Any] | None,
    allowed_types: "frozenset[RegistryItemType]",
    *,
    include: bool,
) -> dict[str, Any]:
    """Return a copy of ``data_registry`` filtered by item type.

    Args:
        data_registry: Source registry dict (may contain Pydantic
            ``RegistryItem`` instances or their dict serializations).
        allowed_types: Set of ``RegistryItemType`` members to match against.
        include: If True, keep only items whose type is in ``allowed_types``.
            If False, keep only items whose type is NOT in ``allowed_types``.

    Returns:
        New dict with the same ids mapping to the same item references —
        filtered according to ``include``.
    """
    if not data_registry:
        return {}

    allowed_values: set[str] = {t.value for t in allowed_types}
    result: dict[str, Any] = {}
    for item_id, item in data_registry.items():
        raw_type = getattr(item, "type", None)
        if raw_type is None and isinstance(item, dict):
            raw_type = item.get("type")
        if hasattr(raw_type, "value"):
            raw_type = raw_type.value
        is_allowed = raw_type in allowed_values
        if (include and is_allowed) or (not include and not is_allowed):
            result[item_id] = item
    return result


def generate_html_for_interactive_widgets(
    data_registry: dict[str, Any] | None,
    user_viewport: str = "desktop",
    user_language: str = settings.default_language,
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
) -> str:
    """Render only the interactive-widget registry items (SKILL_APP, MCP_APP,
    DRAFT) to their frontend sentinels.

    These widgets are **features the user explicitly requested** (a skill
    producing a frame/image, an MCP app, a draft awaiting confirmation).
    They rely on React host components (iframe sandbox, draft UI) which
    cannot be reproduced by the LLM in plain markdown or HTML. Therefore
    they must always be injected post-LLM — independently of the user's
    ``user_display_mode`` preference, which only governs the data-card
    rendering path.

    Args:
        data_registry: Full current-turn registry dict.
        user_viewport: Device viewport (mobile/tablet/desktop).
        user_language: Language code.
        user_timezone: User's IANA timezone.

    Returns:
        HTML string containing only the sentinels for interactive widgets,
        or ``""`` if the registry has none.
    """
    from src.domains.agents.data_registry.models import INTERACTIVE_WIDGET_TYPES

    filtered = _filter_registry_by_types(data_registry, INTERACTIVE_WIDGET_TYPES, include=True)
    if not filtered:
        return ""
    return generate_html_for_registry(
        data_registry=filtered,
        user_viewport=user_viewport,
        user_language=user_language,
        user_timezone=user_timezone,
    )


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


def _merge_react_synthesis_result(
    agent_results: dict[str, Any] | None,
    react_message: str,
    current_turn: int,
    current_registry: dict[str, Any],
) -> dict[str, Any]:
    """Merge the ReAct final answer into agent_results without overwriting entries.

    The ReAct answer is keyed ``{turn}:react_agent``. When the Initiative node ran on
    the ReAct nominal path (react_finalize -> initiative -> response), it has already
    written ``{turn}:initiative`` into agent_results; a plain ``if not agent_results``
    guard would then skip the ReAct answer entirely, dropping the user-facing reply.
    This merge is idempotent on the react key, so graph re-entry never duplicates it.

    Args:
        agent_results: Existing agent_results map (possibly populated by Initiative).
        react_message: The ReAct loop's final answer text.
        current_turn: Current turn id (for the composite key).
        current_registry: Registry items for this turn (drives HTML cards / display).

    Returns:
        A new dict containing every existing entry plus the ``{turn}:react_agent`` one.
    """
    merged = dict(agent_results or {})
    react_key = f"{current_turn}:react_agent"
    if react_key not in merged:
        merged[react_key] = {
            "data": {FIELD_REACT_SYNTHESIS: react_message},
            "registry_updates": current_registry,
        }
    return merged


class _SkillActivationResult(NamedTuple):
    """Outputs of :func:`_activate_response_skills` threaded back into response_node."""

    skills_context: str
    skill_react_response: str | None
    activated_skill_name: str | None
    skill_registry_updates: dict[str, Any] | None
    current_turn_registry: dict[str, Any] | None
    # ``react_agent_result`` state contract (MessagesState), never the runner's
    # dataclass — see the normalization in the skill-runner branch.
    react_result: dict[str, Any] | None


def _get_skill_data(skill_name: str, skill_user_id: str | None) -> dict | None:
    """Get skill data from cache (user-scoped first, then global)."""
    from src.domains.skills.cache import SkillsCache

    return SkillsCache.get_by_name_for_user(skill_name, skill_user_id) or SkillsCache.get_by_name(
        skill_name
    )


def _skill_needs_runner(skill_name: str, skill_user_id: str | None) -> bool:
    """Return True if the skill has scripts (needs LLM to orchestrate)."""
    skill_data = _get_skill_data(skill_name, skill_user_id)
    if not skill_data:
        return False
    return bool(skill_data.get("scripts"))


def _skill_has_resources_only(skill_name: str, skill_user_id: str | None) -> bool:
    """Return True if the skill has resources but no scripts."""
    skill_data = _get_skill_data(skill_name, skill_user_id)
    if not skill_data:
        return False
    return bool(skill_data.get("references")) and not skill_data.get("scripts")


def _load_all_skill_resources(skill_name: str, skill_user_id: str | None) -> str:
    """Load all reference files for a skill and return concatenated content.

    The ``references`` field of a skill contains basenames only
    (see loader.py -- ``_list_dir(path.parent / "references")``).
    Files live inside the ``references/`` subdirectory of the skill,
    so we must re-prefix the path here to resolve them correctly.
    """
    skill_data = _get_skill_data(skill_name, skill_user_id)
    if not skill_data:
        return ""
    from pathlib import Path

    skill_dir = Path(skill_data["source_path"]).parent.resolve()
    references_dir = skill_dir / "references"
    parts: list[str] = []
    for ref in skill_data.get("references", []):
        ref_path = (references_dir / ref).resolve()
        # Path traversal protection: reject any ref that escapes
        # the skill directory (e.g., "../other-skill/secret.md").
        try:
            ref_path.relative_to(skill_dir)
        except ValueError:
            logger.warning(
                "skill_resource_path_traversal",
                skill_name=skill_name,
                path=ref,
            )
            continue
        if ref_path.exists() and ref_path.is_file():
            try:
                content = ref_path.read_text(encoding="utf-8")
                parts.append(f'<resource path="{ref}">\n{content}\n</resource>')
            except Exception as read_err:
                logger.warning(
                    "skill_resource_read_error",
                    skill_name=skill_name,
                    path=ref,
                    error=str(read_err),
                )
        else:
            logger.warning(
                "skill_resource_file_not_found",
                skill_name=skill_name,
                path=ref,
                expected_location=str(ref_path),
            )
    return "\n\n".join(parts)


def _plan_already_produced_skill_app(state: MessagesState, skill_name: str) -> bool:
    """Return True when THIS TURN's plan already produced a SKILL_APP registry
    item for this skill.

    Addresses the B1 hybrid case (plan_template + scripts): when the
    plan's ``run_skill_script`` step has already emitted the interactive
    widget, the ReactSubAgentRunner would only re-synthesize text
    around a frame that is already final. Skipping the runner avoids
    a ~15k tokens LLM round-trip for zero net gain.

    Scoped on TWO axes, and both matter:

    - ``skill_name``, so another skill's widget never fires the guard;
    - the CURRENT TURN. ``agent_results`` accumulates across the whole
      conversation (production showed keys for turns 41 through 48 in a single
      state). Without the turn scope, one widget produced at turn 47 silenced
      the runner at every later turn that activated the same skill — and when
      the plan did not re-run the script, no SKILL_APP was created at all and
      the widget silently vanished (observed on run ``d0fad28b``, 2026-07-21:
      the guard fired, the turn registry held only ``weather``/``location``,
      and the map was never rendered).
    """
    agent_results = state.get(STATE_KEY_AGENT_RESULTS) or {}
    current_turn = state.get(STATE_KEY_CURRENT_TURN_ID, 0)
    turn_prefix = f"{current_turn}:"
    for result_key, result_entry in agent_results.items():
        # Composite key "{turn_id}:{agent_name}" (see _merge_react_synthesis_result).
        if not str(result_key).startswith(turn_prefix):
            continue
        if not isinstance(result_entry, dict):
            continue
        registry_updates = result_entry.get("registry_updates") or {}
        for item in registry_updates.values():
            # RegistryItem may be a Pydantic model or a dict
            item_type = getattr(item, "type", None)
            if item_type is None and isinstance(item, dict):
                item_type = item.get("type")
            # Enum values stringify consistently
            if hasattr(item_type, "value"):
                item_type = item_type.value
            if item_type != "SKILL_APP":
                continue
            payload = getattr(item, "payload", None)
            if payload is None and isinstance(item, dict):
                payload = item.get("payload") or {}
            if not payload:
                continue
            if payload.get("skill_name") == skill_name:
                return True
    return False


async def _instrument_business_metrics(
    state: MessagesState, config: RunnableConfig, run_id: str
) -> None:
    """Instrument business-level KPIs for the conversation (graceful degradation).

    Extracted verbatim from ``response_node`` — pure side effects (Prometheus
    metrics from the DB-priced conversation summary); failures never propagate.
    """
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


def _record_plan_pattern_learning(state: MessagesState, run_id: str, turn_type: Any) -> None:
    """Record plan execution success/failure for pattern learning (post-execution).

    Extracted verbatim from ``response_node``. Only records on ACTION turns with an
    execution_plan and no prior semantic_validation entry (avoids double-recording).
    Pure side effects with graceful degradation.
    """
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
        # Only record if: ACTION turn + plan exists + not already recorded by semantic_validator.
        if _is_action_turn(turn_type) and execution_plan and semantic_validation is None:
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


async def _activate_response_skills(
    state: MessagesState,
    config: RunnableConfig,
    run_id: str,
    *,
    last_user_message: str,
    conversation_history: str,
    current_turn_registry: dict[str, Any] | None,
    react_result: dict[str, Any] | None,
) -> _SkillActivationResult:
    """Run the hybrid skill activation (passive L2 injection + ReAct sub-agent).

    Extracted verbatim from ``response_node`` (behavior-preserving). Note the
    ``react_result`` in/out threading: the script-skill runner branch reassigns
    ``react_result`` in the original node scope (read later by the ProactiveFindings
    directive), so it is passed in and returned to reproduce that exact behavior.
    Mutates/returns ``current_turn_registry`` when the runner accumulates registry
    items, exactly as the inline version did.

    ``conversation_history`` is forwarded to the script-skill runner (S5): the
    runner spawns a fresh sub-agent each turn that otherwise only sees the last
    user message, which breaks multi-turn skill dialogues (e.g. the
    skill-generator's clarify → answer → generate flow). Passing the windowed
    history lets the sub-agent resume where the previous turn left off.
    """
    skills_context = ""
    skill_react_response: str | None = None
    _activated_skill_name: str | None = None
    skill_registry_updates: dict[str, Any] | None = None
    if getattr(settings, "skills_enabled", False):
        from src.core.context import active_skills_ctx
        from src.domains.skills.activation import activate_skill
        from src.domains.skills.cache import SkillsCache

        skill_sections: list[str] = []
        activated_names: set[str] = set()
        skill_user_id = config.get("configurable", {}).get("langgraph_user_id")
        active = active_skills_ctx.get()

        # --- Helpers: skill classification for activation strategy ---
        # --- Identify target skill name (planner or always-loaded) ---
        _target_skill_name: str | None = None

        # 1. Planner-activated skill (from plan.metadata)
        # Guard against stale execution_plan from a previous turn: the plan
        # persists in LangGraph state across turns via the checkpoint. A
        # conversational turn (route=response) skips the planner entirely,
        # so any execution_plan we see belongs to the previous action turn
        # and must not re-trigger its skill.
        execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
        qi_route_to = get_qi_attr(state, "route_to", None)
        if qi_route_to == "planner" and execution_plan and execution_plan.metadata:
            plan_skill_name = execution_plan.metadata.get("skill_name")
            if plan_skill_name and (active is None or plan_skill_name in active):
                # D3: do not activate the plan's skill when the plan itself
                # totally failed — otherwise a timed-out action masquerades
                # as a successful skill answer.
                if _plan_execution_failed(state):
                    logger.info(
                        "skill_planner_activation_skipped_plan_failed",
                        run_id=run_id,
                        skill_name=plan_skill_name,
                        reason="execution plan failed — not activating its skill",
                    )
                else:
                    _target_skill_name = plan_skill_name
        elif (
            execution_plan and execution_plan.metadata and execution_plan.metadata.get("skill_name")
        ):
            logger.info(
                "skill_stale_execution_plan_ignored",
                run_id=run_id,
                stale_skill_name=execution_plan.metadata.get("skill_name"),
                route_to=qi_route_to,
                reason="execution_plan from previous turn — current turn did not route to planner",
            )

        # 2. Always-loaded skills — passive L2 injection (additive, always)
        for s in SkillsCache.get_always_loaded(skill_user_id):
            if s["name"] not in activated_names and (active is None or s["name"] in active):
                skill_content = activate_skill(s["name"], user_id=skill_user_id)
                if skill_content:
                    skill_sections.append(skill_content)
                    activated_names.add(s["name"])

        # 3. Query analyzer detected skill (covers both planner and response routes)
        if not _target_skill_name:
            qi = state.get("query_intelligence")
            if isinstance(qi, dict):
                _detected = qi.get("detected_skill_name")
            else:
                _detected = getattr(qi, "detected_skill_name", None)
            if _detected and (active is None or _detected in active):
                _target_skill_name = _detected

        # 4. Activate the target skill (unified for planner + response routes)
        #    - Scripts present → runner (LLM orchestrates resources + scripts)
        #    - Resources only (no scripts) → load in Python, inject with L2
        #    - Neither → passive L2 injection only
        if _target_skill_name and _target_skill_name not in activated_names:
            if _skill_needs_runner(_target_skill_name, skill_user_id):
                # Has scripts → ReactSubAgentRunner
                _activated_skill_name = _target_skill_name
            else:
                # L2 passive injection
                skill_content = activate_skill(_target_skill_name, user_id=skill_user_id)
                if skill_content:
                    # If resources exist (no scripts), load them in Python.
                    # Offload the blocking file reads off the event loop (CA-4).
                    if _skill_has_resources_only(_target_skill_name, skill_user_id):
                        resources_content = await asyncio.to_thread(
                            _load_all_skill_resources, _target_skill_name, skill_user_id
                        )
                        if resources_content:
                            skill_content += "\n\n" + resources_content
                            logger.info(
                                "skill_resources_loaded_inline",
                                run_id=run_id,
                                skill_name=_target_skill_name,
                            )
                    skill_sections.append(skill_content)
                    activated_names.add(_target_skill_name)
                    _activated_skill_name = _target_skill_name

        # --- Run ReAct agent only when target skill needs it ---
        # Skip the runner when the deterministic plan has already produced
        # a SKILL_APP widget for this skill (B1 hybrid optimisation — avoids
        # a redundant LLM reformulation around an already-final frame).
        _needs_runner = bool(
            _activated_skill_name
            and _skill_needs_runner(_activated_skill_name, skill_user_id)
            and not _plan_already_produced_skill_app(state, _activated_skill_name)
        )
        if (
            _activated_skill_name
            and not _needs_runner
            and _skill_needs_runner(_activated_skill_name, skill_user_id)
        ):
            logger.info(
                "skill_runner_skipped_plan_already_produced",
                run_id=run_id,
                skill_name=_activated_skill_name,
                msg="Plan deterministic produced SKILL_APP — skipping runner",
            )
        if _needs_runner:
            from src.core.constants import SKILLS_REACT_RECURSION_LIMIT
            from src.domains.agents.tools.react_runner import ReactSubAgentRunner
            from src.domains.agents.tools.react_tool_wrapper import (
                ReactToolWrapper,
            )
            from src.domains.skills.tools import skills_tools

            try:
                runner = ReactSubAgentRunner(
                    llm_type="mcp_react_agent",
                    prompt_name="skill_react_agent_prompt",
                )

                configurable = config.get("configurable", {})
                _user_lang = configurable.get("user_language", "fr")
                # ADR-137 follow-up: the sub-agent cannot resolve a position on
                # its own (empty bypass plan, no location tool) — feed it the
                # canonical resolution so it never invents one ("ma position").
                from src.domains.agents.services.skill_location_context import (
                    resolve_user_location_for_prompt,
                )

                _user_location = await resolve_user_location_for_prompt(
                    config, last_user_message, _user_lang
                )

                # Build task: direct activation with optional collected data
                # (from plan_executor / SkillBypassStrategy if they ran)
                _agent_data = ""
                _raw_agent_results = state.get(STATE_KEY_AGENT_RESULTS, {})
                if _raw_agent_results:
                    _data_summary = format_agent_results_for_prompt(
                        _raw_agent_results,
                        current_turn_id=state.get("current_turn_id"),
                        user_timezone=config.get("configurable", {}).get("user_timezone", "UTC"),
                    )
                    if _data_summary:
                        _agent_data = (
                            f"\n\n<collected_data>\n{_data_summary}\n"
                            f"</collected_data>\n"
                            f"Use this data to generate your response."
                        )
                # S5: forward the windowed history so a fresh runner sub-agent
                # can resume a multi-turn skill dialogue (clarify → answer →
                # generate). Harmless for one-shot skills (extra context only).
                _history_block = ""
                if conversation_history and conversation_history.strip():
                    _history_block = (
                        f"\n\n<conversation_history>\n{conversation_history}\n"
                        "</conversation_history>\n"
                        "If the skill runs a multi-step dialogue, use this history "
                        "to resume it (e.g. treat the latest user message as the "
                        "answer to a question you asked earlier)."
                    )
                _task = (
                    f"Activate skill '{_activated_skill_name}' and follow "
                    f"its instructions to respond to: {last_user_message}"
                    f"{_history_block}{_agent_data}"
                )
                _catalog_for_prompt = (
                    f"<available_skills><skill><name>"
                    f"{_activated_skill_name}"
                    f"</name></skill></available_skills>"
                )

                # Lightweight ToolRuntime-like object for config propagation
                from types import SimpleNamespace

                from src.domains.agents.registry.agent_registry import (
                    get_global_registry,
                )

                _skill_parent = SimpleNamespace(
                    config={
                        "configurable": {
                            "user_id": configurable.get("langgraph_user_id", ""),
                            "thread_id": configurable.get("thread_id", ""),
                            "user_timezone": configurable.get("user_timezone", "UTC"),
                            "user_language": _user_lang,
                        },
                        "callbacks": config.get("callbacks"),
                        "metadata": config.get("metadata", {}),
                    },
                    store=get_global_registry().get_store(),
                )

                # Wrap skills_tools so ReactSubAgentRunner can collect
                # registry_updates (frames/images) via _accumulated_registry.
                # Without wrapping, rich skill outputs never reach the frontend.
                _wrapped_skills_tools = [ReactToolWrapper(original_tool=t) for t in skills_tools]

                _runner_result = await runner.run(
                    task=_task,
                    tools=_wrapped_skills_tools,
                    prompt_vars={
                        "skills_catalog": _catalog_for_prompt,
                        "user_language": _user_lang,
                        "user_location": _user_location,
                    },
                    parent_runtime=_skill_parent,
                    thread_prefix="skill_react",
                    recursion_limit=SKILLS_REACT_RECURSION_LIMIT,
                    display_name="Skill Activation",
                )

                if _runner_result.iteration_count > 0 and _runner_result.final_message:
                    skill_react_response = _runner_result.final_message
                    # Normalize onto the ONE shape `react_result` carries
                    # everywhere else — the ``react_agent_result`` state
                    # contract (MessagesState: dict | None). The runner returns
                    # a `ReactSubAgentResult` dataclass; assigning it raw made
                    # two incompatible shapes travel under one `Any`-typed name,
                    # and `_build_response_system_prompt` — which reads
                    # `react_result.get("final_message")` — crashed with
                    # AttributeError on run ``117ce96f`` (2026-07-21), taking
                    # the whole turn down to a 98-character fallback.
                    react_result = {
                        "final_message": _runner_result.final_message,
                        "iteration_count": _runner_result.iteration_count,
                        "mode": "react",
                    }
                    logger.info(
                        "skill_react_agent_activated",
                        run_id=run_id,
                        skill_name=_activated_skill_name,
                        iterations=_runner_result.iteration_count,
                        response_length=len(skill_react_response),
                        duration_ms=_runner_result.duration_ms,
                    )

                    # Propagate registry items accumulated by the wrappers:
                    # current_turn_registry (local) feeds the rendering and
                    # SSE below; the cross-turn persistence goes through the
                    # returned state_update ("registry" has the merge_registry
                    # reducer — returning only the NEW items is equivalent to
                    # the historical in-place update, but persisted by
                    # contract instead of by shared-reference side effect).
                    if _runner_result.accumulated_registry:
                        if current_turn_registry is None:
                            current_turn_registry = {}
                        current_turn_registry.update(_runner_result.accumulated_registry)
                        skill_registry_updates = _runner_result.accumulated_registry
                        logger.info(
                            "skill_react_registry_propagated",
                            run_id=run_id,
                            skill_name=_activated_skill_name,
                            registry_items=len(_runner_result.accumulated_registry),
                        )
            except Exception as exc:
                logger.warning(
                    "skill_react_agent_error",
                    run_id=run_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                # Graceful degradation: fall back to passive L2 injection
                skill_content = activate_skill(_activated_skill_name, user_id=skill_user_id)
                if skill_content:
                    skill_sections.append(skill_content)

        if skill_sections:
            skills_context = "\n\n".join(skill_sections)
    return _SkillActivationResult(
        skills_context=skills_context,
        skill_react_response=skill_react_response,
        activated_skill_name=_activated_skill_name,
        skill_registry_updates=skill_registry_updates,
        current_turn_registry=current_turn_registry,
        react_result=react_result,
    )


def _render_response_html(
    *,
    final_content: str,
    current_turn_registry: dict[str, Any] | None,
    resolved_context_for_html: dict[str, Any] | None,
    user_display_mode: str,
    user_viewport: str,
    user_language: str,
    user_timezone: str,
    run_id: str,
) -> str:
    """Inject structured HTML after the LLM response and return the new content.

    Extracted verbatim from ``response_node``. Two paths: interactive widgets
    (SKILL_APP/MCP_APP/DRAFT — always injected) and data cards (cards mode only).
    Read-only on the registry; only the (possibly appended) content is returned.

    Widget sentinels are host-owned: any the model authored itself is stripped
    first, so the injection below is the single source of them. Without this the
    answer carried the same ``data-registry-id`` twice (two iframes really
    mounted), and sometimes a lone sentinel pointing at a STALE id the backend
    never injected — see ``display/sentinel_filter``.
    """
    stripped_content, llm_sentinels = strip_widget_sentinels(final_content)
    if llm_sentinels:
        final_content = stripped_content
        widget_sentinels_stripped_total.labels(source="response_llm").inc(llm_sentinels)
        logger.info(
            "llm_authored_widget_sentinels_stripped",
            run_id=run_id,
            count=llm_sentinels,
        )

    html_content = ""
    source = ""

    # ---------- Path 1: interactive widgets (always on) ----------
    widget_html = ""
    if current_turn_registry:
        try:
            widget_html = generate_html_for_interactive_widgets(
                data_registry=current_turn_registry,
                user_viewport=user_viewport,
                user_language=user_language,
                user_timezone=user_timezone,
            )
        except (ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
            logger.warning(
                "interactive_widgets_rendering_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )
    if widget_html:
        final_content = final_content + "\n\n" + widget_html
        logger.info(
            "interactive_widgets_injected_post_llm",
            run_id=run_id,
            html_length=len(widget_html),
            user_display_mode=user_display_mode,
        )

    # ---------- Path 2: data cards (cards mode only) ----------
    # In ``cards`` mode, render data-oriented items. Interactive widgets
    # are filtered out here to avoid double-rendering (path 1 already did).
    if user_display_mode != RESPONSE_DISPLAY_MODE_CARDS:
        logger.info(
            "html_cards_skipped_user_disabled",
            run_id=run_id,
            user_display_mode=user_display_mode,
        )

    elif not current_turn_registry and not resolved_context_for_html:
        pass  # No data to render

    else:
        try:
            if current_turn_registry:
                # Exclude interactive widgets — already rendered in path 1.
                from src.domains.agents.data_registry.models import (
                    INTERACTIVE_WIDGET_TYPES,
                )

                data_only_registry = _filter_registry_by_types(
                    current_turn_registry,
                    INTERACTIVE_WIDGET_TYPES,
                    include=False,
                )
                if data_only_registry:
                    html_content = generate_html_for_registry(
                        data_registry=data_only_registry,
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
    return final_content


def _apply_relevant_ids_filtering(
    *,
    final_content: str,
    original_content: str,
    current_turn_registry: dict[str, Any] | None,
    state: MessagesState,
    result_domains: set[str],
    last_user_message: str,
    run_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Parse ``<relevant_ids>`` from the LLM output and filter the turn registry.

    Extracted verbatim from ``response_node``. Returns the (stripped) content and
    the filtered registry; protected items (initiative/MCP_APP/SKILL_APP/DRAFT) are
    always preserved, and filtering is skipped for domains where it is meaningless.
    """
    # =====================================================================
    # INTELLIGENT FILTERING: Parse relevant_ids and filter registry
    # =====================================================================
    # The LLM may have returned <relevant_ids>...</relevant_ids> to filter results
    # based on user criteria that couldn't be filtered by the API
    try:
        relevant_ids, final_content = parse_relevant_ids_from_response(final_content)

        # ADR-062: Collect initiative registry IDs to protect from filtering.
        # Initiative items were proactively selected by the initiative LLM
        # and should not be eliminated by the response LLM's filtering.
        initiative_protected_ids: set[str] = set()
        for ir in state.get("initiative_results") or []:
            if isinstance(ir, dict):
                initiative_protected_ids.update(ir.get("registry_ids") or [])

        # Extract items that must NEVER be filtered out:
        # - Initiative items (proactively selected by initiative LLM)
        # - MCP App items (interactive widgets — not search results)
        # - Draft items (HITL confirmation flow)
        # Items may be dicts (model_dump) or RegistryItem Pydantic objects.
        _UNFILTERABLE_TYPES = {"MCP_APP", "SKILL_APP", "DRAFT"}
        protected_items: dict[str, Any] = {}
        for k, v in (current_turn_registry or {}).items():
            if k in initiative_protected_ids:
                protected_items[k] = v
            elif isinstance(v, dict) and v.get("type") in _UNFILTERABLE_TYPES:
                protected_items[k] = v
            elif (
                hasattr(v, "type")
                and hasattr(v.type, "value")
                and v.type.value in _UNFILTERABLE_TYPES
            ):
                protected_items[k] = v

        if relevant_ids:
            # Filter the registry to only include relevant items
            original_registry_count = len(current_turn_registry) if current_turn_registry else 0

            current_turn_registry = filter_registry_by_relevant_ids(
                current_turn_registry, relevant_ids
            )

            # Re-inject protected items that were filtered out
            if protected_items:
                restored_count = 0
                for k, v in protected_items.items():
                    if k not in current_turn_registry:
                        current_turn_registry[k] = v
                        restored_count += 1
                if restored_count:
                    logger.info(
                        "protected_items_restored_after_filtering",
                        run_id=run_id,
                        restored_count=restored_count,
                        restored_ids=list(protected_items.keys()),
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
            if "<relevant_ids>" in original_content.lower():
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
                    # Preserve protected items even when LLM returns empty
                    current_turn_registry = protected_items
                    logger.info(
                        "intelligent_filtering_no_matches",
                        run_id=run_id,
                        protected_preserved=len(protected_items),
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
    return final_content, current_turn_registry


def _build_response_system_prompt(
    *,
    state: MessagesState,
    run_id: str,
    user_timezone: str,
    user_language: str,
    user_viewport: str,
    user_display_mode: str,
    user_psyche_enabled: bool,
    personality_instruction: str | None,
    conversation_history: str,
    psychological_profile: Any,
    knowledge_context: str,
    rag_context: Any,
    user_query_for_prompt: str | None,
    last_user_message: str,
    enriched_query: str | None,
    data_for_filtering: str,
    resolved_references: dict[str, str] | None,
    anticipated_needs: Any,
    skills_context: str,
    app_knowledge_context: str,
    journal_context: str,
    psyche_context: str,
    user_model_block: Any,
    react_result: dict[str, Any] | None,
    recent_entities: str = "",
    peer_context: str = "",
) -> str:
    """Assemble the response LLM system prompt from all injected context.

    Extracted verbatim from ``response_node``: base prompt (get_response_prompt)
    plus the user-model portrait, initiative suggestion, ReAct proactive-findings,
    HTML-directive and psyche self-report instruction, in the same order/gating.
    """
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
        psyche_context=psyche_context,  # Psyche Engine expression profile
        recent_entities=recent_entities,  # Grounding when this turn produced no data
        peer_context=peer_context,  # Local CRM facts about a named connected user
    )
    # ADR-079 commit 3: ambient diffusion of the user-model portrait.
    # Appended after the base prompt so it is read alongside (not in place
    # of) the factual psychological profile.
    if user_model_block:
        base_system_prompt += "\n\n" + user_model_block
    # ADR-062 / ADR-070: initiative suggestion + ReAct proactive-findings injection.
    from src.core.constants import (
        STATE_KEY_INITIATIVE_RESULTS,
        STATE_KEY_INITIATIVE_SUGGESTION,
    )

    initiative_suggestion = state.get(STATE_KEY_INITIATIVE_SUGGESTION)
    if initiative_suggestion:
        base_system_prompt += "\n\n" + load_prompt("initiative_suggestion_directive").format(
            initiative_suggestion=initiative_suggestion
        )
    # ADR-070: in ReAct mode the agent's answer is delivered as authoritative
    # (the response LLM is told not to re-derive). When the Initiative node
    # gathered proactive read-only findings AFTER that answer was written, they
    # would otherwise surface only as orphan cards. The findings are already in
    # the prompt via `data_for_filtering`; this directive invites weaving them in.
    # Gated to ReAct + Initiative-acted to keep zero impact elsewhere (pipeline
    # already synthesises from the registry directly).
    _initiative_results = state.get(STATE_KEY_INITIATIVE_RESULTS) or []
    _initiative_acted = any(r.get("actions_executed", 0) > 0 for r in _initiative_results)
    if (
        state.get("execution_mode") == "react"
        and _initiative_acted
        and react_result
        and react_result.get("final_message")
    ):
        base_system_prompt += "\n\n" + load_prompt("proactive_findings_directive")
    # DISPLAY MODE: ``user_display_mode`` was resolved once earlier (history
    # neutralization gate); reused here for the HTML directive / cards logic.
    # Resolve the current turn's routing target via the canonical helper
    # (handles both the object and serialized-dict forms of query
    # intelligence). This is the same source the voice path uses to decide
    # conversation vs action, so the display gate can never desync from it.
    # Rich HTML is only injected for planner-routed (tool/data) turns —
    # see _should_inject_html_directive for the rationale.
    route_to = get_qi_attr(state, "route_to", None)
    # HTML mode: Inject rich HTML formatting directive into prompt.
    # Placed BEFORE FINAL REMINDER for maximum authority (same pattern as
    # psyche). Gated to action turns: a conversational reply is read aloud
    # verbatim by the TTS, so emitting HTML would make it speak tags/CSS.
    if _should_inject_html_directive(user_display_mode, route_to):
        _html_directive = str(load_prompt("html_response_directive"))
        _final_reminder = "### FINAL REMINDER ###"
        if _final_reminder in base_system_prompt:
            base_system_prompt = base_system_prompt.replace(
                _final_reminder,
                _html_directive + "\n\n" + _final_reminder,
            )
        else:
            base_system_prompt += "\n\n" + _html_directive
        logger.info(
            "html_response_directive_injected",
            run_id=run_id,
            display_mode=user_display_mode,
            route_to=route_to,
        )
    # PSYCHE ENGINE: Inject self-report instruction (before FINAL REMINDER)
    if settings.psyche_enabled and user_psyche_enabled and psyche_context:
        _psyche_instruction = str(load_prompt("psyche_self_report_instruction"))
        _final_reminder = "### FINAL REMINDER ###"
        if _final_reminder in base_system_prompt:
            base_system_prompt = base_system_prompt.replace(
                _final_reminder,
                _psyche_instruction + "\n\n" + _final_reminder,
            )
        else:
            base_system_prompt += "\n\n" + _psyche_instruction
    logger.debug(
        "response_node_prompt_loaded",
        run_id=run_id,
        viewport=user_viewport,
        has_filtering_data=bool(data_for_filtering),
        has_initiative_suggestion=initiative_suggestion is not None,
        user_query_for_prompt=user_query_for_prompt[:80] if user_query_for_prompt else "",
        last_user_message=last_user_message[:80] if last_user_message else "",
        used_original_query=user_query_for_prompt != last_user_message,
    )
    return base_system_prompt


def _launch_knowledge_enrichment(
    state: MessagesState, config: RunnableConfig, run_id: str, user_language: str
) -> tuple[Any, dict[str, Any] | None]:
    """Launch the Brave-search knowledge enrichment task (non-blocking).

    Extracted verbatim from ``response_node``. Returns (task, debug_result): the
    asyncio task is None when enrichment is skipped (feature off, no QI/deps/user,
    skip-domain, no keywords), in which case debug_result carries the skip reason.
    """
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
    return enrichment_task, knowledge_enrichment_result


async def _await_knowledge_enrichment(
    enrichment_task: Any,
    knowledge_enrichment_result: dict[str, Any] | None,
    run_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Await the Brave-search enrichment task and return (context, debug_result).

    Extracted verbatim from ``response_node``: timeout- and error-guarded; on
    success returns the prompt context and a debug payload, otherwise preserves
    the incoming ``knowledge_enrichment_result`` (skip reasons) or records an error.
    """
    knowledge_context = ""
    # Note: knowledge_enrichment_result is already initialized above with skip_reason if applicable
    if enrichment_task:
        try:
            context_obj = await asyncio.wait_for(
                enrichment_task,
                timeout=settings.brave_search_enrichment_timeout_seconds,
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
                "timeout_seconds": settings.brave_search_enrichment_timeout_seconds,
            }
            logger.warning(
                "knowledge_enrichment_timeout",
                run_id=run_id,
                timeout=settings.brave_search_enrichment_timeout_seconds,
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
    return knowledge_context, knowledge_enrichment_result


async def _resolve_response_context_summary(
    state: MessagesState,
    config: RunnableConfig,
    run_id: str,
    *,
    resolved_context: dict[str, Any] | None,
    current_turn_id: Any,
    current_turn_registry: dict[str, Any] | None,
    override_action: str | None,
    user_timezone: str,
    user_language: str,
    user_viewport: str,
) -> tuple[str, dict[str, Any] | None, Any, str | None]:
    """Resolve the agent-results summary shown to the LLM (turn-type aware).

    Extracted verbatim from ``response_node``: formats agent results per turn type
    (reference/conversational/action), executes a confirmed draft and folds its
    result in, and prepends plan-rejection / planner-error explanations. Returns
    (summary, resolved_context_for_html, turn_type, plan_rejection_reason).
    """
    # === CONTEXT RESOLUTION: Determine which results to show ===
    turn_type = state.get(STATE_KEY_TURN_TYPE, TURN_TYPE_ACTION)
    # Note: resolved_context and current_turn_id already retrieved above (lines 2103-2104)
    # V3 HTML: Track resolved_context for HTML injection post-LLM
    # Used when REFERENCE turn uses resolved_context directly (no current_turn_registry)
    resolved_context_for_html: dict[str, Any] | None = None
    # Format agent results based on turn type.
    # NOTE: use the helper (tolerant to REFERENCE_PURE/REFERENCE_ACTION emitted
    # by QueryIntelligence) so resolved_context is correctly used even when
    # the state carries the composite UPPERCASE variant.
    if _is_reference_turn(turn_type) and resolved_context and resolved_context.get("items"):
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
    return agent_results_summary, resolved_context_for_html, turn_type, plan_rejection_reason


def _build_response_chain(
    *,
    base_system_prompt: str,
    agent_results_summary: str,
    skills_context: str,
    plan_rejection_reason: str | None,
    state: MessagesState,
    user_language: str,
    llm: Any,
) -> Any:
    """Build the response ChatPromptTemplate + LLM chain (dynamic system blocks).

    Extracted verbatim from ``response_node``: assembles only non-empty system
    blocks (base prompt, skill contract, rejection/cancel directive, authoritative
    data), a MessagesPlaceholder and a trailing language-reinforcement human message,
    then returns ``prompt | llm``.
    """
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
    # PLAN BLOCKED BY VALIDATION: the validator refused steps and the turn ran
    # on anyway, so without this the model explains an empty result it knows
    # nothing about — and invents a diagnosis (2026-07-30: "aucun service de
    # contacts ni d'agenda n'est configuré", said three times, all false).
    # Never overrides an explicit user rejection/cancellation above: those are
    # decisions the user made, this is a failure they must hear about.
    # The verdict is weighed against what the turn actually ran: a rejected
    # plan is executed unchanged, so a capability that produced data was not
    # blocked — reporting it as such is the same lie in the other direction
    # (2026-07-31: ten emails in the registry, "retrieval was blocked").
    if not rejection_override:
        blocked_capabilities = format_plan_blockers(
            summarize_plan_blockers(
                state.get(STATE_KEY_VALIDATION_RESULT),
                executed_tool_names(
                    state.get(STATE_KEY_EXECUTION_PLAN),
                    state.get(STATE_KEY_COMPLETED_STEPS),
                ),
            )
        )
        if blocked_capabilities:
            rejection_override = load_prompt(
                "response_directive_plan_blocked",
                version=settings.response_prompt_version,
            ).format(user_language=user_language, blocked_capabilities=blocked_capabilities)

    # Build ChatPromptTemplate dynamically — only include non-empty system blocks.
    # Anthropic (and potentially other providers) reject empty system content blocks.
    # By constructing the template after knowing the values, we avoid sending
    # ("system", "") which causes 400 errors with strict providers.
    safe_rejection_override = escape_braces(rejection_override)
    safe_agent_results = escape_braces(agent_results_summary)
    safe_skills_context = escape_braces(skills_context) if skills_context else ""
    # base_system_prompt embeds the conversation history (get_response_prompt
    # conversation_history=...), which can contain literal curly braces from
    # the user or assistant (LaTeX like \frac{d}{2}, MCP/HTML payloads).
    # ChatPromptTemplate re-processes each system string as an f-string, so
    # a stray "{2}" raised ValueError ("Invalid variable name '2'") and
    # crashed every follow-up turn. Escape it like the other injected blocks
    # (the prompt is already fully rendered — no template vars remain; the
    # actual messages flow through MessagesPlaceholder, not this string).
    safe_base_system_prompt = escape_braces(base_system_prompt)
    prompt_messages: list[Any] = [("system", safe_base_system_prompt)]
    # Skill instructions are injected as a DEDICATED high-priority system
    # message placed right after the base prompt. Rationale: when a skill
    # is active, its ``references/*.md`` content (format rules, business
    # logic, examples, constraints) defines the authoritative behavior for
    # the turn. Placing it as a separate system block — and declaring it
    # explicitly as overriding the generic <ResponseGuidelines> — mitigates
    # the primacy-effect problem where generic guidelines placed early in
    # ``base_system_prompt`` would otherwise outweigh the skill content
    # that used to be diluted deep inside the template.
    if safe_skills_context:
        # Versioned template at ``prompts/v1/skill_contract_prefix_prompt.txt`` —
        # keeps the "primacy effect" wrapper under source control and load_prompt
        # LRU cache (CLAUDE.md §16). Template has a single ``{skills_context}``
        # placeholder substituted by str.format(). ``safe_skills_context`` is
        # already escape_braces()'d, so downstream ChatPromptTemplate will see
        # it as literal text (no double-processing).
        skill_contract_template = load_prompt("skill_contract_prefix_prompt")
        skill_contract_prefix = skill_contract_template.format(skills_context=safe_skills_context)
        prompt_messages.append(("system", skill_contract_prefix))
    if safe_rejection_override:
        prompt_messages.append(("system", safe_rejection_override))
    if safe_agent_results:
        # Prefix data with authority reminder to override contradictory history
        data_prefix = (
            "CURRENT TURN DATA (AUTHORITATIVE — overrides any contradictory "
            "information from conversation history above):\n\n"
        )
        prompt_messages.append(("system", data_prefix + safe_agent_results))
    prompt_messages.append(MessagesPlaceholder(variable_name="messages"))
    # Language reinforcement: inject a final human message AFTER conversation history.
    # When the user switches language mid-conversation, the history (in the previous
    # language) + personality prompt can overpower the system prompt's language directive.
    # Placing this reminder as the last message before generation ensures compliance.
    # NOTE: Uses "human" role because Anthropic API rejects non-consecutive system messages.
    from src.core.i18n_types import LANGUAGE_NAMES

    _lang_name = LANGUAGE_NAMES.get(user_language, user_language)
    prompt_messages.append(
        (
            "human",
            f"[INSTRUCTION] Respond ENTIRELY in {_lang_name}. "
            f"The conversation above may be in another language — "
            f"ignore that and write your response in {_lang_name} only.",
        )
    )
    prompt = ChatPromptTemplate.from_messages(prompt_messages)
    # Create chain
    chain = prompt | llm
    return chain


async def _prepare_conversational_messages(
    state: MessagesState,
    run_id: str,
    *,
    neutralize_history_formatting: bool,
    plan_rejection_reason: str | None,
    current_turn_attachments: Any,
    last_user_message: str,
    has_vision_content: bool,
) -> list[Any]:
    """Window + filter the message history for the synthesis LLM and inject vision.

    Extracted verbatim from ``response_node``: drops the current-turn answer, windows
    and filters for LLM context, applies the rejected-plan anti-hallucination filter,
    and substitutes the last HumanMessage with multimodal content when attachments
    are present. Operates on a local copy only (never the graph state).
    """
    # Phase: Performance Optimization - Message Windowing
    # Apply windowing BEFORE filtering to reduce token count
    # Response needs rich context for creative synthesis (20 turns default)
    from src.domains.agents.utils.message_windowing import get_response_windowed_messages

    # Drop current-turn assistant output (ReAct passthrough leaves its final answer in
    # state["messages"]) so the synthesis LLM's message array ends on the user query,
    # not on a complete answer to it. See drop_current_turn_responses for the rationale.
    windowed_messages = get_response_windowed_messages(
        drop_current_turn_responses(state[STATE_KEY_MESSAGES])
    )
    # Filter messages for LLM context
    # Keeps: HumanMessage + ToolMessage (JSON) + AIMessage without HTML
    # Excludes: AIMessage with HTML (lia-card) to prevent LLM reformulating as Markdown
    # In "html" display mode, also neutralizes the style of prior assistant answers
    # (see neutralize_history_formatting above) so accumulated Markdown does not
    # override the HTML directive over multi-turn conversations.
    # Uses centralized filter from utils/message_filters.py
    conversational_messages = filter_for_llm_context(
        windowed_messages, neutralize_formatting=neutralize_history_formatting
    )
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
            build_vision_message_async,
        )

        # Extract clean user text (without annotation hint)
        clean_user_text = last_user_message
        # Remove the annotation hint using unique marker prefix
        marker_prefix = f"\n\n{ATTACHMENT_HINT_MARKER}"
        if clean_user_text and marker_prefix in clean_user_text:
            clean_user_text = clean_user_text[: clean_user_text.rfind(marker_prefix)]
        # Offload base64 image loading off the event loop (CA-4).
        multimodal_msg = await build_vision_message_async(
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
    return conversational_messages


def _detect_response_result_domains(
    *,
    turn_type: Any,
    agent_results_summary: str,
    current_turn_registry: dict[str, Any] | None,
    agent_results_raw: dict[str, Any],
    run_id: str,
) -> set[str]:
    """Detect the current turn's result domains (and log mono/multi-domain metrics).

    Extracted verbatim from ``response_node``: derives the domain set from the
    filtered current-turn registry, increments the Prometheus domain-detection /
    multi-domain-composition counters, and emits the diagnostic log.
    """
    # Detect if this is a conversational turn based on turn_type from context resolution.
    # Helpers tolerate the UPPERCASE composite values (REFERENCE_PURE / REFERENCE_ACTION)
    # emitted by QueryIntelligence in addition to the lowercase constants.
    is_reference = _is_reference_turn(turn_type)
    is_conversational_turn = (
        _is_conversational_turn(turn_type)
        or (agent_results_summary in NO_EXTERNAL_AGENT_MESSAGES and not is_reference)
        or (not agent_results_summary.strip() and not is_reference)
    )
    # Detect mono vs multi-domain for metrics and logging
    # BugFix 2025-12-19: Use current_turn_registry (filtered) instead of full_registry
    result_domains = _detect_result_domains_from_registry(current_turn_registry)
    is_mono_domain = len(result_domains) == 1 and "other" not in result_domains
    # Prometheus: domain detection + multi-domain composition (dashboard 15)
    with suppress(Exception):
        from src.infrastructure.observability.metrics_agents import (
            domain_detection_total,
            multi_domain_composition_total,
        )

        for _d in result_domains:
            domain_detection_total.labels(domain=_d, detected=str(not is_mono_domain).lower()).inc()
        if len(result_domains) >= 2:
            multi_domain_composition_total.labels(
                composition_mode="sequential",
                domain_count=str(len(result_domains)),
            ).inc()
    logger.info(
        "response_node_domain_detection",
        run_id=run_id,
        agent_results_summary=agent_results_summary[:LOGGING_SUMMARY_PREVIEW_CHARS],
        is_conversational_turn=is_conversational_turn,
        result_domains=list(result_domains),
        is_mono_domain=is_mono_domain,
        agent_results_keys=list(agent_results_raw.keys()),
    )
    return result_domains


def _normalize_agent_results(state: MessagesState, run_id: str) -> dict[str, Any]:
    """Return agent_results, falling back to the semantic tool_results shape if empty.

    Extracted verbatim from ``response_node``: the legacy task_orchestrator path
    populates agent_results; the semantic tool_executor path populates tool_results,
    which is coerced here into the ``{turn}:semantic_tools`` agent-results shape.
    """
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
    return agent_results_raw


def _build_data_for_filtering(
    current_turn_registry: dict[str, Any] | None, user_language: str, run_id: str
) -> str:
    """Generate the item-ID + filterable-fields payload used for semantic filtering.

    Extracted verbatim from ``response_node`` (empty when no current-turn registry;
    error-guarded with a localized fallback marker).
    """
    # Generate enriched data for intelligent filtering
    # This includes item IDs and filterable fields (addresses, locations, etc.)
    data_for_filtering = ""
    if current_turn_registry:
        try:
            data_for_filtering = generate_data_for_filtering(current_turn_registry, user_language)
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
            data_for_filtering = DATA_FILTERING_GENERATION_ERROR_MARKER
    return data_for_filtering


def _extract_qi_response_hints(
    state: MessagesState, run_id: str
) -> tuple[dict[str, str] | None, str | None, Any]:
    """Extract resolved references, enriched query and anticipated needs from QI.

    Extracted verbatim from ``response_node``. Returns
    (resolved_references, enriched_query, anticipated_needs).
    """
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
    return resolved_references, enriched_query, anticipated_needs


def _build_conversation_history(
    state: MessagesState, run_id: str, neutralize_history_formatting: bool
) -> tuple[str, str, str | None]:
    """Window + filter the history and format it for prompt injection.

    Extracted verbatim from ``response_node``. Returns (conversation_history,
    last_user_message, user_query_for_prompt); the current query is excluded from
    the formatted history (it is passed separately via {user_query}).
    """
    # Format conversation history for prompt injection
    # Architecture (2025-12-07): Uses explicit placeholder {conversation_history} in prompt
    from src.domains.agents.utils.conversation_context import format_conversation_history
    from src.domains.agents.utils.message_windowing import get_response_windowed_messages

    # Drop current-turn assistant output before windowing: in ReAct passthrough the
    # agent's final answer lives in state["messages"], and leaving it in the history
    # makes the synthesis LLM treat the query as already answered (see
    # drop_current_turn_responses). The answer reaches the LLM via the AUTHORITATIVE
    # agent_results block instead. No-op on the planner path (no current-turn AI yet).
    windowed_for_history = get_response_windowed_messages(
        drop_current_turn_responses(state[STATE_KEY_MESSAGES])
    )
    # Use filter_for_llm_context: keeps HumanMessage + ToolMessage (JSON) + simple AIMessage
    # Excludes AIMessage with HTML (lia-card) to prevent LLM reformulating as Markdown
    llm_context_for_history = filter_for_llm_context(
        windowed_for_history, neutralize_formatting=neutralize_history_formatting
    )
    # =====================================================================
    # INTELLIGENT FILTERING: Extract user query for semantic filtering
    # =====================================================================
    # Extract last user message for filtering context (also used by memory injection)
    last_user_message = ""
    for msg in reversed(state[STATE_KEY_MESSAGES]):
        if isinstance(msg, HumanMessage) and msg.content:
            last_user_message = msg.text
            break

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
    return conversation_history, last_user_message, user_query_for_prompt


def _apply_react_passthrough(state: MessagesState, run_id: str) -> tuple[Any, bool]:
    """Inject the ReAct agent's final answer into agent_results (in place).

    Extracted verbatim from ``response_node`` (ADR-070): merges the ReAct final
    message under ``{turn}:react_agent`` so all post-processing applies. Mutates
    ``state[agent_results]`` and returns (react_result, react_passthrough_merged);
    the merged agent_results is also persisted by contract via the state_update.
    """
    _react_passthrough_merged = False  # F5: gate for the explicit state return
    react_result = state.get("react_agent_result")
    if react_result and react_result.get("final_message"):
        # The ReAct answer is handed to the response LLM as AUTHORITATIVE
        # (``agent_results_summary``). A sentinel the agent copied from history
        # would therefore be reproduced verbatim in the final answer, on top of
        # the deterministic injection. Sentinels are host-owned: drop them here,
        # at the point the message becomes authoritative.
        react_message, _react_sentinels = strip_widget_sentinels(react_result["final_message"])
        if _react_sentinels:
            widget_sentinels_stripped_total.labels(source="agent_results").inc(_react_sentinels)
            logger.info(
                "react_answer_widget_sentinels_stripped",
                run_id=run_id,
                count=_react_sentinels,
            )
        current_turn = state.get(STATE_KEY_CURRENT_TURN_ID, 0)
        # Inject as agent_results with registry_updates so that
        # _filter_registry_by_current_turn() can find the current turn's
        # registry items and generate_data_for_filtering() produces data
        # for HTML cards / display mode.
        # current_turn_registry ONLY — never fall back to the cross-turn
        # `registry`: injecting it here would tag EVERY historical item as
        # a registry_update of the current turn, bypassing the turn filter
        # and re-displaying previous turns' data. react_execute_tools and
        # the initiative node always write current_turn_registry alongside
        # registry, so a tool-less ReAct turn legitimately yields {}.
        current_registry = state.get("current_turn_registry") or {}
        # Merge (not gate): the Initiative node may have written {turn}:initiative
        # before us on the ReAct nominal path. A plain "if not agent_results" guard
        # would drop the ReAct answer; merging preserves both (ADR-070).
        # NOTE (F5): the in-place assignment feeds the 6 downstream readers
        # of this node; cross-turn persistence additionally goes through the
        # returned state_update (see the state_update block) so it holds by
        # contract, not by shared-reference side effect.
        state[STATE_KEY_AGENT_RESULTS] = _merge_react_synthesis_result(
            state.get(STATE_KEY_AGENT_RESULTS),
            react_message,
            current_turn,
            current_registry,
        )
        _react_passthrough_merged = True
        logger.info(
            "response_node_react_passthrough",
            run_id=run_id,
            iterations=react_result.get("iteration_count", 0),
            registry_items=len(current_registry),
            message_preview=react_message[:80] if react_message else "",
        )
    return react_result, _react_passthrough_merged


def _parse_psyche_appraisal(
    final_content: str, user_psyche_enabled: bool, run_id: str
) -> tuple[Any, str]:
    """Parse and strip the psyche self-report tag from the LLM output.

    Extracted verbatim from ``response_node``: must run BEFORE relevant_ids parsing
    (both modify content). Returns (appraisal, stripped_content); on any error the
    content is returned unchanged with a None appraisal.
    """
    psyche_appraisal = None
    if settings.psyche_enabled and user_psyche_enabled:
        try:
            from src.domains.psyche.engine import PsycheEngine as _PsycheEngine

            psyche_appraisal, final_content = _PsycheEngine.parse_psyche_eval(final_content)
            if psyche_appraisal:
                logger.debug(
                    "psyche_eval_parsed",
                    run_id=run_id,
                    valence=psyche_appraisal.valence,
                    arousal=psyche_appraisal.arousal,
                    dominance=psyche_appraisal.dominance,
                    emotion=psyche_appraisal.dominant_emotion,
                    intensity=psyche_appraisal.dominant_intensity,
                    emotions=psyche_appraisal.emotions,
                    quality=psyche_appraisal.quality,
                )
        except Exception as e:
            logger.warning(
                "psyche_eval_parse_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )
    return psyche_appraisal, final_content


def _resolve_turn_preamble(
    state: MessagesState, config: RunnableConfig, run_id: str
) -> tuple[str, str, str, str, bool, Any, bool]:
    """Resolve per-turn display context and detect vision attachments.

    Extracted verbatim from ``response_node``: cleans the stale content-replacement
    signal, resolves timezone/language/viewport/display-mode (and the history
    neutralization gate), and detects image attachments. Returns the seven values
    (timezone, language, viewport, display_mode, neutralize_history_formatting,
    current_turn_attachments, has_vision_content).
    """
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
    # DISPLAY MODE: resolve once, up-front — it gates several style decisions below.
    # In the "html" mode the prompt carries the rich-HTML directive, so the Markdown
    # style precedent that accumulates in the LLM's conversational history must be
    # neutralized: prior assistant answers are rewritten to style-free text via
    # filter_for_llm_context(neutralize_formatting=...) so they cannot bias the model
    # into Markdown over multi-turn conversations. The current turn's content to render
    # (e.g. the ReAct agent's final_message) is left intact — it is the input to
    # reformat, not a style precedent. The "cards" and "markdown" modes keep the
    # historical behaviour (flag stays False) — no regression.
    user_display_mode = config.get("configurable", {}).get(
        "user_display_mode", RESPONSE_DISPLAY_MODE_CARDS
    )
    neutralize_history_formatting = user_display_mode == RESPONSE_DISPLAY_MODE_HTML
    # === VISION LLM SWITCH (evolution F4 — File Attachments) ===
    # Detect if current turn has image attachments → use vision_analysis LLM
    current_turn_attachments = state.get("metadata", {}).get("current_turn_attachments")
    has_vision_content = False
    if current_turn_attachments:
        from src.domains.attachments.models import AttachmentContentType

        has_vision_content = any(
            a["content_type"] == AttachmentContentType.IMAGE for a in current_turn_attachments
        )
    return (
        user_timezone,
        user_language,
        user_viewport,
        user_display_mode,
        neutralize_history_formatting,
        current_turn_attachments,
        has_vision_content,
    )


def _log_response_llm_input(
    run_id: str, agent_results_summary: str, conversational_messages: list[Any]
) -> None:
    """Emit the pre-synthesis debug log describing the exact LLM input."""
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


def _track_vision_llm_metrics(llm: Any, vision_start: float) -> None:
    """Increment the vision-LLM Prometheus counters after a vision synthesis call."""
    from src.infrastructure.observability.metrics_attachments import (
        vision_llm_duration_seconds,
        vision_llm_requests_total,
    )

    vision_model = getattr(llm, "model_name", "unknown")
    vision_llm_requests_total.labels(model=vision_model).inc()
    vision_llm_duration_seconds.labels(model=vision_model).observe(
        time.perf_counter() - vision_start
    )


def _track_response_token_efficiency(result_domains: set[str], enriched_config: Any) -> None:
    """Track the response node token-efficiency ratio, labelled by result domain."""
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


def _prepare_turn_registry(
    state: MessagesState, run_id: str, agent_results_raw: dict[str, Any]
) -> tuple[dict[str, Any], Any, dict[str, Any] | None, dict[str, Any] | None, str | None, Any]:
    """Filter the registry to the current turn and derive override_action / personality.

    Extracted verbatim from ``response_node``. Returns (full_registry, current_turn_id,
    resolved_context, current_turn_registry, override_action, personality_instruction).
    """
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
    return (
        full_registry,
        current_turn_id,
        resolved_context,
        current_turn_registry,
        override_action,
        personality_instruction,
    )


def _response_error_fallback(state: MessagesState, run_id: str, exc: Exception) -> dict[str, Any]:
    """Return the graceful error-fallback state_update for response_node.

    Extracted verbatim from ``response_node``'s except handler: logs the exception,
    increments the graph-exception counter and returns a localized AIMessage error
    (language re-read from state, since user_language may be unbound on early failure).
    """
    # Business logic error handling (fallback message)
    # Note: Basic error metrics/logs already tracked by @track_metrics decorator
    logger.error(
        "response_node_exception",
        run_id=run_id,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        exc_info=True,  # Include stack trace in logs
    )

    graph_exceptions_total.labels(
        node_name="response",
        exception_type=type(exc).__name__,
    ).inc()

    # Fallback: return error message
    # BUG FIX: Use AIMessage (not HumanMessage) for error responses from assistant
    # Re-read the language from state: user_language is assigned inside the
    # try block, so it may be unbound if the exception occurred before it.
    fallback_language = state.get("user_language", settings.default_language)
    error_message = AIMessage(
        content=get_error_fallback_message(type(exc).__name__, language=fallback_language)
    )

    error_state = {STATE_KEY_MESSAGES: [error_message]}
    track_state_updates(state, error_state, "response", run_id)
    return error_state


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
        (
            user_timezone,
            user_language,
            user_viewport,
            user_display_mode,
            neutralize_history_formatting,
            current_turn_attachments,
            has_vision_content,
        ) = _resolve_turn_preamble(state, config, run_id)
        # =====================================================================
        # ADR-070: ReAct mode — inject the agent's final message as agent_results
        # so the response LLM can reformulate with personality, display mode, etc.
        # This preserves ALL post-processing: voice, registry SSE, memory extraction,
        # psyche, journal, interest extraction — unlike a direct bypass.
        # =====================================================================
        react_result, _react_passthrough_merged = _apply_react_passthrough(state, run_id)

        llm = get_llm("vision_analysis") if has_vision_content else get_llm("response")

        agent_results_raw = _normalize_agent_results(state, run_id)

        (
            full_registry,
            current_turn_id,
            resolved_context,
            current_turn_registry,
            override_action,
            personality_instruction,
        ) = _prepare_turn_registry(state, run_id, agent_results_raw)
        # Registry items produced by the skill ReAct sub-agent (persisted via the
        # merge_registry reducer in state_update, not by in-place mutation — F5).
        skill_registry_updates: dict[str, Any] | None = None

        conversation_history, last_user_message, user_query_for_prompt = (
            _build_conversation_history(state, run_id, neutralize_history_formatting)
        )

        # Knowledge enrichment: launch Brave Search in parallel (non-blocking).
        enrichment_task, knowledge_enrichment_result = _launch_knowledge_enrichment(
            state, config, run_id, user_language
        )

        data_for_filtering = _build_data_for_filtering(current_turn_registry, user_language, run_id)

        # =====================================================================
        # CONTEXT INJECTIONS (embedding + memory, RAG, journal, portrait, psyche)
        # =====================================================================
        # Latency overlap: when the turn traversed the initiative node, the
        # bundle below was prefetched concurrently with the initiative LLM
        # call (services/response_context.py). Otherwise fetch inline — the
        # exact same code path as the historical in-node version.
        from src.domains.agents.services.response_context import (
            fetch_app_knowledge_context,
            fetch_response_context,
            pop_response_context,
        )

        user_psyche_enabled = config.get("configurable", {}).get("user_psyche_enabled", False)

        context_bundle = await pop_response_context(run_id)
        if context_bundle is None:
            context_bundle = await fetch_response_context(state, config, run_id)

        psychological_profile = context_bundle.psychological_profile
        rag_context = context_bundle.rag_context
        app_knowledge_context = context_bundle.app_knowledge_context
        if context_bundle.system_rag_deferred:
            # Latency lot R2: the router-entry prefetch could not evaluate the
            # QI-dependent system-RAG injection (is_app_help_query unknown at
            # router entry) — resolve it now with the current-turn intelligence.
            app_knowledge_context = await fetch_app_knowledge_context(
                state, last_user_message, run_id
            )
        journal_context = context_bundle.journal_context
        user_model_block = context_bundle.user_model_block
        psyche_context = context_bundle.psyche_context
        peer_context = context_bundle.peer_context
        logger.info(
            "response_context_ready",
            run_id=run_id,
            prefetched=context_bundle.prefetched,
        )

        # =====================================================================
        # Await knowledge enrichment (Brave) if a task was launched.
        knowledge_context, knowledge_enrichment_result = await _await_knowledge_enrichment(
            enrichment_task, knowledge_enrichment_result, run_id
        )

        resolved_references, enriched_query, anticipated_needs = _extract_qi_response_hints(
            state, run_id
        )

        # =================================================================
        # SKILL ACTIVATION — Hybrid: passive L2 injection + ReAct agent
        # =================================================================
        # Strategy based on skill nature (not activation route):
        #  - Skills WITH scripts → ReactSubAgentRunner (LLM orchestrates)
        #  - Skills WITH resources only (no scripts) → L2 + resources loaded
        #    in Python (no extra LLM call)
        #  - Skills WITHOUT scripts/resources → passive L2 injection only
        #  - Always-loaded skills → always passive L2 (additive context)
        #
        # Both planner and response routes use the same logic.
        _skill_res = await _activate_response_skills(
            state,
            config,
            run_id,
            last_user_message=last_user_message,
            conversation_history=conversation_history,
            current_turn_registry=current_turn_registry,
            react_result=react_result,
        )
        skills_context = _skill_res.skills_context
        skill_react_response = _skill_res.skill_react_response
        _activated_skill_name = _skill_res.activated_skill_name
        skill_registry_updates = _skill_res.skill_registry_updates
        current_turn_registry = _skill_res.current_turn_registry
        react_result = _skill_res.react_result

        # Journal, portrait and psyche contexts were computed concurrently in
        # the parallel context injections block above (TTFT optimization).
        # Read previous-turn injected IDs (= IDs from turn T-1) BEFORE we
        # overwrite them at end of node — used for deferred self-evaluation
        # by the next extraction (ADR-079).
        previous_journal_injected_ids: list[str] = list(state.get("injected_journal_ids") or [])

        # Get timezone-aware prompt with personality, history, and memory injection
        # V3 Architecture: LLM generates conversational response only
        # Data formatting handled by HTML components, injected post-LLM via HtmlRenderer
        # Intelligent Filtering: Pass user_query and data_for_filtering for semantic filtering
        #
        # Grounding fallback: when THIS turn produced no structured data,
        # current_turn_registry (and therefore data_for_filtering) is empty by
        # design, and <History> drops ToolMessages — so the model could only
        # recall entity values from prose ("16h" for an 11:15 appointment).
        # Surface the Tool-Context entities still in focus instead. REFERENCE
        # turns are deliberately excluded: their empty registry is a data-leak
        # fail-safe (registry_filtering), not a grounding gap.
        recent_entities = ""
        if should_ground_from_recent_entities(
            current_turn_registry, state.get(STATE_KEY_TURN_TYPE)
        ):
            recent_entities = build_recent_entities_context(
                full_registry,
                agent_results_raw,
                current_turn_id,
                user_language,
            )

        base_system_prompt = _build_response_system_prompt(
            state=state,
            run_id=run_id,
            user_timezone=user_timezone,
            user_language=user_language,
            user_viewport=user_viewport,
            user_display_mode=user_display_mode,
            user_psyche_enabled=user_psyche_enabled,
            personality_instruction=personality_instruction,
            conversation_history=conversation_history,
            psychological_profile=psychological_profile,
            knowledge_context=knowledge_context,
            rag_context=rag_context,
            user_query_for_prompt=user_query_for_prompt,
            last_user_message=last_user_message,
            enriched_query=enriched_query,
            data_for_filtering=data_for_filtering,
            resolved_references=resolved_references,
            anticipated_needs=anticipated_needs,
            skills_context=skills_context,
            app_knowledge_context=app_knowledge_context,
            journal_context=journal_context,
            psyche_context=psyche_context,
            user_model_block=user_model_block,
            react_result=react_result,
            recent_entities=recent_entities,
            peer_context=peer_context,
        )

        (
            agent_results_summary,
            resolved_context_for_html,
            turn_type,
            plan_rejection_reason,
        ) = await _resolve_response_context_summary(
            state,
            config,
            run_id,
            resolved_context=resolved_context,
            current_turn_id=current_turn_id,
            current_turn_registry=current_turn_registry,
            override_action=override_action,
            user_timezone=user_timezone,
            user_language=user_language,
            user_viewport=user_viewport,
        )

        result_domains = _detect_response_result_domains(
            turn_type=turn_type,
            agent_results_summary=agent_results_summary,
            current_turn_registry=current_turn_registry,
            agent_results_raw=agent_results_raw,
            run_id=run_id,
        )

        conversational_messages = await _prepare_conversational_messages(
            state,
            run_id,
            neutralize_history_formatting=neutralize_history_formatting,
            plan_rejection_reason=plan_rejection_reason,
            current_turn_attachments=current_turn_attachments,
            last_user_message=last_user_message,
            has_vision_content=has_vision_content,
        )

        chain = _build_response_chain(
            base_system_prompt=base_system_prompt,
            agent_results_summary=agent_results_summary,
            skills_context=skills_context,
            plan_rejection_reason=plan_rejection_reason,
            state=state,
            user_language=user_language,
            llm=llm,
        )

        # Enrich config with node metadata for observability (Prometheus metrics)
        enriched_config = enrich_config_with_node_metadata(config, "response")

        _log_response_llm_input(run_id, agent_results_summary, conversational_messages)

        # =====================================================================
        # FAST PATH: Skip LLM for draft confirmation/cancellation
        # =====================================================================
        # When user confirms or cancels a draft, generate a short response directly
        # without calling the LLM. This avoids verbose "chat" responses.
        draft_action_result = state.get(STATE_KEY_DRAFT_ACTION_RESULT)
        if draft_action_result:
            draft_action = draft_action_result.get("action")
            if draft_action in (
                DraftAction.CONFIRM.value,
                DraftAction.CANCEL.value,
                DraftAction.CONFIRM_BATCH.value,
            ):
                # Generate short confirmation/cancellation message (i18n)
                if draft_action in (DraftAction.CONFIRM.value, DraftAction.CONFIRM_BATCH.value):
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
                # A confirmed/cancelled draft is still a real turn: the last
                # user message in state is the request that opened the flow
                # ("send Marie a mail saying I'm moving to Lyon"), because draft
                # resumption is a bare Command(resume=...) with no message
                # injection. Returning here without scheduling meant that turn —
                # and the interrupted one before it — fed nothing at all.
                # psyche_appraisal/final_content are not yet computed on this
                # path: there was no LLM call to self-report, and the response
                # text is the short confirmation.
                _schedule_post_response_extractions(
                    state,
                    config,
                    run_id,
                    user_msg_is_trivial=context_bundle.user_msg_is_trivial,
                    personality_instruction=personality_instruction,
                    user_message_embedding=context_bundle.user_message_embedding,
                    user_language=user_language,
                    final_content=short_response,
                    previous_journal_injected_ids=previous_journal_injected_ids,
                    psyche_appraisal=None,
                )
                return draft_state_update

        # =====================================================================
        # FAST PATH: Skill ReAct agent already generated the response
        # =====================================================================
        # Mechanism #2 (SKILLS_INTEGRATION.md): ReactSubAgentRunner ran in
        # isolation and produced a complete response. Skip the main LLM chain.
        # Post-processing (psyche tags, HTML injection, etc.) still applies.
        if skill_react_response:
            logger.info(
                "response_node_skill_react_fast_path",
                run_id=run_id,
                skill_name=_activated_skill_name,
                response_length=len(skill_react_response),
            )
            # Include a synthetic tool_call so the streaming service Route 3
            # detects the skill activation and shows the frontend badge.
            _skill_tool_calls = []
            if _activated_skill_name:
                _skill_tool_calls = [
                    {
                        "name": "activate_skill_tool",
                        "args": {"name": _activated_skill_name},
                        "id": f"skill_react_{run_id}",
                    }
                ]
            result = AIMessage(
                content=skill_react_response,
                tool_calls=_skill_tool_calls,
            )
        else:
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
                _track_vision_llm_metrics(llm, _vision_start)

        _track_response_token_efficiency(result_domains, enriched_config)

        # Normalize once: Gemini 3.x returns content as list[dict] blocks; all
        # downstream regex/psyche/HTML processing requires str. This baseline also
        # lets us detect post-processing modifications (vs the raw list .content).
        original_content = coerce_content_to_text(result.content)

        logger.info(
            "response_node_completed",
            run_id=run_id,
            response_length=len(original_content),
        )

        # =====================================================================
        # CURRENT TURN REGISTRY (already filtered at start of function)
        # =====================================================================
        # BugFix 2025-12-18: Photo injection fix
        # BugFix 2025-12-19: Moved filtering to start of function (before domain detection)
        #
        # current_turn_registry is already available from earlier in this function
        # (lines ~2008-2010) - no need to re-filter here

        # Post-processing: Inject place photo if LLM didn't include it.
        # LLMs sometimes omit images despite fewshot instructions.
        final_content = original_content

        # =====================================================================
        # PSYCHE ENGINE: Parse self-report tag and strip from output
        # =====================================================================
        # Must happen BEFORE relevant_ids parsing — both modify final_content.
        # Tag is at END of response. Stripped so user never sees it.
        # content_was_modified will trigger content_replacement SSE chunk.
        psyche_appraisal, final_content = _parse_psyche_appraisal(
            final_content, user_psyche_enabled, run_id
        )

        # Intelligent filtering: parse <relevant_ids> and filter the current-turn registry.
        final_content, current_turn_registry = _apply_relevant_ids_filtering(
            final_content=final_content,
            original_content=original_content,
            current_turn_registry=current_turn_registry,
            state=state,
            result_domains=result_domains,
            last_user_message=last_user_message,
            run_id=run_id,
        )

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
        # V3 HTML rendering: inject widgets (always) + data cards (cards mode) post-LLM.
        final_content = _render_response_html(
            final_content=final_content,
            current_turn_registry=current_turn_registry,
            resolved_context_for_html=resolved_context_for_html,
            user_display_mode=user_display_mode,
            user_viewport=user_viewport,
            user_language=user_language,
            user_timezone=user_timezone,
            run_id=run_id,
        )

        # Update result content if modified
        content_was_modified = final_content != original_content
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
        state_update["memory_injection_debug"] = context_bundle.memory_injection_debug
        # RAG Spaces: Store debug details for debug panel
        state_update["rag_injection_debug"] = context_bundle.rag_injection_debug
        # Journals: Store debug details for debug panel
        state_update["journal_injection_debug"] = context_bundle.journal_injection_debug
        # Personal Journals — propagate the injected entry IDs of the CURRENT turn
        # so the next turn's extraction can perform deferred self-evaluation
        # (T → T+1, ADR-079). Reset on conversation reset is gracefully handled:
        # absent ids → extraction skips the deferred-eval section silently.
        state_update["injected_journal_ids"] = context_bundle.journal_injected_ids
        # F5 — persistence by contract (not by shared-reference side effect):
        # the ReAct passthrough merge and the skill sub-agent registry items
        # are returned explicitly. agent_results has no reducer (overwrite:
        # same value the in-place path produced); "registry" goes through the
        # merge_registry reducer (last-write-wins), equivalent to the
        # historical full_registry.update().
        if _react_passthrough_merged:
            state_update[STATE_KEY_AGENT_RESULTS] = state.get(STATE_KEY_AGENT_RESULTS, {})
        if skill_registry_updates:
            state_update["registry"] = skill_registry_updates

        await _instrument_business_metrics(state, config, run_id)

        # PHASE 2.5 - LangGraph Observability: Track state updates
        track_state_updates(state, state_update, "response", run_id)

        _record_plan_pattern_learning(state, run_id, turn_type)

        _schedule_post_response_extractions(
            state,
            config,
            run_id,
            user_msg_is_trivial=context_bundle.user_msg_is_trivial,
            personality_instruction=personality_instruction,
            user_message_embedding=context_bundle.user_message_embedding,
            user_language=user_language,
            final_content=final_content,
            previous_journal_injected_ids=previous_journal_injected_ids,
            psyche_appraisal=psyche_appraisal,
        )

        # Return updated messages (will be merged by add_messages_with_truncate reducer)
        return state_update

    except (RuntimeError, ValueError, KeyError, TypeError, AttributeError) as e:
        return _response_error_fallback(state, run_id, e)
