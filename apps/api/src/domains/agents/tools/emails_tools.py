"""
LangChain v1 tools for Gmail operations.

Pattern:
    @tool
    async def my_tool(
        arg: str,
        runtime: ToolRuntime,  # Unified access to runtime resources
    ) -> UnifiedToolOutput:
        user_id = runtime.config.get("configurable", {}).get("user_id")
        # Use runtime.config, runtime.store, runtime.state, etc.

Data Registry Mode (LOT 5):
    - Tools return UnifiedToolOutput (migrated from StandardToolOutput 2025-12-30)
    - Data Registry mode enabled via registry_enabled=True class attribute
    - Uses ToolOutputMixin for registry item creation
    - parallel_executor detects UnifiedToolOutput and extracts registry
    - Registry propagates to state and SSE stream for frontend rendering

Migration Note (2025-12-30):
    - Migrated from StandardToolOutput to UnifiedToolOutput
    - All functions now return UnifiedToolOutput directly (no conversion needed)
    - Factory methods used: UnifiedToolOutput.data_success(), UnifiedToolOutput.failure()
"""

import json
import time
from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import (
    GMAIL_DATE_OPERATORS,
    GMAIL_FORMAT_FULL,
    GMAIL_FORMAT_METADATA,
    GMAIL_INBOX_ONLY_KEYWORDS,
    GMAIL_TRASH_KEYWORDS,
)
from src.core.field_names import (
    FIELD_CACHED_AT,
)
from src.core.i18n_api_messages import APIMessages, SupportedLanguage
from src.core.i18n_types import get_language_name
from src.core.validators import validate_email
from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.context.decorators import auto_save_context
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.prompts import load_prompt
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.exceptions import (
    ContentGenerationError,
    EmailValidationError,
)
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import StandardToolOutput, UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    get_original_user_message,
    get_user_preferences,
    parse_user_id,
    resolve_recipients_to_emails,
)
from src.domains.agents.tools.validation_helpers import validate_positive_int_or_default
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.models import ConnectorType
from src.infrastructure.database import get_db_context
from src.infrastructure.llm import get_llm

logger = structlog.get_logger(__name__)


# ============================================================================
# VALIDATION HELPERS (DRY - centralized validation)
# ============================================================================


def _extract_email_from_address(address: str) -> str:
    """
    Extract email from address string.

    Handles formats:
    - "email@example.com" → "email@example.com"
    - "Name <email@example.com>" → "email@example.com"

    Args:
        address: Email address (plain or RFC 5322 format)

    Returns:
        Extracted email address
    """
    import re

    address = address.strip()
    # Match "Name <email>" format (RFC 5322)
    match = re.match(r".*<([^>]+)>", address)
    if match:
        return match.group(1).strip()
    return address


def _validate_email_addresses(
    addresses: str,
    field_name: str,
    language: SupportedLanguage = settings.default_language,
) -> None:
    """
    Validate comma-separated email addresses.

    Supports both plain emails and RFC 5322 format "Name <email>".

    Args:
        addresses: Comma-separated email addresses
        field_name: Field name for error messages (to, cc, bcc)
        language: User language for error messages

    Raises:
        EmailValidationError: If any email has invalid format
    """
    for email_addr in addresses.split(","):
        email_addr = email_addr.strip()
        if email_addr:
            # Extract email from "Name <email>" format if needed
            extracted = _extract_email_from_address(email_addr)
            if not validate_email(extracted):
                raise EmailValidationError(
                    APIMessages.email_invalid_format(email_addr, language),
                    field=field_name,
                )


# ============================================================================
# GMAIL QUERY NORMALIZATION (DRY - centralized query processing)
# ============================================================================
# LLM error normalizations for common bad queries
_LLM_ERROR_NORMALIZATIONS: dict[str, str] = {
    "inbox": "",  # Common LLM mistake for "latest emails"
    "received": "-in:sent -in:draft",  # "received" = not sent by me
    "sent": "in:sent",  # "sent" should be in:sent operator
}


def normalize_gmail_query(
    query: str,
    default_days_back: int | None = None,
    log_context: dict[str, Any] | None = None,
) -> str:
    """
    Normalize Gmail query with defense-in-depth patterns.

    Applies several transformations:
    1. Strip enclosing quotes
    2. Fix common LLM errors (e.g., "inbox" → empty query)
    3. Add scope (exclude sent/drafts by default unless inbox or other scope explicitly requested)
    4. Exclude trash unless explicitly requested
    5. Add default date range if no date filter specified

    All patterns are English-only since planner uses Semantic Pivot.
    Constants are centralized in core.constants (GMAIL_*).

    Args:
        query: Raw Gmail query string
        default_days_back: Days to look back if no date filter.
            Defaults to settings.gmail_default_search_days.
        log_context: Optional dict for logging (e.g., original_query for comparison)

    Returns:
        Normalized Gmail query string

    Example:
        >>> normalize_gmail_query("inbox")
        "-in:sent -in:draft -in:trash after:2025/10/15"
        >>> normalize_gmail_query("from:john in:inbox")
        "from:john in:inbox -in:trash after:2025/10/15"
    """
    # Use setting if not specified
    if default_days_back is None:
        default_days_back = settings.gmail_default_search_days

    # Strip enclosing quotes (LLM sometimes adds them)
    if query.startswith('"') and query.endswith('"') and query.count('"') == 2:
        query = query[1:-1]

    # LLM error normalizations
    query_stripped = query.strip().lower()
    if query_stripped in _LLM_ERROR_NORMALIZATIONS:
        normalized = _LLM_ERROR_NORMALIZATIONS[query_stripped]
        if log_context is not None:
            logger.info(
                "gmail_query_llm_error_normalized",
                original_query=query,
                normalized_query=normalized,
                reason=f"LLM generated '{query_stripped}' as search term instead of operator",
            )
        query = normalized

    query_lower = query.lower()
    original_query = log_context.get("original_query", query) if log_context else query

    # Check for explicit inbox/trash requests
    user_requested_inbox_only = any(keyword in query_lower for keyword in GMAIL_INBOX_ONLY_KEYWORDS)
    user_requested_trash = any(keyword in query_lower for keyword in GMAIL_TRASH_KEYWORDS)

    # Track scope applied for logging
    scope_applied = "preserved"  # Default if label: or in: already present

    # Add scope: exclude sent/drafts by default (user expects "received" emails), UNLESS user requested inbox only
    if "label:" not in query_lower and "in:" not in query_lower:
        if user_requested_inbox_only:
            query = f"{query} label:inbox".strip()
            scope_applied = "inbox"
        else:
            # Default behavior: return received emails only (exclude sent and drafts)
            # This matches user expectations when asking for "my emails" or "latest emails"
            query = f"{query} -in:sent -in:draft".strip()
            scope_applied = "received"

    # Exclude trash unless explicitly requested
    trash_excluded = False
    if not user_requested_trash and "-in:trash" not in query_lower:
        query = f"{query} -in:trash".strip()
        trash_excluded = True

    # Add default date range if no date filter specified
    has_date_filter = any(op in query_lower for op in GMAIL_DATE_OPERATORS)
    if not has_date_filter and default_days_back > 0:
        default_date = (datetime.now() - timedelta(days=default_days_back)).strftime("%Y/%m/%d")
        query = f"{query} after:{default_date}".strip()
        if log_context is not None:
            logger.info(
                "gmail_query_default_date_applied",
                default_date=default_date,
                days_back=default_days_back,
            )

    # Log the query scope transformation for observability
    if log_context is not None:
        logger.info(
            "search_emails_query_scope",
            original_query=original_query,
            final_query=query,
            user_requested_inbox_only=user_requested_inbox_only,
            scope_applied=scope_applied,
            trash_excluded=trash_excluded,
        )

    return query


def _validate_send_email_inputs(
    to: str | None,
    subject: str | None,
    body: str | None,
    cc: str | None = None,
    bcc: str | None = None,
    language: SupportedLanguage = settings.default_language,
) -> None:
    """
    Validate send_email inputs (centralized validation).

    Args:
        to: Recipient email(s)
        subject: Email subject
        body: Email body
        cc: CC recipients (optional)
        bcc: BCC recipients (optional)
        language: User language for error messages

    Raises:
        EmailValidationError: If validation fails
    """
    # Required fields
    if not to:
        raise EmailValidationError(
            APIMessages.email_field_required("to", language),
            field="to",
        )
    if not subject or not body:
        raise EmailValidationError(
            APIMessages.email_fields_required(["subject", "body"], language),
            field="subject,body",
        )

    # Email format validation
    _validate_email_addresses(to, "to", language)
    if cc:
        _validate_email_addresses(cc, "cc", language)
    if bcc:
        _validate_email_addresses(bcc, "bcc", language)


# ============================================================================
# CONTEXT REGISTRATION
# ============================================================================


class EmailItem(BaseModel):
    """
    Standardized email item schema for context manager.

    Used for reference resolution (e.g., "the 2nd email", "the one from John").
    """

    id: str  # Gmail message ID
    snippet: str  # Email preview text
    from_email: str = ""  # Sender email
    subject: str = ""  # Email subject


# Register email context types for context manager
# This enables contextual references like "the 2nd email", "the one from John"
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_EMAILS,  # Primary identifier (domain-based architecture)
        agent_name=AGENT_EMAIL,
        item_schema=EmailItem,  # Type-safe validation
        primary_id_field="id",
        display_name_field="snippet",
        # Searchable fields for fuzzy matching
        reference_fields=[
            "snippet",
            "from_email",
            "subject",
        ],
        icon="📧",  # Optional emoji for UI
    )
)


