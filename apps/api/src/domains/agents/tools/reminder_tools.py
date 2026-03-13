"""
Reminder Tools for LangGraph.

Provides tools for creating, listing, and canceling user reminders.
These are internal tools (no OAuth required) that use the ReminderService.

Design Decision:
    Uses @tool + decorators instead of @connector_tool because:
    - Reminders are internal operations (no external OAuth API)
    - @connector_tool is designed for Google/external API connectors
    - Simpler pattern: @tool + @track_tool_metrics + @rate_limit

Architecture (2025-12-29):
    Migrated from json.dumps() legacy format to UnifiedToolOutput.
    UnifiedToolOutput provides:
    - Explicit success/error status
    - message field for LLM response generation
    - structured_data for optional metadata
    - Compatibility with parallel_executor via summary_for_llm property

Feature (2026-01-26): Relative trigger support
    Added `relative_trigger` parameter for FOR_EACH scenarios where reminder
    time is relative to an event datetime. Format: "ISO_DATETIME|OFFSET|@TIME"
    Examples:
    - "2026-01-27T10:30:00|-1d|@19:00" → day before at 19:00
    - "2026-01-27T10:30:00|-2h" → 2 hours before (keeps original time)

Usage:
    >>> # Tools are registered in the agent's tool catalog
    >>> # User can say "remind me to X in Y"
    >>> # LLM extracts content and datetime, calls create_reminder_tool
"""

import re
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.core.constants import DEFAULT_LANGUAGE, DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_api_messages import APIMessages
from src.core.time_utils import format_datetime_for_display
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    validate_runtime_config,
)
from src.domains.agents.utils.rate_limiting import rate_limit
from src.domains.reminders.schemas import ReminderCreate
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

AGENT_NAME = "reminder_agent"
TOOL_CATEGORY_READ = 20  # 20 calls/min for read operations
TOOL_CATEGORY_WRITE = 5  # 5 calls/min for write operations
WINDOW_SECONDS = 60

# Regex pattern for relative_trigger offset parsing
# Matches: -1d, +2h, -30m, +1d, etc.
OFFSET_PATTERN = re.compile(r"^([+-])?(\d+)([dhm])$")


# =============================================================================
# Helper Functions
# =============================================================================


class RelativeTriggerError(Exception):
    """Custom exception for relative_trigger parsing errors with i18n support."""

    def __init__(self, error_type: str, value: str) -> None:
        """Initialize with error type and problematic value."""
        self.error_type = error_type
        self.value = value
        super().__init__(f"{error_type}: {value}")


