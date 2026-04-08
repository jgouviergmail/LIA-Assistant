"""
Reminder Tools for LangGraph.

Provides tools for creating, listing, and canceling user reminders.
These are internal tools (no OAuth required) that use the ReminderService.

Architecture:
    Uses @write_tool / @read_tool decorator presets (same as connector tools)
    with @with_user_preferences for centralized user timezone/language injection.
    Although reminders are internal (no external API client), the decorator
    pattern and output format align with the standard ConnectorTool conventions.

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
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_api_messages import APIMessages
from src.core.time_utils import format_datetime_for_display
from src.domains.agents.constants import (
    AGENT_REMINDER,
    CONTEXT_DOMAIN_REMINDERS,
)
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.tools.decorators import read_tool, with_user_preferences, write_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    validate_runtime_config,
)
from src.domains.reminders.schemas import ReminderCreate

logger = structlog.get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

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
    """Parse relative_trigger expression and calculate absolute datetime.

    Format: "ISO_DATETIME|OFFSET|@TIME" or "ISO_DATETIME|OFFSET"
    Also supports date-only format for all-day events: "YYYY-MM-DD|OFFSET|@TIME"

    Components:
        - ISO_DATETIME: Base datetime in ISO format (e.g., "2026-01-27T10:30:00")
                        OR date-only for all-day events (e.g., "2026-01-27")
        - OFFSET: Time offset like "-1d" (1 day before), "+2h" (2 hours after), "-30m"
        - @TIME (optional): Override time to specific hour (e.g., "@19:00")
                            REQUIRED for date-only inputs to set a meaningful time

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
            base_dt = base_dt.replace(tzinfo=tz)
        else:
            # Parse ISO datetime (handles both with and without timezone)
            normalized = base_datetime_str.replace("Z", "+00:00")
            base_dt = datetime.fromisoformat(normalized)

            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=tz)
            else:
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

    # Return as ISO string (local time, no timezone suffix for consistency)
    return result_dt.strftime("%Y-%m-%dT%H:%M:%S")


# =============================================================================
# Tools
# =============================================================================