# ============================================================================
# TOOL 1: GET EMAILS (Unified - replaces search + details)
# ============================================================================


class GetEmailsInput(BaseModel):
    """Input schema for get_emails_tool (unified search + details)."""

    # Query mode: search by text
    query: str | None = None
    max_results: int = settings.emails_tool_default_max_results
    # ID mode: direct fetch by ID(s)
    message_id: str | None = None
    message_ids: list[str] | None = None
    # Common options
    use_cache: bool = True


# ============================================================================
# TOOL IMPLEMENTATION CLASSES (Phase 3.2 - New Architecture)
# ============================================================================


class GetEmailsTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Unified email retrieval tool - replaces search_emails_tool + get_email_details_tool.

    Architecture Simplification (2026-01):
    - Combines search and details into single tool
    - Always returns FULL email content (body, headers, attachments)
    - Supports query mode (search) OR ID mode (direct fetch)

    Modes:
    1. Query mode: query provided → search + fetch full details for each result
    2. ID mode: message_id/message_ids provided → fetch specific emails with full details
    3. No params: returns latest emails with full details

    Data Registry Mode (LOT 5.3):
    - registry_enabled=True: Returns UnifiedToolOutput with registry items
    - Registry items contain full email data for frontend rendering
    - parallel_executor extracts registry and routes to SSE stream

    Benefits vs old architecture:
    - Single tool instead of two (search + details)
    - No need for chained calls (search → details)
    - Simplified LLM reasoning (one tool covers all read operations)
    - Reduced token consumption in manifests/prompts
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"

    # Data Registry mode enabled
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize unified get emails tool."""
        super().__init__(tool_name="get_emails_tool", operation="get")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute unified email retrieval - query mode or ID mode.

        Query mode: Search + fetch full details for each result
        ID mode: Direct fetch with full details
        """
        query: str | None = kwargs.get("query")
        message_id: str | None = kwargs.get("message_id")
        message_ids: list[str] | None = kwargs.get("message_ids")
        use_cache: bool = kwargs.get("use_cache", True)
        user_timezone: str = kwargs.get("user_timezone", "UTC")
        locale: str = kwargs.get("locale", "fr-FR")

        # Route to appropriate mode
        if message_id or message_ids:
            # ID mode: direct fetch
            return await self._execute_by_ids(
                client, user_id, message_id, message_ids, use_cache, user_timezone, locale
            )
        else:
            # Query mode: search + fetch details
            return await self._execute_by_query(
                client,
                user_id,
                query or "",
                kwargs.get("max_results"),
                use_cache,
                user_timezone,
                locale,
            )

    async def _execute_by_query(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        query: str,
        max_results: int | None,
        use_cache: bool,
        user_timezone: str,
        locale: str,
    ) -> dict[str, Any]:
        """
        Search emails by query and return full details for each result.

        This is the unified behavior: search + fetch details in one call.
        """
        # Apply query normalization (from old SearchEmailsTool)
        query = self._normalize_query(query)

        # Determine max_results
        default_max_results = settings.emails_tool_default_max_results
        if max_results is None or not isinstance(max_results, int) or max_results <= 0:
            max_results = default_max_results

        # Cap at domain-specific limit (EMAILS_TOOL_DEFAULT_MAX_RESULTS)
        security_cap = settings.emails_tool_default_max_results
        if max_results > security_cap:
            logger.warning(
                "get_emails_limit_capped",
                requested_max_results=max_results,
                capped_max_results=security_cap,
            )
            max_results = security_cap

        # Execute search
        search_result = await client.search_emails(
            query=query,
            max_results=max_results,
            use_cache=use_cache,
        )

        # Get message IDs from search
        messages_metadata = search_result.get("messages", [])

        if not messages_metadata:
            logger.info(
                "get_emails_no_results",
                user_id=str(user_id),
                query=query[:50] if query else "(empty)",
            )
            return {
                "emails": [],
                "query": query,
                "from_cache": search_result.get("from_cache", False),
                "user_timezone": user_timezone,
                "locale": locale,
                "mode": "query",
            }

        # Extract message IDs and fetch full details
        message_ids = [msg.get("id") for msg in messages_metadata if msg.get("id")]

        # Fetch full details for each email (parallel)
        emails_with_details = await self._fetch_full_details(
            client, user_id, message_ids, use_cache
        )

        logger.info(
            "get_emails_query_success",
            user_id=str(user_id),
            query=query[:50] if query else "(empty)",
            total_results=len(emails_with_details),
            from_cache=search_result.get("from_cache", False),
        )

        return {
            "emails": emails_with_details,
            "query": query,
            "from_cache": search_result.get("from_cache", False),
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "query",
        }

    async def _execute_by_ids(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        message_id: str | None,
        message_ids: list[str] | None,
        use_cache: bool,
        user_timezone: str,
        locale: str,
    ) -> dict[str, Any]:
        """
        Fetch emails by ID(s) with full details.
        """
        # Determine IDs to fetch
        if message_ids and len(message_ids) > 0:
            ids_to_fetch = message_ids
        elif message_id:
            ids_to_fetch = [message_id]
        else:
            raise ValueError("Either message_id or message_ids must be provided for ID mode")

        # Cap batch size
        max_batch = 10
        if len(ids_to_fetch) > max_batch:
            logger.warning(
                "get_emails_batch_capped",
                user_id=str(user_id),
                requested=len(ids_to_fetch),
                capped=max_batch,
            )
            ids_to_fetch = ids_to_fetch[:max_batch]

        # Fetch full details
        emails_with_details = await self._fetch_full_details(
            client, user_id, ids_to_fetch, use_cache
        )

        logger.info(
            "get_emails_id_success",
            user_id=str(user_id),
            total_fetched=len(emails_with_details),
        )

        return {
            "emails": emails_with_details,
            "query": None,
            "from_cache": False,  # Batch doesn't track individual cache status
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "id",
            "message_ids": ids_to_fetch,
        }

    async def _fetch_full_details(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        message_ids: list[str],
        use_cache: bool,
    ) -> list[dict[str, Any]]:
        """
        Fetch full details for a list of message IDs (parallel).
        """
        import asyncio

        format_type = GMAIL_FORMAT_FULL

        # Fetch all emails concurrently
        tasks = [
            client.get_message(message_id=mid, format=format_type, use_cache=use_cache)
            for mid in message_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Get labels mapping once for all emails
        labels_mapping = await client.list_labels(use_cache=True)

        # Process results
        emails_list = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "get_emails_fetch_error",
                    message_id=message_ids[i],
                    error=str(result),
                )
                continue

            # Resolve label IDs
            if "labelIds" in result:
                result["labelIds"] = [
                    labels_mapping.get(label_id, label_id)
                    for label_id in result.get("labelIds", [])
                ]

            # Enrich with body and attachments
            self._enrich_email(result, message_ids[i])
            emails_list.append(result)

        return emails_list

    def _enrich_email(self, result: dict[str, Any], message_id: str) -> None:
        """Enrich email with flattened body + attachments.

        For Gmail: extracts body from base64 payload, truncates, adds web link.
        For Apple: body is already at top-level, but may need truncation.
        """
        try:
            from src.domains.agents.tools.formatters import GmailFormatter

            # Extract or truncate body (handles both Gmail payload and Apple top-level)
            body = GmailFormatter._extract_body_truncated(result)
            if body:
                result["body"] = body

            attachments = result.get("attachments")
            if attachments is None:
                attachments = GmailFormatter._extract_attachments(result)
                result["attachments"] = attachments or []
        except Exception as e:
            logger.warning(
                "get_emails_enrich_failed",
                message_id=message_id,
                error=str(e),
            )

    def _normalize_query(self, query: str) -> str:
        """
        Normalize query with defense-in-depth patterns.

        Delegates to shared normalize_gmail_query() function (DRY).
        """
        return normalize_gmail_query(query)

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with full email details.
        """
        emails = result.get("emails", [])
        query = result.get("query")
        from_cache = result.get("from_cache", False)
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        # Use ToolOutputMixin helper (with timezone conversion)
        return self.build_emails_output(
            emails=emails,
            query=query,
            from_cache=from_cache,
            user_timezone=user_timezone,
            locale=locale,
        )


# Create unified tool instance (singleton)
_get_emails_tool_instance = GetEmailsTool()


@connector_tool(
    name="get_emails",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.LIST,
    category="read",
)
@auto_save_context("emails")
async def get_emails_tool(
    query: Annotated[
        str | None, "Gmail search query (optional, supports all Gmail operators)"
    ] = None,
    message_id: Annotated[str | None, "Gmail message ID for direct fetch (optional)"] = None,
    message_ids: Annotated[
        list[str] | None, "List of Gmail message IDs for batch fetch (optional)"
    ] = None,
    max_results: Annotated[
        int, "Maximum number of results (default 10, max 50)"
    ] = settings.emails_tool_default_max_results,
    use_cache: Annotated[bool, "Use cached results if available (default True)"] = True,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get emails with full details - unified search and retrieval.

    Replaces search_emails_tool + get_email_details_tool with a single tool.

    Modes:
    - Query mode: get_emails_tool(query="from:john") → search + return full details
    - ID mode: get_emails_tool(message_id="abc123") → fetch specific email with full details
    - Batch mode: get_emails_tool(message_ids=["abc", "def"]) → fetch multiple emails
    - List mode: get_emails_tool() → return latest emails with full details

    Always returns FULL email content including:
    - Headers (From, To, Subject, Date, etc.)
    - Body content (text extracted from HTML if needed)
    - Labels and flags
    - Attachments info

    Gmail search operators (for query mode):
    - from:john@example.com - Emails from specific sender
    - to:jane@example.com - Emails to specific recipient
    - subject:meeting - Emails with keyword in subject
    - is:unread - Unread emails
    - has:attachment - Emails with attachments
    - after:2025/01/01 - Emails after date
    - label:inbox - Emails with specific label

    Args:
        query: Gmail search query (optional)
        message_id: Specific message ID to fetch (optional)
        message_ids: List of message IDs for batch fetch (optional)
        max_results: Maximum number of results for query mode (default 10, max 50)
        use_cache: Use cached results if available (default True)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with registry items containing full email data
    """
    # Get user timezone/locale for formatting
    user_timezone = "UTC"
    locale = "fr-FR"

    try:
        user_id_raw = runtime.config.get("configurable", {}).get("user_id")
        if user_id_raw:
            user_id = parse_user_id(user_id_raw)
            async with get_db_context() as db:
                from src.domains.users.service import UserService

                user_service = UserService(db)
                user = await user_service.get_user_by_id(user_id)
                if user:
                    user_timezone = user.timezone if user.timezone else "UTC"
                    user_language = user.language if user.language else "fr"
                    locale = f"{user_language}-{user_language.upper()}"
    except Exception as e:
        logger.debug("user_preferences_fallback", error=str(e))

    # Delegate to unified tool instance
    result = await _get_emails_tool_instance.execute(
        runtime=runtime,
        query=query,
        message_id=message_id,
        message_ids=message_ids,
        max_results=max_results,
        use_cache=use_cache,
        user_timezone=user_timezone,
        locale=locale,
    )

    # Save to context (for $context.emails references)
    if runtime.store:
        try:
            user_id_raw = runtime.config.get("configurable", {}).get("user_id")
            thread_id = runtime.config.get("configurable", {}).get("thread_id")

            if user_id_raw and thread_id:
                user_id = parse_user_id(user_id_raw)
                thread_id_str = str(thread_id)

                # Extract emails from result
                emails_to_save = []
                if isinstance(result, StandardToolOutput | UnifiedToolOutput):
                    for item in result.registry_updates.values():
                        emails_to_save.append(item.payload)
                else:
                    parsed = json.loads(result)
                    data = parsed.get("data", {})
                    emails_to_save = data.get("emails", [])

                # Store with proper namespace
                await runtime.store.aput(
                    (str(user_id), thread_id_str, "context", "emails"),
                    "list_current_search",
                    {
                        "emails": emails_to_save,
                        "query": query,
                        "timestamp": time.time(),
                    },
                )
        except Exception as e:
            logger.debug("store_context_failed", error=str(e))

    return result