def _parse_relative_trigger(relative_trigger: str, user_timezone: str) -> str:
    """
    Parse relative_trigger expression and calculate absolute datetime.

    Format: "ISO_DATETIME|OFFSET|@TIME" or "ISO_DATETIME|OFFSET"
    Also supports date-only format for all-day events: "YYYY-MM-DD|OFFSET|@TIME"

    Components:
        - ISO_DATETIME: Base datetime in ISO format (e.g., "2026-01-27T10:30:00")
                        OR date-only for all-day events (e.g., "2026-01-27")
        - OFFSET: Time offset like "-1d" (1 day before), "+2h" (2 hours after), "-30m"
        - @TIME (optional): Override time to specific hour (e.g., "@19:00")
                            REQUIRED for date-only inputs to set a meaningful time

    Examples:
        >>> _parse_relative_trigger("2026-01-27T10:30:00|-1d|@19:00", "Europe/Paris")
        "2026-01-26T19:00:00"  # Day before at 19:00

        >>> _parse_relative_trigger("2026-01-27T10:30:00|-2h", "Europe/Paris")
        "2026-01-27T08:30:00"  # 2 hours before (keeps original time)

        >>> _parse_relative_trigger("2026-01-27|-1d|@19:00", "Europe/Paris")
        "2026-01-26T19:00:00"  # All-day event: day before at 19:00

    Args:
        relative_trigger: Expression string in format "ISO|OFFSET|@TIME" or "ISO|OFFSET"
        user_timezone: User's timezone for local time interpretation

    Returns:
        ISO datetime string for the calculated trigger time

    Raises:
        RelativeTriggerError: If format is invalid or parsing fails
    """
    parts = relative_trigger.split("|")

    if len(parts) < 2 or len(parts) > 3:
        raise RelativeTriggerError("invalid_format", relative_trigger)

    base_datetime_str = parts[0].strip()
    offset_str = parts[1].strip()
    time_override = parts[2].strip() if len(parts) == 3 else None

    tz = ZoneInfo(user_timezone)

    # Parse base datetime
    try:
        # Check if it's a date-only format (all-day event: YYYY-MM-DD)
        date_only_pattern = re.match(r"^\d{4}-\d{2}-\d{2}$", base_datetime_str)

        if date_only_pattern:
            # All-day event: parse as date, set time to midnight in user's timezone
            base_dt = datetime.strptime(base_datetime_str, "%Y-%m-%d")
            # Attach timezone to naive datetime (ZoneInfo pattern)
            base_dt = base_dt.replace(tzinfo=tz)
        else:
            # Parse ISO datetime (handles both with and without timezone)
            # Replace Z with +00:00 for fromisoformat compatibility
            normalized = base_datetime_str.replace("Z", "+00:00")
            base_dt = datetime.fromisoformat(normalized)

            if base_dt.tzinfo is None:
                # No timezone - assume user's local time (attach timezone)
                base_dt = base_dt.replace(tzinfo=tz)
            else:
                # Has timezone - convert to user's local timezone
                base_dt = base_dt.astimezone(tz)
    except (ValueError, TypeError) as e:
        raise RelativeTriggerError("invalid_datetime", base_datetime_str) from e

    # Parse and apply offset
    offset_match = OFFSET_PATTERN.match(offset_str)
    if not offset_match:
        raise RelativeTriggerError("invalid_offset", offset_str)

    sign = -1 if offset_match.group(1) == "-" else 1
    amount = int(offset_match.group(2))
    unit = offset_match.group(3)

    if unit == "d":
        delta = timedelta(days=sign * amount)
    elif unit == "h":
        delta = timedelta(hours=sign * amount)
    elif unit == "m":
        delta = timedelta(minutes=sign * amount)
    else:
        raise RelativeTriggerError("invalid_offset", offset_str)

    result_dt = base_dt + delta

    # Apply time override if specified
    if time_override:
        # Accept both "@19:00" and "19:00" formats (LLM may omit the @ prefix)
        time_str = time_override[1:] if time_override.startswith("@") else time_override
        try:
            time_parts = time_str.split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise RelativeTriggerError("invalid_time", time_override)

            result_dt = result_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, IndexError) as e:
            raise RelativeTriggerError("invalid_time", time_override) from e

    # Return as ISO string (local time, no timezone suffix for consistency with trigger_datetime)
    return result_dt.strftime("%Y-%m-%dT%H:%M:%S")


async def _get_user_info(runtime: ToolRuntime) -> tuple[str, str] | None:
    """
    Get user timezone and language from database.

    Args:
        runtime: ToolRuntime with user_id in config

    Returns:
        Tuple of (timezone, language) or None if not found
    """
    try:
        user_id_raw = runtime.config.get("configurable", {}).get("user_id")
        if not user_id_raw:
            return None

        user_id = parse_user_id(user_id_raw)

        from src.domains.users.service import UserService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            user_service = UserService(db)
            user = await user_service.get_user_by_id(user_id)
            if user:
                return (
                    user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
                    user.language or DEFAULT_LANGUAGE,
                )
    except Exception as e:
        logger.warning(
            "reminder_tools_get_user_info_error",
            error=str(e),
        )

    return (DEFAULT_USER_DISPLAY_TIMEZONE, DEFAULT_LANGUAGE)


# =============================================================================
# Tools
# =============================================================================