@write_tool(name="create_reminder", agent_name=AGENT_REMINDER)
@with_user_preferences
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
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Create a reminder for the user.

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

    Args:
        content: Ce dont l'utilisateur veut être rappelé (résumé)
        original_message: La demande originale de l'utilisateur (complète)
        trigger_datetime: Quand envoyer le rappel (format ISO, heure locale) - mode absolu
        relative_trigger: Expression relative "ISO|OFFSET|@TIME" - mode FOR_EACH
        user_timezone: User timezone (injected by @with_user_preferences)
        locale: User language (injected by @with_user_preferences)

    Returns:
        UnifiedToolOutput with confirmation message
    """
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    # Validate runtime config
    config = validate_runtime_config(runtime, "create_reminder_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        user_id = parse_user_id(config.user_id)

        # Validate: exactly one of trigger_datetime or relative_trigger
        if trigger_datetime and relative_trigger:
            return UnifiedToolOutput.failure(
                message=APIMessages.reminder_trigger_params_conflict(locale),
                error_code="invalid_parameters",
            )

        if not trigger_datetime and not relative_trigger:
            return UnifiedToolOutput.failure(
                message=APIMessages.reminder_trigger_params_missing(locale),
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
                error_messages = {
                    "invalid_format": APIMessages.relative_trigger_invalid_format,
                    "invalid_datetime": APIMessages.relative_trigger_invalid_datetime,
                    "invalid_offset": APIMessages.relative_trigger_invalid_offset,
                    "invalid_time": APIMessages.relative_trigger_invalid_time,
                }
                msg_fn = error_messages.get(e.error_type)
                message = msg_fn(e.value, locale) if msg_fn else str(e)

                return UnifiedToolOutput.failure(
                    message=message,
                    error_code="invalid_relative_trigger",
                )
        else:
            from src.core.time_utils import normalize_user_datetime

            final_trigger_datetime = (
                normalize_user_datetime(trigger_datetime, user_timezone) or trigger_datetime
            )

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

            formatted_time = format_datetime_for_display(
                reminder.trigger_at,
                user_timezone=user_timezone,
                locale=locale,
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


@read_tool(name="list_reminders", agent_name=AGENT_REMINDER)
@with_user_preferences
async def list_reminders_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    locale: str = "fr",
) -> UnifiedToolOutput:
    """List pending reminders for the user.

    Returns all reminders with "pending" status,
    sorted by trigger date in ascending order.

    Args:
        runtime: LangChain tool runtime.
        user_timezone: User timezone (injected by @with_user_preferences).
        locale: User language (injected by @with_user_preferences).

    Returns:
        UnifiedToolOutput with reminders list and formatted message
    """
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    # Validate runtime config
    config = validate_runtime_config(runtime, "list_reminders_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        user_id = parse_user_id(config.user_id)

        async with get_db_context() as db:
            service = ReminderService(db)
            reminders = await service.list_pending_for_user(user_id)

            if not reminders:
                return UnifiedToolOutput.action_success(
                    message=APIMessages.no_pending_reminders(locale),
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

                formatted_trigger = format_datetime_for_display(
                    local_trigger,
                    user_timezone=user_timezone,
                    locale=locale,
                )
                formatted_created = format_datetime_for_display(
                    local_created,
                    user_timezone=user_timezone,
                    locale=locale,
                )

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
                        source=CONTEXT_DOMAIN_REMINDERS,
                        domain=CONTEXT_DOMAIN_REMINDERS,
                        tool_name="list_reminders_tool",
                    ),
                )
                item_ids.append(item_id)
                item_names.append(reminder.content[:50] if reminder.content else item_id)

            summary = (
                f"[{CONTEXT_DOMAIN_REMINDERS}] {len(reminders)} rappel(s): "
                f"{ToolOutputMixin._build_item_preview(item_names, max_preview=5)}"
            )

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


@write_tool(name="cancel_reminder", agent_name=AGENT_REMINDER)
@with_user_preferences
async def cancel_reminder_tool(
    reminder_identifier: Annotated[
        str,
        "ID du rappel (UUID) ou référence naturelle ('next', 'le prochain', 'prochain')",
    ],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Cancel a pending reminder (creates draft for user confirmation).

    Identifies the reminder, fetches its details, and creates a deletion
    draft that requires user confirmation via HITL before actual cancellation.

    Args:
        reminder_identifier: Reminder UUID or natural reference ('next', etc.)
        runtime: LangChain tool runtime.
        user_timezone: User timezone (injected by @with_user_preferences).
        locale: User language (injected by @with_user_preferences).

    Returns:
        UnifiedToolOutput with DRAFT RegistryItem (requires_confirmation=True)
    """
    from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
    from src.domains.agents.drafts import create_reminder_delete_draft
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    # Validate runtime config
    config = validate_runtime_config(runtime, "cancel_reminder_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        user_id = parse_user_id(config.user_id)

        async with get_db_context() as db:
            service = ReminderService(db)

            # Resolve the reminder (find by ID or natural reference) WITHOUT cancelling
            reminder = await service.resolve_reminder(
                user_id=user_id,
                identifier=reminder_identifier,
            )

            logger.info(
                "cancel_reminder_draft_prepared",
                reminder_id=str(reminder.id),
                user_id=str(user_id),
                content=reminder.content[:50] if reminder.content else "",
            )

            # Create draft for user confirmation (actual cancellation after HITL)
            return create_reminder_delete_draft(
                reminder_id=str(reminder.id),
                content=reminder.content or "",
                trigger_at=reminder.trigger_at.isoformat() if reminder.trigger_at else "",
                source_tool="cancel_reminder_tool",
                user_language=locale,
            )

    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message=APIMessages.reminder_not_found(reminder_identifier, locale),
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
# Draft Executor (HITL callback)
# =============================================================================


async def execute_reminder_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Execute a reminder delete draft: actually cancel the reminder.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    Args:
        draft_content: Draft content with reminder_id, content, trigger_at.
        user_id: User UUID.
        deps: ToolDependencies (unused for internal reminders).

    Returns:
        Result dict with success status and message.
    """
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    reminder_id_str = draft_content["reminder_id"]
    content = draft_content.get("content", "")

    async with get_db_context() as db:
        service = ReminderService(db)
        await service.cancel_reminder(
            user_id=user_id,
            reminder_id=UUID(reminder_id_str),
        )
        await db.commit()

    logger.info(
        "reminder_delete_draft_executed",
        user_id=str(user_id),
        reminder_id=reminder_id_str,
    )

    return {
        "success": True,
        "reminder_id": reminder_id_str,
        "message": APIMessages.reminder_cancelled(content),
    }


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
    "execute_reminder_delete_draft",
    "list_reminders_tool",
]