# ============================================================================
# LEGACY TOOLS (Deprecated - kept for backward compatibility)
# ============================================================================


class SearchEmailsInput(BaseModel):
    """Input schema for search_emails_tool (DEPRECATED - use GetEmailsInput)."""

    query: str
    max_results: int = settings.emails_tool_default_max_results
    use_cache: bool = True


class SearchEmailsTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Search emails tool using new Phase 3.2 architecture with Data Registry support.

    Benefits vs old implementation:
    - Eliminates 100+ lines of DI boilerplate
    - Standardizes error handling
    - Reuses ConnectorTool base class
    - Uses GmailFormatter (eliminates formatting duplication)

    Data Registry Mode (LOT 5.3):
    - registry_enabled=True: Returns UnifiedToolOutput with registry items
    - Registry items contain full email data for frontend rendering
    - Summary for LLM is compact text with subject, sender and IDs
    - parallel_executor extracts registry and routes to SSE stream
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"

    # Data Registry mode enabled - returns StandardToolOutput instead of JSON string
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize search emails tool with Data Registry support."""
        super().__init__(tool_name="get_emails_tool", operation="search")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute search emails API call - business logic only."""

        query: str = kwargs["query"]
        raw_max_results = kwargs.get("max_results")
        default_max_results = settings.emails_tool_default_max_results
        max_results = validate_positive_int_or_default(raw_max_results, default=default_max_results)
        # Cap at domain-specific limit (EMAILS_TOOL_DEFAULT_MAX_RESULTS)
        security_cap = settings.emails_tool_default_max_results
        if max_results > security_cap:
            logger.warning(
                "emails_search_limit_capped",
                requested_max_results=raw_max_results,
                capped_max_results=security_cap,
                default_max_results=default_max_results,
            )
            max_results = security_cap
        use_cache: bool = kwargs.get("use_cache", True)
        user_timezone: str = kwargs.get("user_timezone", "UTC")
        locale: str = kwargs.get("locale", "fr-FR")

        # DEFENSE IN DEPTH: Normalize Gmail query using shared helper (DRY)
        # Handles: quote removal, LLM errors, scope, trash exclusion, date range
        original_query = kwargs["query"]
        query = normalize_gmail_query(query, log_context={"original_query": original_query})

        logger.info(
            "search_emails_query_normalized",
            original_query=original_query,
            final_query=query,
        )

        # Resolve user-friendly label names to Gmail label IDs
        # This transforms "label:COPRO" to "label:Label_12345678"
        resolved_query = await client.resolve_label_names_in_query(query, use_cache=True)
        if resolved_query != query:
            logger.info(
                "search_emails_labels_resolved",
                original_query=query,
                resolved_query=resolved_query,
            )
            query = resolved_query

        # Execute API call
        result = await client.search_emails(
            query=query,
            max_results=max_results,
            use_cache=use_cache,
        )

        # Extract messages
        messages = result.get("messages", [])
        from_cache = result.get("from_cache", False)
        cached_at = result.get(FIELD_CACHED_AT)

        # Resolve label IDs to user-friendly names
        # This translates technical IDs like "Label_12345678" to "Mon projet"
        if messages:
            labels_mapping = await client.list_labels(use_cache=True)
            for msg in messages:
                if "labelIds" in msg:
                    msg["labelIds"] = [
                        labels_mapping.get(label_id, label_id)
                        for label_id in msg.get("labelIds", [])
                    ]

        logger.info(
            "search_emails_success",
            user_id=str(user_id),
            query_preview=query[:20] if len(query) > 20 else query,
            total_results=len(messages),
            from_cache=from_cache,
        )

        return {
            "messages": messages,
            "query": query,
            "from_cache": from_cache,
            FIELD_CACHED_AT: cached_at,
            "user_timezone": user_timezone,
            "locale": locale,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with registry items.

        Uses ToolOutputMixin.build_emails_output() to create:
        - message: Compact text with subject, sender and IDs
        - registry_updates: Full email data for frontend rendering
        - metadata: Query info, cache status, etc.

        The summary is designed for LLM reasoning while registry
        provides complete data for rich frontend display.

        TIMEZONE: Dates are converted to user's timezone before storage.

        Example summary:
            Found 5 emails for "invoice":
            - "Invoice #1234" from john@example.com [email_abc123]
            - "Payment reminder" from billing@corp.com [email_def456]
            - "Receipt attached" from shop@store.com [email_ghi789]
        """
        messages = result.get("messages", [])
        query = result.get("query", "")
        from_cache = result.get("from_cache", False)
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        # Use ToolOutputMixin helper method (with timezone conversion)
        # build_emails_output returns UnifiedToolOutput directly
        return self.build_emails_output(
            emails=messages,
            query=query,
            from_cache=from_cache,
            user_timezone=user_timezone,
            locale=locale,
        )


# Create tool instance (singleton)
_search_emails_tool_instance = SearchEmailsTool()


@connector_tool(
    name="search_emails",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="read",
)
@auto_save_context("emails")
async def search_emails_tool(
    query: Annotated[str, "Gmail search query (supports all Gmail search operators)"],
    max_results: Annotated[
        int, "Maximum number of results to return (default 10, max 100)"
    ] = settings.emails_tool_default_max_results,
    use_cache: Annotated[bool, "Use cached results if available (default True)"] = True,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Search emails using Gmail search query syntax.

    Supports all Gmail search operators:
    - from:john@example.com - Emails from specific sender
    - to:jane@example.com - Emails to specific recipient
    - subject:meeting - Emails with keyword in subject
    - is:unread - Unread emails
    - has:attachment - Emails with attachments
    - after:2025/01/01 - Emails after date
    - before:2025/12/31 - Emails before date
    - label:inbox - Emails with specific label

    **IMPORTANT - Semantic Label Mappings (for natural language queries):**
    When user asks for emails from specific folders, translate to label: syntax:
    - "boîte de réception" / "inbox" / "received" → label:INBOX
    - "envoyés" / "sent" / "emails I sent" → label:SENT
    - "brouillons" / "drafts" → label:DRAFT
    - "corbeille" / "trash" / "deleted" → label:TRASH
    - "spam" / "indésirables" → label:SPAM
    - "importants" / "starred" / "favoris" → label:STARRED
    - "non lus" / "unread" → is:unread
    - "lus" / "read" → is:read

    Returns minimal email metadata (id, threadId, snippet, labels, date).
    For full email content, use get_email_details_tool.

    Examples:
        - "from:john@example.com subject:invoice"
        - "is:unread after:2025/01/01"
        - "has:attachment label:inbox"
        - "label:INBOX" (for inbox/boîte de réception)
        - "label:SENT" (for sent/envoyés)
        - "label:STARRED is:unread" (for unread starred emails)

    Args:
        query: Gmail search query string
        max_results: Maximum number of emails to return (default 10, max 100)
        use_cache: Use cached results if available (default True)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with registry items containing email data

    **Phase 3.2 Migration:** This tool now uses the new architecture (ConnectorTool base class).
    All boilerplate (DI, OAuth, error handling, formatting) is eliminated.

    **Data Registry Mode (LOT 5.3):** Returns UnifiedToolOutput with registry items.
    parallel_executor handles extraction and SSE streaming to frontend.
    """
    # Get user timezone/locale for formatting
    try:
        user_timezone, _, locale = await get_user_preferences(runtime)
    except Exception:
        # Fallback to defaults
        user_timezone = "UTC"
        locale = "fr-FR"

    # Delegate to tool instance (new architecture)
    result = await _search_emails_tool_instance.execute(
        runtime=runtime,
        query=query,
        max_results=max_results,
        use_cache=use_cache,
        user_timezone=user_timezone,
        locale=locale,
    )

    # Save to context (for $context.emails references)
    # BUGFIX (Issue #38): Store with proper user-scoped namespace for automatic cleanup
    # Format: (user_id, thread_id, "context", "emails") enables cleanup on conversation reset
    if runtime.store:
        try:
            # Extract user_id and thread_id from runtime.config
            user_id_raw = runtime.config.get("configurable", {}).get("user_id")
            thread_id = runtime.config.get("configurable", {}).get("thread_id")

            if user_id_raw and thread_id:
                user_id = parse_user_id(user_id_raw)
                thread_id_str = str(thread_id)

                # Data Registry LOT 5.3: Handle UnifiedToolOutput, StandardToolOutput, and legacy JSON string
                messages = []
                if isinstance(result, StandardToolOutput | UnifiedToolOutput):
                    # Extract messages from registry_updates payload
                    for item in result.registry_updates.values():
                        messages.append(item.payload)
                else:
                    # Legacy mode: Parse JSON string
                    parsed = json.loads(result)
                    data = parsed.get("data", {})
                    messages = data.get("emails", [])

                # Store with proper namespace
                # OLD BUG: ("emails", "list") - no user scope, orphaned data accumulation
                # NEW FIX: (user_id, thread_id, "context", "emails") - user scoped, auto-cleanup
                await runtime.store.aput(
                    (str(user_id), thread_id_str, "context", "emails"),
                    "list_current_search",
                    {
                        "emails": messages,
                        "query": query,
                        "timestamp": time.time(),
                    },
                )
        except Exception:
            pass  # Context save is non-critical

    return result


# ============================================================================
# TOOL 2: GET EMAIL DETAILS
# ============================================================================


class GetEmailDetailsInput(BaseModel):
    """Input schema for get_email_details_tool (legacy, tool uses annotations)."""

    # MULTI-ORDINAL FIX (2026-01-02): Support both single and batch modes
    message_id: str | None = None  # Single mode
    message_ids: list[str] | None = None  # Batch mode
    include_body: bool = True
    use_cache: bool = True


class GetEmailDetailsTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Get email details tool using new Phase 3.2 architecture with Data Registry support.

    Benefits vs old implementation:
    - Eliminates 80+ lines of DI boilerplate
    - Standardizes error handling
    - Reuses ConnectorTool base class
    - Uses GmailFormatter (eliminates formatting duplication)

    Data Registry Mode (LOT 5.3):
    - registry_enabled=True: Returns UnifiedToolOutput with registry items
    - Registry contains full email data including body for frontend rendering
    - Summary for LLM includes subject, sender, and key metadata
    - parallel_executor extracts registry and routes to SSE stream
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"

    # Data Registry mode enabled - returns StandardToolOutput instead of JSON string
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize get email details tool with Data Registry support."""
        super().__init__(tool_name="get_emails_tool", operation="details")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute get email details API call - business logic only.

        Supports both single and batch modes:
        - Single: message_id provided → fetch one email
        - Batch: message_ids provided → fetch multiple emails in parallel

        MULTI-ORDINAL FIX (2026-01-01): Added batch mode support for multi-reference queries.
        Example: "detail du 1 et du 2" → message_ids=["id1", "id2"]
        """
        message_id: str | None = kwargs.get("message_id")
        message_ids: list[str] | None = kwargs.get("message_ids")
        use_cache: bool = kwargs.get("use_cache", True)
        user_timezone: str = kwargs.get("user_timezone", "UTC")
        locale: str = kwargs.get("locale", "fr-FR")

        # Validation: exactly one of message_id or message_ids required
        if not message_id and not message_ids:
            raise ValueError("Either message_id or message_ids must be provided")
        if message_id and message_ids:
            raise ValueError("message_id and message_ids are mutually exclusive")

        # Route to single or batch mode
        if message_ids:
            return await self._execute_batch(
                client, user_id, message_ids, use_cache, user_timezone, locale
            )
        else:
            return await self._execute_single(
                client, user_id, message_id, use_cache, user_timezone, locale
            )

    async def _execute_single(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        message_id: str,
        use_cache: bool,
        user_timezone: str,
        locale: str,
    ) -> dict[str, Any]:
        """Execute single email details fetch."""
        # Force body/attachments for details: downstream formatting relies on rich payload
        include_body: bool = True

        # Get message with appropriate format
        format_type = GMAIL_FORMAT_FULL if include_body else GMAIL_FORMAT_METADATA
        result = await client.get_message(
            message_id=message_id,
            format=format_type,
            use_cache=use_cache,
        )

        # Resolve label IDs to user-friendly names
        if "labelIds" in result:
            labels_mapping = await client.list_labels(use_cache=True)
            result["labelIds"] = [
                labels_mapping.get(label_id, label_id) for label_id in result.get("labelIds", [])
            ]

        # Enrich with flattened body + attachments for downstream consumption
        self._enrich_email(result, message_id, include_body)

        # Extract data
        from_cache = result.get("from_cache", False)
        cached_at = result.get(FIELD_CACHED_AT)

        logger.info(
            "get_email_details_success",
            user_id=str(user_id),
            message_id=message_id,
            include_body=include_body,
            from_cache=from_cache,
        )

        return {
            "email": result,
            "message_id": message_id,
            "include_body": include_body,
            "from_cache": from_cache,
            FIELD_CACHED_AT: cached_at,
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "single",
        }

    async def _execute_batch(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        message_ids: list[str],
        use_cache: bool,
        user_timezone: str,
        locale: str,
    ) -> dict[str, Any]:
        """
        Execute batch email details fetch using asyncio.gather.

        MULTI-ORDINAL FIX (2026-01-01): Parallel fetch for multi-reference queries.
        """
        import asyncio

        include_body: bool = True
        format_type = GMAIL_FORMAT_FULL

        # Cap batch size for safety
        max_batch = 10
        if len(message_ids) > max_batch:
            logger.warning(
                "get_email_details_batch_capped",
                user_id=str(user_id),
                requested=len(message_ids),
                capped=max_batch,
            )
            message_ids = message_ids[:max_batch]

        # Fetch all emails concurrently
        tasks = [
            client.get_message(message_id=mid, format=format_type, use_cache=use_cache)
            for mid in message_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Get labels mapping once for all emails
        labels_mapping = await client.list_labels(use_cache=True)

        # Process results (separate successes and errors)
        emails_list = []
        errors = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append(
                    {
                        "message_id": message_ids[i],
                        "error": str(result),
                        "error_type": type(result).__name__,
                    }
                )
            else:
                # Resolve label IDs
                if "labelIds" in result:
                    result["labelIds"] = [
                        labels_mapping.get(label_id, label_id)
                        for label_id in result.get("labelIds", [])
                    ]
                # Enrich email
                self._enrich_email(result, message_ids[i], include_body)
                emails_list.append(result)

        logger.info(
            "get_email_details_batch_success",
            user_id=str(user_id),
            total_requested=len(message_ids),
            total_success=len(emails_list),
            total_errors=len(errors),
        )

        return {
            "emails": emails_list,
            "message_ids": message_ids,
            "include_body": include_body,
            "from_cache": False,  # Batch mode doesn't track individual cache status
            FIELD_CACHED_AT: None,
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "batch",
            "errors": errors if errors else None,
        }

    def _enrich_email(self, result: dict[str, Any], message_id: str, include_body: bool) -> None:
        """Enrich email with flattened body + attachments for downstream consumption.

        For Gmail: extracts body from base64 payload, truncates, adds web link.
        For Apple: body is already at top-level, but may need truncation.
        """
        try:
            from src.domains.agents.tools.formatters import GmailFormatter

            if include_body:
                body = GmailFormatter._extract_body_truncated(result)
                if body:
                    result["body"] = body

            attachments = result.get("attachments")
            if attachments is None:
                attachments = GmailFormatter._extract_attachments(result)
                result["attachments"] = attachments or []
        except Exception as e:
            logger.warning(
                "get_email_details_enrich_failed",
                message_id=message_id,
                error=str(e),
            )

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with registry items.

        Handles both single and batch modes:
        - Single mode: One email in registry with full details
        - Batch mode: Multiple emails in registry, errors in metadata

        Uses ToolOutputMixin.build_emails_output() for consistent formatting.

        TIMEZONE: Dates are converted to user's timezone before storage.

        MULTI-ORDINAL FIX (2026-01-01): Added batch mode support.

        Example summary (single):
            Email details: "Re: Project Update" from john@example.com
            Content: 523 chars, 1 attachment

        Example summary (batch):
            Email details retrieved: 2 emails
            1. "Re: Project Update" from john@example.com
            2. "Meeting Tomorrow" from jane@example.com
        """
        mode = result.get("mode", "single")
        from_cache = result.get("from_cache", False)
        include_body = result.get("include_body", True)
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        # Handle single vs batch mode
        errors = None
        if mode == "batch":
            emails = result.get("emails", [])
            message_ids = result.get("message_ids", [])
            errors = result.get("errors")
        else:
            email = result.get("email", {})
            emails = [email] if email else []
            message_ids = [result.get("message_id", "")]

        # Build base output using mixin helper (with timezone conversion)
        # build_emails_output returns UnifiedToolOutput directly
        output = self.build_emails_output(
            emails=emails,
            query=None,  # Details operation doesn't use query
            from_cache=from_cache,
            user_timezone=user_timezone,
            locale=locale,
        )

        # Add details-specific metadata
        if mode == "batch":
            output.metadata["message_ids"] = message_ids
            output.metadata["mode"] = "batch"
            if errors:
                output.metadata["errors"] = errors
        else:
            output.metadata["message_id"] = message_ids[0] if message_ids else ""
            output.metadata["mode"] = "single"
        output.metadata["include_body"] = include_body

        # Build summary based on mode
        if mode == "batch" and emails:
            # Batch summary
            summary_lines = [f"Email details retrieved: {len(emails)} email(s)"]
            for i, email in enumerate(emails[:5], 1):  # Limit to 5 for summary
                headers = email.get("payload", {}).get("headers", [])
                subject = ""
                from_addr = ""
                for header in headers:
                    name = header.get("name", "").lower()
                    if name == "subject":
                        subject = header.get("value", "")[:40]
                    elif name == "from":
                        from_addr = header.get("value", "")
                summary_lines.append(f'{i}. "{subject}" from {from_addr}')
            if len(emails) > 5:
                summary_lines.append(f"... and {len(emails) - 5} more")
            output.message = "\n".join(summary_lines)
        elif emails:
            # Single email summary
            email = emails[0]
            headers = email.get("payload", {}).get("headers", [])
            subject = ""
            from_addr = ""
            for header in headers:
                name = header.get("name", "").lower()
                if name == "subject":
                    subject = header.get("value", "")[:50]
                elif name == "from":
                    from_addr = header.get("value", "")

            body_length = len(email.get("body", "")) if include_body else 0
            attachments = email.get("attachments", [])
            attachment_info = f", {len(attachments)} attachment(s)" if attachments else ""

            output.message = (
                f'Email details: "{subject}" from {from_addr}\n'
                f"Content: {body_length} chars{attachment_info}"
            )

        return output


# Create tool instance (singleton)
_get_email_details_tool_instance = GetEmailDetailsTool()


@connector_tool(
    name="get_email_details",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="read",
)
@auto_save_context("emails")
async def get_email_details_tool(
    message_id: Annotated[str | None, "Gmail message ID to retrieve (single mode)"] = None,
    message_ids: Annotated[
        list[str] | None,
        "List of Gmail message IDs to retrieve (batch mode for multi-ordinal queries)",
    ] = None,
    include_body: Annotated[bool, "Include email body content (default True)"] = True,
    use_cache: Annotated[bool, "Use cached results if available (default True)"] = True,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get detailed information for one or more email messages.

    Supports both single and batch modes:
    - Single: message_id="abc123" → fetch one email
    - Batch: message_ids=["abc123", "def456"] → fetch multiple emails in parallel

    MULTI-ORDINAL FIX (2026-01-01): Added batch mode for multi-reference queries.
    Example: "detail du 1 et du 2" → message_ids=["id1", "id2"]

    Returns complete email metadata including:
    - Headers (From, To, Subject, Date, etc.)
    - Body content (text extracted from HTML if needed)
    - Labels and flags
    - Thread ID
    - Attachments info

    Use this after search_emails_tool to get full content of specific emails.

    Args:
        message_id: Gmail message ID for single mode (from search_emails_tool results)
        message_ids: List of Gmail message IDs for batch mode
        include_body: Include email body content (default True)
        use_cache: Use cached results if available (default True)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with registry items containing email details

    **Phase 3.2 Migration:** This tool now uses the new architecture (ConnectorTool base class).
    All boilerplate (DI, OAuth, error handling, formatting) is eliminated.

    **Data Registry Mode (LOT 5.3):** Returns UnifiedToolOutput with registry items.
    parallel_executor handles extraction and SSE streaming to frontend.
    """
    # Get user timezone/locale for formatting
    user_timezone = "UTC"
    locale = "fr-FR"

    try:
        user_id_raw = runtime.config.get("configurable", {}).get("user_id")
        if user_id_raw:
            user_id = parse_user_id(user_id_raw)
            async with get_db_context() as db:
                from src.domains.users.service import UserService

                user_service = UserService(db)
                user = await user_service.get_user_by_id(user_id)
                if user:
                    user_timezone = user.timezone if user.timezone else "UTC"
                    user_language = user.language if user.language else "fr"
                    locale = f"{user_language}-{user_language.upper()}"
    except Exception:
        pass  # Use defaults if user lookup fails

    # Delegate to tool instance (new architecture)
    # Pass both message_id and message_ids - execute_api_call will validate
    result = await _get_email_details_tool_instance.execute(
        runtime=runtime,
        message_id=message_id,
        message_ids=message_ids,
        include_body=include_body,
        use_cache=use_cache,
        user_timezone=user_timezone,
        locale=locale,
    )

    # Save to context
    # BUGFIX (Issue #38): Store with proper user-scoped namespace for automatic cleanup
    # MULTI-ORDINAL FIX (2026-01-01): Support batch mode context saving
    if runtime.store:
        try:
            # Extract user_id and thread_id from runtime.config
            user_id_raw = runtime.config.get("configurable", {}).get("user_id")
            thread_id = runtime.config.get("configurable", {}).get("thread_id")

            if user_id_raw and thread_id:
                user_id = parse_user_id(user_id_raw)
                thread_id_str = str(thread_id)

                # Determine mode and extract emails
                is_batch_mode = message_ids is not None and len(message_ids) > 0
                emails_to_save: list[tuple[str, dict]] = []  # List of (msg_id, email_data)

                if isinstance(result, StandardToolOutput | UnifiedToolOutput):
                    # Data Registry mode: Extract from registry_updates
                    for item in result.registry_updates.values():
                        email_data = item.payload
                        msg_id = email_data.get("id", "")
                        if msg_id:
                            emails_to_save.append((msg_id, email_data))
                        if not is_batch_mode:
                            break  # Single mode: only one email
                else:
                    # Legacy mode: Parse JSON string
                    parsed = json.loads(result)
                    data_wrapper = parsed.get("data", {})
                    emails_array = data_wrapper.get("emails", [])
                    for email_data in emails_array:
                        msg_id = email_data.get("id", "")
                        if msg_id:
                            emails_to_save.append((msg_id, email_data))
                        if not is_batch_mode:
                            break  # Single mode: only one email

                # Save each email to context
                for msg_id, email_data in emails_to_save:
                    # Extract subject/from for context storage
                    subject = ""
                    from_addr = ""
                    body = None

                    if isinstance(result, StandardToolOutput | UnifiedToolOutput):
                        # Extract from payload headers
                        headers = email_data.get("payload", {}).get("headers", [])
                        for header in headers:
                            name = header.get("name", "").lower()
                            if name == "subject":
                                subject = header.get("value", "")
                            elif name == "from":
                                from_addr = header.get("value", "")
                        body = email_data.get("body") if include_body else None
                    else:
                        subject = email_data.get("subject", "")
                        from_addr = email_data.get("from", "")
                        body = email_data.get("body") if include_body else None

                    # Store with proper namespace
                    # OLD BUG: ("emails", "item") - no user scope, orphaned data accumulation
                    # NEW FIX: (user_id, thread_id, "context", "emails") - user scoped, auto-cleanup
                    await runtime.store.aput(
                        (str(user_id), thread_id_str, "context", "emails"),
                        f"item_{msg_id}",
                        {
                            "id": msg_id,
                            "subject": subject,
                            "from": from_addr,
                            "body": body,
                            # Store the full payload so reference resolution/details reuse all attributes
                            "email": email_data,
                            "timestamp": time.time(),
                        },
                    )
        except Exception:
            pass  # Context save is non-critical

    return result


# ============================================================================
# TOOL 3: SEND EMAIL (Data Registry LOT 5.4 - Draft/HITL Integration)
# ============================================================================


class SendEmailInput(BaseModel):
    """Input schema for send_email_tool."""

    to: str
    subject: str | None = None  # Optional if content_instruction provided
    body: str | None = None  # Optional if content_instruction provided
    content_instruction: str | None = None  # For LLM-generated creative content
    cc: str | None = None
    bcc: str | None = None
    is_html: bool = False


class SendEmailDraftTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Send email tool with Draft/HITL integration.

    Data Registry LOT 5.4: Write operations with confirmation flow.

    This tool creates a DRAFT that requires user confirmation before sending.
    The actual email is NOT sent until the user confirms via HITL.

    Flow:
    1. Tool creates draft → UnifiedToolOutput with requires_confirmation=True
    2. LIAToolNode detects requires_confirmation → sets pending_draft_critique
    3. Graph routes to draft_critique node
    4. User confirms/edits/cancels via HITL
    5. On confirm: execute_fn sends the email

    Benefits:
    - User can review email before sending
    - User can edit subject/body before confirming
    - Prevents accidental email sends
    - Audit trail of drafts and confirmations
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"

    # Data Registry mode enabled - creates draft for HITL confirmation
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize send email draft tool."""
        super().__init__(tool_name="send_email_tool", operation="send_draft")

    async def execute(
        self,
        runtime: ToolRuntime | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute send email with automatic recipient resolution.

        If 'to', 'cc', or 'bcc' is a name instead of an email, automatically searches
        contacts to find the email address using the centralized helper.

        This enables flows like:
        - User says "my wife" → memory resolves to "Jane Smith"
        - Planner uses "Jane Smith" as recipient
        - This method resolves "Jane Smith" → "jane.smith@example.com"
        """
        # Resolve recipient fields via centralized helper
        # Each field is resolved independently: "Name" → "Name <email>"
        for field in ("to", "cc", "bcc"):
            value = kwargs.get(field, "")
            if value:
                resolved = await resolve_recipients_to_emails(runtime, value, field)
                if resolved:
                    kwargs[field] = resolved

        return await super().execute(runtime=runtime, **kwargs)

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare email draft data (no API call yet).

        The actual send happens after user confirms via HITL.
        Note: Content generation (if content_instruction was provided) is handled
        by send_email_tool BEFORE calling this method.

        Args:
            client: GoogleGmailClient (not used here, but required by base class)
            user_id: User UUID
            **kwargs: Email parameters (to, subject, body, cc, bcc, is_html)

        Returns:
            Dict with email draft data for Data Registry formatting
        """
        to: str = kwargs["to"]
        subject: str | None = kwargs.get("subject")
        body: str | None = kwargs.get("body")
        cc: str | None = kwargs.get("cc")
        bcc: str | None = kwargs.get("bcc")
        is_html: bool = kwargs.get("is_html", False)

        # Centralized validation (DRY)
        _validate_send_email_inputs(to, subject, body, cc, bcc)

        logger.info(
            "send_email_draft_prepared",
            user_id=str(user_id),
            to=to,
            subject=subject[:50] if len(subject) > 50 else subject,
        )

        # Return draft data for Data Registry formatting
        # Note: No API call here - email will be sent after user confirms
        return {
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc,
            "bcc": bcc,
            "is_html": is_html,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create email draft via DraftService.

        Returns UnifiedToolOutput with:
        - DRAFT registry item containing email content
        - requires_confirmation=True in metadata
        - Actions: confirm, edit, cancel

        The LIAToolNode will detect requires_confirmation and route
        to draft_critique node for HITL flow.
        """
        from src.domains.agents.drafts import create_email_draft

        # create_email_draft returns UnifiedToolOutput directly
        return create_email_draft(
            to=result["to"],
            subject=result["subject"],
            body=result["body"],
            cc=result.get("cc"),
            bcc=result.get("bcc"),
            is_html=result.get("is_html", False),
            source_tool="send_email_tool",
            user_language=self.get_user_language(),
        )


# ============================================================================
# LEGACY: Direct Send (for backward compatibility during transition)
# ============================================================================


class SendEmailDirectTool(ConnectorTool[GoogleGmailClient]):
    """
    Send email tool that executes immediately (no HITL).

    WARNING: This tool sends emails WITHOUT user confirmation.
    Use SendEmailDraftTool instead for production.

    This class is kept for:
    1. Backward compatibility during LOT 5.4 migration
    2. execute_fn in DraftCritiqueInteraction (actual send after confirm)
    3. Testing/debugging without HITL flow

    For normal use, prefer SendEmailDraftTool which creates a draft
    and requires user confirmation before sending.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"

    def __init__(self) -> None:
        """Initialize direct send email tool."""
        super().__init__(tool_name="send_email_direct_tool", operation="send")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute send email API call - business logic only."""
        to: str = kwargs["to"]
        subject: str = kwargs["subject"]
        body: str = kwargs["body"]
        cc: str | None = kwargs.get("cc")
        bcc: str | None = kwargs.get("bcc")
        is_html: bool = kwargs.get("is_html", False)

        # Centralized validation (DRY)
        _validate_send_email_inputs(to, subject, body, cc, bcc)

        # Send email
        result = await client.send_email(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            is_html=is_html,
        )

        logger.info(
            "gmail_email_sent_via_tool",
            user_id=str(user_id),
            message_id=result.get("id"),
            to=to,
            subject=subject[:50] if len(subject) > 50 else subject,
        )

        return {
            "success": True,
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "to": to,
            "subject": subject,
            "message": APIMessages.email_sent_successfully(to),
        }


# Create tool instance (singleton)
_send_email_draft_tool_instance = SendEmailDraftTool()


# ============================================================================
# CONTENT GENERATION HELPER
# ============================================================================


async def _generate_email_content(
    instruction: str,
    recipient: str,
    user_language: str = settings.default_language,
    existing_body: str | None = None,
    config: Any = None,
    user_id: str | None = None,
) -> dict[str, str]:
    """
    Generate email subject and/or body from a creative instruction using LLM.

    Optimized: When existing_body is provided, only generates the subject
    using a specialized prompt for better efficiency and accuracy.

    Args:
        instruction: Creative instruction (e.g., "poème d'amour humoristique sur Excel")
        recipient: Email recipient for context
        user_language: Target language for generated content
        existing_body: If provided, only generate subject (body already exists)
        config: Optional RunnableConfig with TokenTrackingCallback for billing tracking
        user_id: User UUID string for psyche context injection

    Returns:
        Dict with 'subject' key (always) and 'body' key (only if generated)

    Raises:
        ContentGenerationError: If generation fails or returns invalid format
    """
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

    # Convert language code to human-readable name for LLM comprehension
    language_name = get_language_name(user_language)

    # Choose appropriate prompt based on what needs to be generated
    if existing_body:
        # Subject-only mode: more efficient, uses existing body for context
        prompt = load_prompt("email_subject_generation_prompt").format(
            instruction=instruction,
            recipient=recipient,
            body=existing_body,
            user_language=language_name,
        )
        required_fields = ["subject"]
        logger.debug(
            "email_content_generation_mode",
            mode="subject_only",
            body_length=len(existing_body),
        )
    else:
        # Full generation mode: generate both subject and body
        prompt = load_prompt("email_content_generation_prompt").format(
            instruction=instruction,
            recipient=recipient,
            user_language=language_name,
        )
        required_fields = ["subject", "body"]
        logger.debug("email_content_generation_mode", mode="full")

    llm = get_llm("email_agent")

    # Enrich config with node metadata for token tracking
    enriched_config = (
        enrich_config_with_node_metadata(config, "email_content_generation") if config else None
    )

    result = await llm.ainvoke(prompt, config=enriched_config)

    # Extract content
    content = result.content if hasattr(result, "content") else str(result)
    content = content.strip()

    # Clean potential markdown code blocks
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

    # Parse JSON
    try:
        parsed = json.loads(content)
        for field in required_fields:
            if field not in parsed:
                raise ContentGenerationError(f"Missing '{field}' in LLM response")
        # Return only the fields that were generated
        result_dict = {"subject": parsed["subject"]}
        if "body" in parsed:
            result_dict["body"] = parsed["body"]
        return result_dict
    except json.JSONDecodeError as e:
        logger.error("email_content_parse_error", content=content[:200], error=str(e))
        raise ContentGenerationError(f"Invalid JSON from LLM: {e}") from e


@connector_tool(
    name="send_email",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def send_email_tool(
    to: Annotated[str, "Recipient email address (or comma-separated list)"],
    subject: Annotated[
        str | None, "Email subject (optional if content_instruction provided)"
    ] = None,
    body: Annotated[
        str | None, "Email body content (optional if content_instruction provided)"
    ] = None,
    content_instruction: Annotated[
        str | None,
        "Creative content instruction for LLM generation. Use instead of subject/body for creative content (poem, story, etc.)",
    ] = None,
    cc: Annotated[str | None, "CC recipients (optional, comma-separated)"] = None,
    bcc: Annotated[str | None, "BCC recipients (optional, comma-separated)"] = None,
    is_html: Annotated[bool, "True if body is HTML, False for plain text (default False)"] = False,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Send an email via Gmail (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The email is NOT sent until the user confirms via HITL.

    Data Registry LOT 5.4: Write operations with Draft/Critique/Execute flow.

    Flow:
    1. Tool creates draft with email content (or generates it via LLM if content_instruction provided)
    2. User sees preview and can confirm/edit/cancel
    3. On confirm, email is actually sent

    Args:
        to: Recipient email address (or comma-separated list)
        subject: Email subject line (optional if content_instruction provided)
        body: Email body content (optional if content_instruction provided)
        content_instruction: Creative instruction for LLM to generate subject/body
        cc: CC recipients (optional, comma-separated)
        bcc: BCC recipients (optional, comma-separated)
        is_html: True if body is HTML, False for plain text
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and requires_confirmation=True

    Example response summary:
        "Brouillon créé: Email à jean@example.com: Confirmation RDV [draft_abc123]
         Action requise: confirmez, modifiez ou annulez."
    """
    # Get user language from runtime config (default: settings.default_language)
    user_language: SupportedLanguage = (
        runtime.config.get("configurable", {}).get("user_language", settings.default_language)
        if runtime and runtime.config
        else settings.default_language
    )

    # Determine effective content instruction:
    # 1. Use explicit content_instruction if provided
    # 2. Fallback to original user message if subject OR body is missing (not just when ALL missing)
    #    This handles cases like "send an email to X saying I am happy" where
    #    the planner provides body but not subject
    effective_content_instruction = content_instruction

    # DEBUG: Log parameters received to diagnose content resolution
    logger.debug(
        "send_email_parameters_debug",
        to=to,
        subject_provided=bool(subject),
        subject_value=subject[:50] if subject else None,
        body_provided=bool(body),
        body_value=body[:50] if body else None,
        content_instruction_provided=bool(content_instruction),
        content_instruction_value=content_instruction[:50] if content_instruction else None,
        runtime_provided=runtime is not None,
        runtime_config_keys=list(runtime.config.keys()) if runtime and runtime.config else [],
        configurable_keys=(
            list(runtime.config.get("configurable", {}).keys())
            if runtime and runtime.config
            else []
        ),
    )

    # FIX: Activate fallback when subject OR body is missing (not just when ALL are missing)
    # This handles the common case where planner provides body but not subject
    if not content_instruction and (not subject or not body) and runtime:
        user_message = get_original_user_message(runtime)
        logger.debug(
            "send_email_fallback_attempt",
            user_message_found=bool(user_message),
            user_message_length=len(user_message) if user_message else 0,
            user_message_preview=(
                user_message[:100] if user_message and len(user_message) > 100 else user_message
            ),
            missing_subject=not subject,
            missing_body=not body,
        )
        if user_message:
            effective_content_instruction = user_message
            logger.info(
                "email_content_instruction_fallback_to_user_message",
                user_message_preview=(
                    user_message[:100] if len(user_message) > 100 else user_message
                ),
                will_generate_subject=not subject,
                will_generate_body=not body,
            )

    # If content_instruction available (explicit or from user message), generate missing content via LLM
    # IMPORTANT: Preserve planner-provided values, only generate what's missing
    final_subject = subject or ""
    final_body = body or ""

    if effective_content_instruction and (not subject or not body):
        try:
            # Optimization: Pass existing body to use subject-only generation prompt
            # This is more efficient and produces better subjects based on actual body content
            # Extract user_id from runtime config for psyche context
            _email_user_id = (
                str(runtime.config.get("configurable", {}).get("user_id", ""))
                if runtime and runtime.config
                else ""
            ) or None
            generated = await _generate_email_content(
                instruction=effective_content_instruction,
                recipient=to,
                user_language=user_language,
                existing_body=body if body and not subject else None,
                config=runtime.config if runtime else None,  # Pass config for token tracking
                user_id=_email_user_id,
            )
            # Only use generated values for fields that are missing
            # This preserves planner-provided values (e.g., body) while generating missing ones (e.g., subject)
            if not subject:
                final_subject = generated.get("subject", "")
            if not body:
                final_body = generated.get("body", "")
            logger.info(
                "email_content_generated",
                instruction=(
                    effective_content_instruction[:100] if effective_content_instruction else ""
                ),
                subject_generated=not subject,
                body_generated=not body,
                subject_preview=final_subject[:50] if final_subject else "",
            )
        except ContentGenerationError as e:
            logger.error("email_content_generation_failed", error=str(e))
            return UnifiedToolOutput.failure(
                message=APIMessages.content_generation_failed(str(e), user_language),
                error_code="CONTENT_GENERATION_FAILED",
            )

    # Validate we have content
    if not final_subject or not final_body:
        return UnifiedToolOutput.failure(
            message=APIMessages.email_content_missing(user_language),
            error_code="MISSING_CONTENT",
        )

    # Delegate to draft tool instance (Data Registry mode)
    return await _send_email_draft_tool_instance.execute(
        runtime=runtime,
        to=to,
        subject=final_subject,
        body=final_body,
        cc=cc,
        bcc=bcc,
        is_html=is_html,
    )


# ============================================================================
# DRAFT EXECUTION HELPER (LOT 5.4)
# ============================================================================


async def execute_email_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an email draft: actually send the email.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    This is the execute_fn passed to DraftService.process_draft_action().
    It retrieves the Gmail client and sends the email.

    Args:
        draft_content: Dict with email content from draft
            {to, subject, body, cc, bcc, is_html}
        user_id: User UUID
        deps: ToolDependencies for getting Gmail client

    Returns:
        Dict with send result:
            {success, message_id, thread_id, to, subject, message}

    Raises:
        Exception: If email send fails
    """
    # Get email client via dynamic provider resolution
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("email", user_id, deps)

    # Send email
    result = await client.send_email(
        to=draft_content["to"],
        subject=draft_content["subject"],
        body=draft_content["body"],
        cc=draft_content.get("cc"),
        bcc=draft_content.get("bcc"),
        is_html=draft_content.get("is_html", False),
    )

    logger.info(
        "email_draft_executed",
        user_id=str(user_id),
        message_id=result.get("id"),
        to=draft_content["to"],
        subject=draft_content["subject"][:50],
    )

    return {
        "success": True,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
        "to": draft_content["to"],
        "subject": draft_content["subject"],
        "message": APIMessages.email_sent_successfully(draft_content["to"]),
    }


# ============================================================================
# TOOL 4: REPLY EMAIL (LOT 5.4 - Draft/HITL Integration)
# ============================================================================


class ReplyEmailDraftTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Reply email tool with Draft/HITL integration.

    Data Registry LOT 5.4: Write operations with confirmation flow.
    This tool creates a DRAFT (UnifiedToolOutput) that requires user confirmation before replying.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize reply email draft tool."""
        super().__init__(tool_name="reply_email_tool", operation="reply_draft")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare email reply draft data (no API call yet).

        The actual reply happens after user confirms via HITL.
        """
        message_id: str = kwargs["message_id"]
        body: str = kwargs["body"]
        reply_all: bool = kwargs.get("reply_all", False)

        if not message_id:
            raise EmailValidationError(
                APIMessages.email_field_required("message_id"),
                field="message_id",
            )
        if not body:
            raise EmailValidationError(
                APIMessages.email_field_required("body"),
                field="body",
            )

        # Get original message to show context in draft
        original = await client.get_message(message_id)
        headers = original.get("payload", {}).get("headers", [])
        header_dict = {h.get("name", "").lower(): h.get("value", "") for h in headers}

        original_subject = header_dict.get("subject", "")
        original_from = header_dict.get("from", "")

        logger.info(
            "reply_email_draft_prepared",
            user_id=str(user_id),
            message_id=message_id,
            reply_all=reply_all,
        )

        return {
            "message_id": message_id,
            "body": body,
            "reply_all": reply_all,
            "original_subject": original_subject,
            "original_from": original_from,
            "thread_id": original.get("threadId"),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create email reply draft.

        Returns UnifiedToolOutput with requires_confirmation=True.
        Includes to/subject for draft preview display.
        """
        from src.domains.agents.drafts import DraftService
        from src.domains.agents.drafts.models import EmailReplyDraftInput

        service = DraftService()

        # Build subject with Re: prefix for preview
        original_subject = result.get("original_subject", "")
        if original_subject and not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject

        # Create typed draft input for email reply
        draft_input = EmailReplyDraftInput(
            message_id=result["message_id"],
            to=result.get("original_from", ""),  # Reply to original sender
            subject=subject,  # Include subject for draft preview
            body=result["body"],
            reply_all=result["reply_all"],
            original_subject=result.get("original_subject", ""),
            original_from=result.get("original_from", ""),
            thread_id=result.get("thread_id"),
            user_language=self.get_user_language(),
        )

        # Use dedicated method for type safety
        return service.create_email_reply_draft(
            draft_input=draft_input,
            source_tool="reply_email_tool",
        )


_reply_email_draft_tool_instance = ReplyEmailDraftTool()


@connector_tool(
    name="reply_email",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def reply_email_tool(
    message_id: Annotated[str, "Original message ID to reply to (required)"],
    body: Annotated[str, "Reply message body (required)"],
    reply_all: Annotated[bool, "Reply to all recipients (default False)"] = False,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Reply to an email in Gmail (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The reply is NOT sent until the user confirms via HITL.

    Maintains the same thread as the original message.

    Args:
        message_id: Original message ID to reply to (required)
        body: Reply message body (required)
        reply_all: Reply to all recipients (default False)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and requires_confirmation=True
    """
    return await _reply_email_draft_tool_instance.execute(
        runtime=runtime,
        message_id=message_id,
        body=body,
        reply_all=reply_all,
    )


# ============================================================================
# TOOL 5: FORWARD EMAIL (LOT 5.4 - Draft/HITL Integration)
# ============================================================================


class ForwardEmailDraftTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Forward email tool with Draft/HITL integration.

    Data Registry LOT 5.4: Write operations with confirmation flow.
    This tool creates a DRAFT (UnifiedToolOutput) that requires user confirmation before forwarding.
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize forward email draft tool."""
        super().__init__(tool_name="forward_email_tool", operation="forward_draft")

    async def execute(
        self,
        runtime: ToolRuntime | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute forward email with automatic recipient resolution.

        If 'to' or 'cc' is a name instead of an email, automatically searches
        contacts to find the email address using the centralized helper.

        This enables flows like:
        - User says "forward to my wife" → memory resolves to "Jane Smith"
        - Planner uses "Jane Smith" as recipient
        - This method resolves "Jane Smith" → "jane.smith@example.com"
        """
        # Resolve recipient fields via centralized helper
        # Each field is resolved independently: "Name" → "Name <email>"
        for field in ("to", "cc"):
            value = kwargs.get(field, "")
            if value:
                resolved = await resolve_recipients_to_emails(runtime, value, field)
                if resolved:
                    kwargs[field] = resolved

        return await super().execute(runtime=runtime, **kwargs)

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare email forward draft data (no API call yet).

        The actual forward happens after user confirms via HITL.
        Includes attachment info for draft preview.
        """
        message_id: str = kwargs["message_id"]
        to: str = kwargs["to"]
        body: str | None = kwargs.get("body")
        cc: str | None = kwargs.get("cc")

        # Required fields validation
        if not message_id:
            raise EmailValidationError(
                APIMessages.email_field_required("message_id"),
                field="message_id",
            )
        if not to:
            raise EmailValidationError(
                APIMessages.email_field_required("to"),
                field="to",
            )

        # Email format validation (centralized helpers)
        _validate_email_addresses(to, "to")
        if cc:
            _validate_email_addresses(cc, "cc")

        # Get original message to show context in draft
        original = await client.get_message(message_id)
        payload = original.get("payload", {})
        headers = payload.get("headers", [])
        header_dict = {h.get("name", "").lower(): h.get("value", "") for h in headers}

        original_subject = header_dict.get("subject", "")
        original_from = header_dict.get("from", "")

        # Extract attachment info for draft preview
        # Uses the same extraction method as forward_email for consistency
        attachments_info = client._extract_attachment_info(payload)

        logger.info(
            "forward_email_draft_prepared",
            user_id=str(user_id),
            message_id=message_id,
            to=to,
            attachments_count=len(attachments_info),
        )

        return {
            "message_id": message_id,
            "to": to,
            "body": body,
            "cc": cc,
            "original_subject": original_subject,
            "original_from": original_from,
            # Include attachments for draft preview display
            "attachments": [
                {
                    "filename": att.get("filename", "attachment"),
                    "mime_type": att.get("mime_type", "application/octet-stream"),
                    "size": att.get("size", 0),
                }
                for att in attachments_info
            ],
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create email forward draft.

        Returns UnifiedToolOutput with requires_confirmation=True.
        Includes attachments info for draft preview.
        """
        from src.domains.agents.drafts import DraftService
        from src.domains.agents.drafts.models import EmailForwardDraftInput

        service = DraftService()

        # Build subject with Fwd: prefix for preview
        original_subject = result.get("original_subject", "")
        if original_subject and not original_subject.lower().startswith("fwd:"):
            subject = f"Fwd: {original_subject}"
        else:
            subject = original_subject

        # Create typed draft input for email forward
        draft_input = EmailForwardDraftInput(
            message_id=result["message_id"],
            to=result["to"],
            subject=subject,  # Include subject for draft preview
            body=result.get("body", ""),
            cc=result.get("cc"),
            original_subject=result.get("original_subject", ""),
            original_from=result.get("original_from", ""),
            # Include attachments for draft preview display
            attachments=result.get("attachments", []),
            user_language=self.get_user_language(),
        )

        # Use dedicated method for type safety
        return service.create_email_forward_draft(
            draft_input=draft_input,
            source_tool="forward_email_tool",
        )


_forward_email_draft_tool_instance = ForwardEmailDraftTool()


@connector_tool(
    name="forward_email",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def forward_email_tool(
    message_id: Annotated[str, "Original message ID to forward (required)"],
    to: Annotated[str, "Forward recipient email (required)"],
    body: Annotated[str | None, "Additional message to prepend (optional)"] = None,
    cc: Annotated[str | None, "CC recipients (optional)"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Forward an email in Gmail (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The forward is NOT sent until the user confirms via HITL.

    Creates a new thread with the forwarded message.

    Args:
        message_id: Original message ID to forward (required)
        to: Forward recipient email (required)
        body: Additional message to prepend (optional)
        cc: CC recipients (optional)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and requires_confirmation=True
    """
    return await _forward_email_draft_tool_instance.execute(
        runtime=runtime,
        message_id=message_id,
        to=to,
        body=body,
        cc=cc,
    )


# ============================================================================
# TOOL 6: DELETE EMAIL (LOT 5.4 - Draft/HITL Integration)
# ============================================================================


class DeleteEmailDraftTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """
    Delete email tool with Draft/HITL integration.

    Data Registry LOT 5.4: Destructive operations require explicit confirmation.

    This tool creates a DRAFT that requires user confirmation before moving
    the email to trash. The email is NOT deleted until user confirms via HITL.

    By default, emails are moved to TRASH (soft delete, recoverable for 30 days).
    Permanent deletion is NOT exposed through this tool for safety.

    Flow:
    1. Tool fetches email details → shows what will be deleted
    2. Creates DRAFT → UnifiedToolOutput with requires_confirmation=True
    3. Graph routes to draft_critique node
    4. User confirms/cancels via HITL
    5. On confirm: trash_email() moves to trash
    """

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize delete email draft tool."""
        super().__init__(tool_name="delete_email_tool", operation="delete_draft")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare email deletion draft data.

        First fetches email details to show user what will be deleted.
        The actual deletion happens after user confirms via HITL.
        """
        message_id: str = kwargs["message_id"]

        if not message_id:
            raise EmailValidationError(
                APIMessages.email_field_required("message_id"),
                field="message_id",
            )

        # Fetch email details to show user what will be deleted
        email = await client.get_message(message_id)
        headers = email.get("payload", {}).get("headers", [])
        header_dict = {h.get("name", "").lower(): h.get("value", "") for h in headers}

        subject = header_dict.get("subject", "(sans objet)")
        from_addr = header_dict.get("from", "")
        date = header_dict.get("date", "")

        logger.info(
            "delete_email_draft_prepared",
            user_id=str(user_id),
            message_id=message_id,
            subject=subject[:50] if len(subject) > 50 else subject,
        )

        return {
            "message_id": message_id,
            "subject": subject,
            "from": from_addr,
            "date": date,
            "thread_id": email.get("threadId"),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create email deletion draft.

        Returns UnifiedToolOutput with requires_confirmation=True.
        Shows email subject and sender so user knows what will be deleted.
        """
        from src.domains.agents.drafts import create_email_delete_draft

        # create_email_delete_draft returns UnifiedToolOutput directly
        return create_email_delete_draft(
            message_id=result["message_id"],
            subject=result.get("subject", "(sans objet)"),
            from_addr=result.get("from", ""),
            date=result.get("date", ""),
            thread_id=result.get("thread_id"),
            source_tool="delete_email_tool",
            user_language=self.get_user_language(),
        )


# Direct delete tool for execute_fn callback
class DeleteEmailDirectTool(ConnectorTool[GoogleGmailClient]):
    """Delete email that executes immediately (for HITL callback)."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"

    def __init__(self) -> None:
        super().__init__(tool_name="delete_email_direct_tool", operation="delete")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute trash email API call - moves to trash (soft delete)."""
        message_id: str = kwargs["message_id"]

        # Move to trash (soft delete, recoverable for 30 days)
        await client.trash_email(message_id)

        logger.info(
            "email_deleted_via_tool",
            user_id=str(user_id),
            message_id=message_id,
        )

        return {
            "success": True,
            "message_id": message_id,
            "message": APIMessages.email_moved_to_trash(),
        }


_delete_email_draft_tool_instance = DeleteEmailDraftTool()


@connector_tool(
    name="delete_email",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="write",
)
async def delete_email_tool(
    message_id: Annotated[str, "Message ID to delete (required)"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Delete an email in Gmail (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The email is NOT deleted until the user confirms via HITL.

    Moves the email to TRASH (soft delete). Emails in trash can be
    recovered for 30 days before permanent deletion by Gmail.

    Args:
        message_id: Gmail message ID to delete (required)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and requires_confirmation=True
    """
    return await _delete_email_draft_tool_instance.execute(
        runtime=runtime,
        message_id=message_id,
    )


# ============================================================================
# DRAFT EXECUTION HELPERS (LOT 5.4)
# ============================================================================


async def execute_email_reply_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an email reply draft: actually send the reply.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("email", user_id, deps)

    result = await client.reply_email(
        message_id=draft_content["message_id"],
        body=draft_content["body"],
        reply_all=draft_content.get("reply_all", False),
        to=draft_content.get("to"),
    )

    logger.info(
        "email_reply_draft_executed",
        user_id=str(user_id),
        message_id=result.get("id"),
        original_message_id=draft_content["message_id"],
    )

    return {
        "success": True,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
        "to": draft_content.get("to"),
        "subject": draft_content.get("subject"),
        "message": APIMessages.reply_sent_successfully(),
    }


async def execute_email_forward_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an email forward draft: actually send the forwarded email.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("email", user_id, deps)

    result = await client.forward_email(
        message_id=draft_content["message_id"],
        to=draft_content["to"],
        body=draft_content.get("body"),
        cc=draft_content.get("cc"),
    )

    logger.info(
        "email_forward_draft_executed",
        user_id=str(user_id),
        message_id=result.get("id"),
        original_message_id=draft_content["message_id"],
        to=draft_content["to"],
    )

    return {
        "success": True,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
        "to": draft_content["to"],
        "subject": draft_content.get("subject"),
        "message": APIMessages.email_forwarded_successfully(draft_content["to"]),
    }


async def execute_email_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an email delete draft: actually move email to trash.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("email", user_id, deps)

    await client.trash_email(draft_content["message_id"])

    subject = draft_content.get("subject", "(sans objet)")

    logger.info(
        "email_delete_draft_executed",
        user_id=str(user_id),
        message_id=draft_content["message_id"],
        subject=subject[:50] if len(subject) > 50 else subject,
    )

    return {
        "success": True,
        "message_id": draft_content["message_id"],
        "message": APIMessages.email_moved_to_trash(subject),
    }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Unified tool (2026-01 - replaces search + details)
    "get_emails_tool",
    "GetEmailsTool",
    # Legacy tool functions (DEPRECATED - kept for backward compatibility)
    "search_emails_tool",
    "get_email_details_tool",
    # Write operations
    "send_email_tool",
    "reply_email_tool",
    "forward_email_tool",
    "delete_email_tool",
    # Tool classes (Phase 3.2 / LOT 5.4 architecture)
    "SearchEmailsTool",
    "GetEmailDetailsTool",
    "SendEmailDraftTool",
    "SendEmailDirectTool",
    "ReplyEmailDraftTool",
    "ForwardEmailDraftTool",
    "DeleteEmailDraftTool",
    "DeleteEmailDirectTool",
    # Draft execution helpers (LOT 5.4)
    "execute_email_draft",
    "execute_email_reply_draft",
    "execute_email_forward_draft",
    "execute_email_delete_draft",
]