@tool
@track_tool_metrics(
    tool_name="create_reminder",
    agent_name=AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
    log_execution=True,
    log_errors=True,
)
@rate_limit(max_calls=TOOL_CATEGORY_WRITE, window_seconds=WINDOW_SECONDS, scope="user")
async def create_reminder_tool(
    content: Annotated[str, "Ce dont l'utilisateur veut être rappelé (résumé concis)"],
    original_message: Annotated[str, "Message original complet de l'utilisateur"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    trigger_datetime: Annotated[
        str | None,
        "Date/heure ISO du rappel en heure LOCALE (ex: 2025-12-29T10:00:00). "
        "Utiliser CE paramètre pour les rappels à date fixe.",
    ] = None,
    relative_trigger: Annotated[
        str | None,
        "Expression relative pour FOR_EACH: 'ISO_DATETIME|OFFSET|@TIME'. "
        "Ex: '$item.start.dateTime|-1d|@19:00' = veille à 19h. "
        "Offset: -1d (1 jour avant), -2h (2h avant), -30m (30min avant). "
        "Utiliser CE paramètre quand le rappel est relatif à un événement.",
    ] = None,
) -> UnifiedToolOutput:
    """
    Create a reminder for the user.

    The reminder will be sent as a push notification (FCM)
    and recorded in the conversation history.

    IMPORTANT - Deux modes de déclenchement (mutuellement exclusifs):

    1. trigger_datetime (mode absolu):
       - Pour les rappels à date/heure fixe
       - Ex: "rappelle-moi demain à 9h" → trigger_datetime="2026-01-27T09:00:00"

    2. relative_trigger (mode relatif - FOR_EACH):
       - Pour les rappels relatifs à un événement (dans un for_each)
       - Format: "ISO_DATETIME|OFFSET|@TIME"
       - Ex: "la veille à 19h de chaque rdv" → relative_trigger="$item.start.dateTime|-1d|@19:00"
       - Offsets supportés: -Nd (jours), -Nh (heures), -Nm (minutes)
       - @TIME optionnel: force l'heure (ex: @19:00, @09:30)

    Args:
        content: Ce dont l'utilisateur veut être rappelé (résumé)
        original_message: La demande originale de l'utilisateur (complète)
        trigger_datetime: Quand envoyer le rappel (format ISO, heure locale) - mode absolu
        relative_trigger: Expression relative "ISO|OFFSET|@TIME" - mode FOR_EACH

    Returns:
        UnifiedToolOutput with confirmation message
    """
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    # Validate runtime config
    config = validate_runtime_config(runtime, "create_reminder_tool")
    if isinstance(config, UnifiedToolOutput):
        return config  # Return error directly

    try:
        user_id = parse_user_id(config.user_id)

        # Get user info
        user_info = await _get_user_info(runtime)
        user_timezone = user_info[0] if user_info else DEFAULT_USER_DISPLAY_TIMEZONE
        user_language = user_info[1] if user_info else DEFAULT_LANGUAGE

        # Validate: exactly one of trigger_datetime or relative_trigger must be provided
        if trigger_datetime and relative_trigger:
            return UnifiedToolOutput.failure(
                message=APIMessages.reminder_trigger_params_conflict(user_language),
                error_code="invalid_parameters",
            )

        if not trigger_datetime and not relative_trigger:
            return UnifiedToolOutput.failure(
                message=APIMessages.reminder_trigger_params_missing(user_language),
                error_code="missing_parameters",
            )

        # Calculate final trigger datetime
        if relative_trigger:
            try:
                final_trigger_datetime = _parse_relative_trigger(relative_trigger, user_timezone)
                logger.info(
                    "relative_trigger_parsed",
                    relative_trigger=relative_trigger,
                    calculated_datetime=final_trigger_datetime,
                    user_timezone=user_timezone,
                )
            except RelativeTriggerError as e:
                logger.warning(
                    "relative_trigger_parse_error",
                    relative_trigger=relative_trigger,
                    error_type=e.error_type,
                    error_value=e.value,
                )
                # Map error type to i18n message
                if e.error_type == "invalid_format":
                    message = APIMessages.relative_trigger_invalid_format(e.value, user_language)
                elif e.error_type == "invalid_datetime":
                    message = APIMessages.relative_trigger_invalid_datetime(e.value, user_language)
                elif e.error_type == "invalid_offset":
                    message = APIMessages.relative_trigger_invalid_offset(e.value, user_language)
                elif e.error_type == "invalid_time":
                    message = APIMessages.relative_trigger_invalid_time(e.value, user_language)
                else:
                    message = str(e)

                return UnifiedToolOutput.failure(
                    message=message,
                    error_code="invalid_relative_trigger",
                )
        else:
            final_trigger_datetime = trigger_datetime

        async with get_db_context() as db:
            service = ReminderService(db)

            reminder = await service.create_reminder(
                user_id=user_id,
                data=ReminderCreate(
                    content=content,
                    trigger_at=final_trigger_datetime,
                    original_message=original_message,
                ),
                user_timezone=user_timezone,
            )

            await db.commit()

            # Format confirmation in user's timezone
            formatted_time = format_datetime_for_display(
                reminder.trigger_at,
                user_timezone=user_timezone,
                locale=user_language,
            )

            logger.info(
                "create_reminder_tool_success",
                reminder_id=str(reminder.id),
                user_id=str(user_id),
                trigger_at=reminder.trigger_at.isoformat(),
                used_relative_trigger=bool(relative_trigger),
            )

            return UnifiedToolOutput.action_success(
                message=APIMessages.reminder_created(formatted_time),
                structured_data={
                    "reminder_id": str(reminder.id),
                    "content": content,
                    "trigger_at_formatted": formatted_time,
                },
            )

    except Exception as e:
        logger.error(
            "create_reminder_tool_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return UnifiedToolOutput.failure(
            message=APIMessages.reminder_creation_error(str(e)),
            error_code="reminder_creation_failed",
        )


@tool
@track_tool_metrics(
    tool_name="list_reminders",
    agent_name=AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
    log_execution=True,
    log_errors=True,
)
@rate_limit(max_calls=TOOL_CATEGORY_READ, window_seconds=WINDOW_SECONDS, scope="user")
async def list_reminders_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """
    List pending reminders for the user.

    Returns all reminders with "pending" status,
    sorted by trigger date in ascending order.

    Returns:
        UnifiedToolOutput with reminders list and formatted message
    """
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    # Validate runtime config
    config = validate_runtime_config(runtime, "list_reminders_tool")
    if isinstance(config, UnifiedToolOutput):
        return config  # Return error directly

    try:
        user_id = parse_user_id(config.user_id)

        # Get user info
        user_info = await _get_user_info(runtime)
        user_timezone = user_info[0] if user_info else DEFAULT_USER_DISPLAY_TIMEZONE
        user_language = user_info[1] if user_info else DEFAULT_LANGUAGE

        async with get_db_context() as db:
            service = ReminderService(db)
            reminders = await service.list_pending_for_user(user_id)

            if not reminders:
                return UnifiedToolOutput.action_success(
                    message=APIMessages.no_pending_reminders(user_language),
                    structured_data={"reminders": [], "total": 0},
                )

            # Build registry items for frontend rendering
            tz = ZoneInfo(user_timezone)
            registry_updates: dict[str, RegistryItem] = {}
            item_ids: list[str] = []
            item_names: list[str] = []

            for reminder in reminders:
                local_trigger = reminder.trigger_at.astimezone(tz)
                local_created = reminder.created_at.astimezone(tz)

                if user_language == "fr":
                    formatted_trigger = local_trigger.strftime("%d/%m à %H:%M")
                    formatted_created = local_created.strftime("%d/%m %H:%M")
                else:
                    formatted_trigger = local_trigger.strftime("%m/%d at %I:%M %p")
                    formatted_created = local_created.strftime("%m/%d %I:%M %p")

                # Build RegistryItem for frontend card rendering
                item_id = f"reminder_{str(reminder.id)[:8]}"
                registry_updates[item_id] = RegistryItem(
                    id=item_id,
                    type=RegistryItemType.REMINDER,
                    payload={
                        "id": str(reminder.id),
                        "content": reminder.content,
                        "trigger_at": reminder.trigger_at.isoformat(),
                        "trigger_at_formatted": formatted_trigger,
                        "created_at": reminder.created_at.isoformat(),
                        "created_at_formatted": formatted_created,
                    },
                    meta=RegistryItemMeta(
                        source="reminders",
                        domain="reminders",
                        tool_name="list_reminders_tool",
                    ),
                )
                item_ids.append(item_id)
                item_names.append(reminder.content[:50] if reminder.content else item_id)

            # Build minimal summary for LLM context
            summary = f"[reminders] {len(reminders)} rappel(s): {ToolOutputMixin._build_item_preview(item_names, max_preview=5)}"

            logger.info(
                "list_reminders_tool_success",
                user_id=str(user_id),
                total=len(reminders),
            )

            return UnifiedToolOutput.data_success(
                message=summary,
                registry_updates=registry_updates,
                metadata={
                    "tool_name": "list_reminders_tool",
                    "total_results": len(reminders),
                },
            )

    except Exception as e:
        logger.error(
            "list_reminders_tool_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return UnifiedToolOutput.failure(
            message=APIMessages.reminder_list_error(str(e)),
            error_code="reminder_list_failed",
        )


@tool
@track_tool_metrics(
    tool_name="cancel_reminder",
    agent_name=AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
    log_execution=True,
    log_errors=True,
)
@rate_limit(max_calls=TOOL_CATEGORY_WRITE, window_seconds=WINDOW_SECONDS, scope="user")
async def cancel_reminder_tool(
    reminder_identifier: Annotated[
        str,
        "ID du rappel (UUID) ou référence naturelle ('next', 'le prochain', 'prochain')",
    ],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """
    Annule un rappel en attente.

    Peut identifier le rappel par:
    - UUID direct (ex: "550e8400-e29b-41d4-a716-446655440000")
    - Référence "next", "le prochain", "prochain" pour le prochain rappel

    Args:
        reminder_identifier: ID du rappel ou description pour le résoudre

    Returns:
        UnifiedToolOutput with cancellation confirmation
    """
    from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    # Validate runtime config
    config = validate_runtime_config(runtime, "cancel_reminder_tool")
    if isinstance(config, UnifiedToolOutput):
        return config  # Return error directly

    # Get user info for language (before try block to ensure availability in except)
    user_info = await _get_user_info(runtime)
    user_language = user_info[1] if user_info else DEFAULT_LANGUAGE

    try:
        user_id = parse_user_id(config.user_id)

        async with get_db_context() as db:
            service = ReminderService(db)

            reminder = await service.resolve_and_cancel(
                user_id=user_id,
                identifier=reminder_identifier,
            )

            await db.commit()

            success_msg = APIMessages.reminder_cancelled(reminder.content, language=user_language)

            logger.info(
                "cancel_reminder_tool_success",
                reminder_id=str(reminder.id),
                user_id=str(user_id),
            )

            return UnifiedToolOutput.action_success(
                message=success_msg,
                structured_data={
                    "reminder_id": str(reminder.id),
                    "content": reminder.content,
                },
            )

    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message=APIMessages.reminder_not_found(reminder_identifier, user_language),
            error_code="not_found",
        )

    except ResourceConflictError as e:
        return UnifiedToolOutput.failure(
            message=str(e),
            error_code="conflict",
        )

    except Exception as e:
        logger.error(
            "cancel_reminder_tool_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return UnifiedToolOutput.failure(
            message=APIMessages.reminder_cancel_error(str(e)),
            error_code="reminder_cancel_failed",
        )


# =============================================================================
# Tool Catalog Export
# =============================================================================

REMINDER_TOOLS = [
    create_reminder_tool,
    list_reminders_tool,
    cancel_reminder_tool,
]

__all__ = [
    "REMINDER_TOOLS",
    "cancel_reminder_tool",
    "create_reminder_tool",
    "list_reminders_tool",
]
