"""
Tool Output Mixins.

INTELLIA v10: Simplified architecture.
- ToolOutputMixin: Builds registry_updates only
- Formatting handled by response_node._simplify_*_payload() + fewshots
- summary_for_llm is minimal (debug/logs only)

TIMEZONE HANDLING:
- All build_*_output() methods accept user_timezone and locale parameters
- Date fields in payloads use ISO format (YYYY-MM-DD or ISO 8601 datetime)
- Display formatting (user language) is handled by card components via format_full_date()

Usage:
    class SearchContactsTool(ToolOutputMixin, ConnectorTool):
        def format_registry_response(self, result: dict) -> UnifiedToolOutput:
            return self.build_contacts_output(
                contacts=result["contacts"],
                query=result.get("query"),
                user_timezone=result.get("user_timezone", "UTC"),
                locale=result.get("locale", "fr"),
            )
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from src.core.config import settings
from src.core.time_utils import (
    convert_email_dates_in_payload,
    convert_event_dates_in_payload,
    convert_file_dates_in_payload,
    convert_task_dates_in_payload,
    convert_weather_dates_in_payload,
)
from src.domains.agents.constants import (
    CONTEXT_DOMAIN_CONTACTS,
    CONTEXT_DOMAIN_EMAILS,
    CONTEXT_DOMAIN_EVENTS,
    CONTEXT_DOMAIN_FILES,
    CONTEXT_DOMAIN_PLACES,
    CONTEXT_DOMAIN_TASKS,
    CONTEXT_DOMAIN_WEATHER,
)
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput

logger = structlog.get_logger(__name__)


class ToolOutputMixin:
    """
    Mixin that adds registry capabilities to existing tools.

    Provides helper methods for creating registry items and
    building UnifiedToolOutput responses.

    Attributes:
        tool_name: Should be set by the parent class
        operation: Should be set by the parent class
        runtime: Should be set by the parent ConnectorTool class

    Example:
        class SearchContactsTool(ToolOutputMixin, ConnectorTool):
            def format_response(self, result: dict) -> UnifiedToolOutput:
                return self.build_contacts_output(
                    contacts=result["contacts"],
                    query=result.get("query"),
                )
    """

    # These should be set by the parent ConnectorTool class
    tool_name: str = "unknown_tool"
    operation: str = "unknown"
    runtime: Any = None  # Set by ConnectorTool.execute() before calling format_registry_response

    def get_user_language(self, default: str | None = None) -> str:
        """
        Extract user_language from runtime config.

        Used by draft creation tools to localize HITL content in user's language.
        The runtime is stored on the instance by ConnectorTool.execute() before
        calling execute_api_call() and format_registry_response().

        Args:
            default: Default language if not found in config (uses settings.default_language if None)

        Returns:
            User's language code (fr, en, es, de, it, zh-CN)
        """
        fallback = default if default is not None else settings.default_language
        if self.runtime and self.runtime.config:
            return self.runtime.config.get("configurable", {}).get("user_language", fallback)
        return fallback

    def create_registry_item(
        self,
        item_type: RegistryItemType,
        unique_key: str,
        payload: dict[str, Any],
        source: str,
        domain: str | None = None,
        step_id: str | None = None,
    ) -> tuple[str, RegistryItem]:
        """
        Create a registry item with auto-generated ID.

        Args:
            item_type: Type of the item (CONTACT, EMAIL, etc.)
            unique_key: Unique identifier from source system
            payload: Complete data for the item
            source: Source system name
            domain: Optional domain context
            step_id: Optional execution step ID

        Returns:
            Tuple of (item_id, RegistryItem)
        """
        item_id = generate_registry_id(item_type, unique_key)

        item = RegistryItem(
            id=item_id,
            type=item_type,
            payload=payload,
            meta=RegistryItemMeta(
                source=source,
                domain=domain,
                tool_name=self.tool_name,
                step_id=step_id,
            ),
        )

        return item_id, item

    @staticmethod
    def _build_item_preview(
        items: list[str],
        max_preview: int = 3,
        max_name_len: int = 50,
    ) -> str:
        """Build a preview string from a list of item names/IDs.

        Args:
            items: List of item identifiers or names.
            max_preview: Max items to show inline (default 3).
            max_name_len: Max length per name before truncation (default 50).

        Returns:
            Formatted string like "item1, item2, item3 (+2 more)".
        """
        if not items:
            return ""
        truncated = [
            (name[: max_name_len - 3] + "..." if len(name) > max_name_len else name)
            for name in items[:max_preview]
        ]
        preview = ", ".join(truncated)
        if len(items) > max_preview:
            preview += f" (+{len(items) - max_preview} more)"
        return preview

    def build_standard_output(
        self,
        items: list[dict[str, Any]],
        item_type: RegistryItemType,
        source: str,
        unique_key_field: str,
        summary_template: str = "Found {count} items",
        preview_field: str | None = None,
        preview_limit: int = 3,
        domain: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UnifiedToolOutput:
        """
        Build a UnifiedToolOutput from a list of items.

        Args:
            items: List of item dicts from API
            item_type: Type for all items
            source: Source system name
            unique_key_field: Field name containing unique ID
            summary_template: Template with {count} and optional {preview}
            preview_field: Field to use for preview (e.g., "name")
            preview_limit: Max items to show in preview
            domain: Optional domain context
            metadata: Optional tool metadata

        Returns:
            UnifiedToolOutput with items in registry and summary for LLM
        """
        registry_updates: dict[str, RegistryItem] = {}
        preview_parts: list[str] = []

        for idx, item in enumerate(items, 1):
            # Add 1-based index for ordinal reference resolution
            item["index"] = idx

            unique_key = item.get(unique_key_field, str(id(item)))
            item_id, registry_item = self.create_registry_item(
                item_type=item_type,
                unique_key=unique_key,
                payload=item,
                source=source,
                domain=domain,
            )
            registry_updates[item_id] = registry_item

            # Build preview for summary
            if preview_field and len(preview_parts) < preview_limit:
                preview_value = item.get(preview_field, "")
                if preview_value:
                    preview_parts.append(f"{preview_value} ({item_id})")

        # Build summary
        preview = ", ".join(preview_parts) if preview_parts else ""
        if len(items) > preview_limit:
            preview += f", ... (+{len(items) - preview_limit} more)"

        summary = summary_template.format(count=len(items), preview=preview)

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata=metadata or {},
        )

    def build_places_output(
        self,
        places: list[dict[str, Any]],
        query: str | None = None,
        from_cache: bool = False,
        operation: str | None = None,
        center: dict[str, float] | None = None,
        radius: int | None = None,
    ) -> UnifiedToolOutput:
        """
        Build UnifiedToolOutput for places results.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_place_payload() + fewshots.

        Args:
            places: List of place dicts from Google Places API
            query: Original search query
            from_cache: Whether results came from cache
            operation: Operation type ('search', 'list', 'nearby', 'details')
            center: Optional center coordinates for nearby search
            radius: Optional radius for nearby search

        Returns:
            UnifiedToolOutput with places in registry and minimal summary for debug
        """
        op = operation or getattr(self, "operation", "search")
        registry_updates: dict[str, RegistryItem] = {}
        item_ids: list[str] = []
        item_names: list[str] = []

        for idx, place in enumerate(places, 1):
            place_id = place.get("id")
            if not place_id:
                continue

            # Add place_id alias for consistency with get_place_details_tool parameter
            # (same pattern as contacts with resource_name)
            if "place_id" not in place:
                place["place_id"] = place_id

            # Add 1-based index for ordinal reference resolution
            place["index"] = idx

            item_id, registry_item = self.create_registry_item(
                item_type=RegistryItemType.PLACE,
                unique_key=place_id,
                payload=place,
                source="google_places",
                domain=CONTEXT_DOMAIN_PLACES,
            )
            registry_updates[item_id] = registry_item
            item_ids.append(item_id)
            item_names.append(place.get("displayName", {}).get("text") or item_id)

        # Build summary with radius info for response_node
        # IMPORTANT: For nearby search, radius MUST be mentioned in response
        summary_parts = [f"[{op}] {len(places)} place(s)"]

        # Add radius info for nearby search (MANDATORY to mention in response)
        if radius is not None and op == "nearby":
            radius_km = radius / 1000
            if radius_km >= 1:
                radius_str = f"{radius_km:.0f} km"
            else:
                radius_str = f"{radius} m"

            # Clear instruction for response_node
            summary_parts.append(f"RAYON_RECHERCHE={radius_str}")
            summary_parts.append("INSTRUCTION: Mentionner le rayon dans la réponse")

            # Add hint to widen radius if no results
            if len(places) == 0:
                summary_parts.append("AUCUN_RESULTAT: Suggérer d'élargir le rayon")

        if item_names:
            summary_parts.append(f"items: {self._build_item_preview(item_names)}")

        summary = " | ".join(summary_parts)

        # Build metadata with human-readable radius
        metadata: dict[str, Any] = {
            "from_cache": from_cache,
            "query": query,
            "operation": op,
            "total_count": len(places),
            "center": center,
            "radius": radius,
        }

        # Add human-readable radius for nearby searches
        if radius is not None and op == "nearby":
            radius_km = radius / 1000
            if radius_km >= 1:
                metadata["radius_used"] = f"{radius_km:.0f} km"
            else:
                metadata["radius_used"] = f"{radius} m"

        logger.debug(
            "build_places_output",
            query=query,
            places_count=len(places),
            operation=op,
            radius_used=metadata.get("radius_used"),
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata=metadata,
        )

    # =========================================================================
    # Type-specific convenience methods
    # INTELLIA v10: Simplified - only builds registry_updates.
    # Formatting is handled by response_node._simplify_*_payload() + fewshots.
    # =========================================================================

    def build_contacts_output(
        self,
        contacts: list[dict[str, Any]],
        query: str | None = None,
        from_cache: bool = False,
        operation: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Build UnifiedToolOutput for contact results.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_contact_payload() + fewshots.

        Args:
            contacts: List of contact dicts from Google People API
            query: Original search query
            from_cache: Whether results came from cache
            operation: Operation type ('search', 'list', 'details')

        Returns:
            UnifiedToolOutput with contacts in registry and minimal summary for debug
        """
        op = operation or getattr(self, "operation", "search")
        registry_updates: dict[str, RegistryItem] = {}
        item_ids: list[str] = []
        item_names: list[str] = []

        for idx, contact in enumerate(contacts, 1):
            resource_name = contact.get("resourceName", "")
            if not resource_name:
                continue

            # Add resource_name alias for backwards compatibility with Jinja templates
            if "resource_name" not in contact:
                contact["resource_name"] = resource_name

            # Add 1-based index for ordinal reference resolution
            contact["index"] = idx

            item_id, registry_item = self.create_registry_item(
                item_type=RegistryItemType.CONTACT,
                unique_key=resource_name,
                payload=contact,
                source="google_contacts",
                domain=CONTEXT_DOMAIN_CONTACTS,
            )
            registry_updates[item_id] = registry_item
            item_ids.append(item_id)
            item_names.append(
                ((contact.get("names") or [{}])[0] or {}).get("displayName") or item_id
            )

        # Minimal summary for debug/logs only (not displayed to user)
        summary = f"[{op}] {len(contacts)} contact(s): {self._build_item_preview(item_names)}"

        logger.debug(
            "build_contacts_output",
            query=query,
            contacts_count=len(contacts),
            operation=op,
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata={
                "from_cache": from_cache,
                "query": query,
                "operation": op,
                "total_count": len(contacts),
            },
        )

    def build_emails_output(
        self,
        emails: list[dict[str, Any]],
        query: str | None = None,
        from_cache: bool = False,
        user_timezone: str = "UTC",
        locale: str = settings.default_language,
    ) -> UnifiedToolOutput:
        """
        Build UnifiedToolOutput for email search results.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_email_payload() + fewshots.

        TIMEZONE: Converts internalDate to user's timezone with formatted display string.

        Args:
            emails: List of email dicts from Gmail API
            query: Original search query
            from_cache: Whether results came from cache
            user_timezone: User's IANA timezone (e.g., "Europe/Paris")
            locale: User's locale for date formatting (e.g., "fr", "en")

        Returns:
            UnifiedToolOutput with emails in registry and minimal summary for debug
        """
        registry_updates: dict[str, RegistryItem] = {}
        item_ids: list[str] = []
        item_names: list[str] = []

        for idx, email in enumerate(emails, 1):
            message_id = email.get("id", "")
            if not message_id:
                continue

            # Add message_id alias for consistency with get_email_details_tool parameter
            # (same pattern as contacts with resource_name)
            if "message_id" not in email:
                email["message_id"] = message_id

            # Add 1-based index for ordinal reference resolution
            email["index"] = idx

            # Promote subject to top-level for Jinja/reference_examples access
            # Gmail stores subject in payload.headers; Apple Mail may have it top-level
            if "subject" not in email:
                subject = next(
                    (
                        h.get("value", "")
                        for h in email.get("payload", {}).get("headers", [])
                        if h.get("name", "").lower() == "subject"
                    ),
                    "",
                )
                email["subject"] = subject

            # Convert dates to user's timezone
            convert_email_dates_in_payload(email, user_timezone, locale)

            item_id, registry_item = self.create_registry_item(
                item_type=RegistryItemType.EMAIL,
                unique_key=message_id,
                payload=email,
                source="gmail",
                domain=CONTEXT_DOMAIN_EMAILS,
            )
            registry_updates[item_id] = registry_item
            item_ids.append(item_id)
            item_names.append(email.get("subject") or item_id)

        # Minimal summary for debug/logs only (not displayed to user)
        summary = f"[search] {len(emails)} email(s): {self._build_item_preview(item_names)}"

        logger.debug(
            "build_emails_output",
            query=query,
            emails_count=len(emails),
            user_timezone=user_timezone,
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata={
                "from_cache": from_cache,
                "query": query,
                "total_count": len(emails),
                "user_timezone": user_timezone,
            },
        )

    def build_events_output(
        self,
        events: list[dict[str, Any]],
        query: str | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
        from_cache: bool = False,
        user_timezone: str = "UTC",
        locale: str = settings.default_language,
        calendar_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Build UnifiedToolOutput for calendar event search results.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_event_payload() + fewshots.

        TIMEZONE: Converts start/end times to user's timezone with formatted display strings.

        Args:
            events: List of event dicts from Google Calendar API
            query: Original search query (optional)
            time_min: Start of time range filter (optional)
            time_max: End of time range filter (optional)
            from_cache: Whether results came from cache
            user_timezone: User's IANA timezone (e.g., "Europe/Paris")
            locale: User's locale for date formatting (e.g., "fr", "en")
            calendar_id: Calendar ID where events were found (for update/delete operations)

        Returns:
            UnifiedToolOutput with events in registry and minimal summary for debug
        """
        registry_updates: dict[str, RegistryItem] = {}
        item_ids: list[str] = []
        item_names: list[str] = []

        for idx, event in enumerate(events, 1):
            event_id = event.get("id", "")
            if not event_id:
                continue

            # Normalize all-day events: add synthetic dateTime at 00:00:00 with timezone
            # This allows plans to use $steps.*.start.dateTime consistently
            # CRITICAL: Include user's timezone so parse_datetime interprets correctly
            # (Without TZ, naive datetimes are interpreted as UTC - see time_utils.py:200)
            start = event.get("start", {})
            end = event.get("end", {})
            if "date" in start and "dateTime" not in start:
                # All-day event: synthesize dateTime from date at midnight in user's timezone
                # Format: 2025-02-22T00:00:00+01:00 (with offset)
                try:
                    tz = ZoneInfo(user_timezone)
                    # Parse date and create datetime at midnight in user's timezone
                    naive_dt = datetime.strptime(start["date"], "%Y-%m-%d")
                    local_dt = naive_dt.replace(hour=0, minute=0, second=0, tzinfo=tz)
                    start["dateTime"] = local_dt.isoformat()
                except (KeyError, ValueError) as e:
                    # Fallback: use UTC if timezone is invalid
                    logger.warning(
                        "all_day_event_tz_fallback",
                        event_id=event_id,
                        user_timezone=user_timezone,
                        error=str(e),
                    )
                    start["dateTime"] = f"{start['date']}T00:00:00Z"

                logger.debug(
                    "normalized_all_day_event_start",
                    event_id=event_id,
                    summary=event.get("summary", ""),
                    date=start["date"],
                    synthesized_dateTime=start["dateTime"],
                    user_timezone=user_timezone,
                )
            if "date" in end and "dateTime" not in end:
                # All-day event end: synthesize dateTime at 23:59:59 in user's timezone
                try:
                    tz = ZoneInfo(user_timezone)
                    naive_dt = datetime.strptime(end["date"], "%Y-%m-%d")
                    local_dt = naive_dt.replace(hour=23, minute=59, second=59, tzinfo=tz)
                    end["dateTime"] = local_dt.isoformat()
                except (KeyError, ValueError):
                    end["dateTime"] = f"{end['date']}T23:59:59Z"

            # Add 1-based index for ordinal reference resolution
            event["index"] = idx

            # Add event_id alias for consistency with get_event_details_tool parameter
            # (same pattern as contacts with resource_name)
            if "event_id" not in event:
                event["event_id"] = event_id

            # CRITICAL: Add calendar_id to each event for update/delete operations
            # Without this, update_event_tool won't know which calendar contains the event
            if calendar_id:
                event["calendar_id"] = calendar_id

            # Log original event dates before conversion for debugging
            start_before = event.get("start", {}).get(
                "dateTime", event.get("start", {}).get("date", "")
            )

            # Convert dates to user's timezone
            convert_event_dates_in_payload(event, user_timezone, locale)

            # Add top-level date alias for cross-domain binding (weather.date, routes.arrival_time)
            # LLM does name-based binding: $item.date is easier than $item.start.dateTime
            # MUST be set AFTER convert_event_dates_in_payload so it contains the
            # user-timezone-aware ISO string, not the raw UTC value from Google API.
            if start.get("dateTime"):
                event["date"] = start["dateTime"]

            # Log after conversion for debugging
            start_after = event.get("start", {}).get("formatted", "")
            logger.debug(
                "event_date_conversion",
                event_id=event_id,
                summary=event.get("summary", ""),
                start_before=start_before,
                start_after=start_after,
                user_timezone=user_timezone,
                locale=locale,
            )

            item_id, registry_item = self.create_registry_item(
                item_type=RegistryItemType.EVENT,
                unique_key=event_id,
                payload=event,
                source="google_calendar",
                domain=CONTEXT_DOMAIN_EVENTS,  # "events" - matches result_key in domain_taxonomy
            )
            registry_updates[item_id] = registry_item
            item_ids.append(item_id)
            item_names.append(event.get("summary") or item_id)

        # Minimal summary for debug/logs only (not displayed to user)
        summary = f"[search] {len(events)} event(s): {self._build_item_preview(item_names)}"

        logger.debug(
            "build_events_output",
            query=query,
            events_count=len(events),
            user_timezone=user_timezone,
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata={
                "from_cache": from_cache,
                "query": query,
                "time_min": time_min,
                "time_max": time_max,
                "total_count": len(events),
                "user_timezone": user_timezone,
            },
        )

    def build_tasks_output(
        self,
        tasks: list[dict[str, Any]],
        task_list_id: str | None = None,
        from_cache: bool = False,
        user_timezone: str = "UTC",
        locale: str = settings.default_language,
    ) -> UnifiedToolOutput:
        """
        Build UnifiedToolOutput for task results.

        TIMEZONE: Converts due/completed dates to user's timezone with formatted display strings.

        Args:
            tasks: List of task dicts from Google Tasks API
            task_list_id: Task list ID (optional)
            from_cache: Whether results came from cache
            user_timezone: User's IANA timezone (e.g., "Europe/Paris")
            locale: User's locale for date formatting (e.g., "fr", "en")

        Returns:
            UnifiedToolOutput with tasks in registry and minimal summary for debug
        """
        registry_updates: dict[str, RegistryItem] = {}
        item_ids: list[str] = []
        item_names: list[str] = []

        for idx, task in enumerate(tasks, 1):
            task_id = task.get("id", "")
            if not task_id:
                continue

            # Add 1-based index for ordinal reference resolution
            task["index"] = idx

            # Add task_id alias for consistency with get_task_details_tool parameter
            # (same pattern as contacts with resource_name)
            if "task_id" not in task:
                task["task_id"] = task_id

            # Add tasklist_id to each task for update/delete/complete operations
            # (same pattern as calendar_id for events)
            if task_list_id and "tasklist_id" not in task:
                task["tasklist_id"] = task_list_id

            # Convert dates to user's timezone
            convert_task_dates_in_payload(task, user_timezone, locale)

            item_id, registry_item = self.create_registry_item(
                item_type=RegistryItemType.TASK,
                unique_key=task_id,
                payload=task,
                source="google_tasks",
                domain=CONTEXT_DOMAIN_TASKS,
            )
            registry_updates[item_id] = registry_item
            item_ids.append(item_id)
            item_names.append(task.get("title") or item_id)

        # Minimal summary for debug/logs only (not displayed to user)
        summary = f"[list] {len(tasks)} task(s): {self._build_item_preview(item_names)}"

        logger.debug(
            "build_tasks_output",
            tasks_count=len(tasks),
            task_list_id=task_list_id,
            user_timezone=user_timezone,
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata={
                "from_cache": from_cache,
                "task_list_id": task_list_id,
                "total_count": len(tasks),
                "user_timezone": user_timezone,
            },
        )

    def build_files_output(
        self,
        files: list[dict[str, Any]],
        query: str | None = None,
        folder_id: str | None = None,
        from_cache: bool = False,
        user_timezone: str = "UTC",
        locale: str = settings.default_language,
    ) -> UnifiedToolOutput:
        """
        Build UnifiedToolOutput for Drive file results.

        TIMEZONE: Converts modifiedTime/createdTime to user's timezone with formatted display strings.

        Args:
            files: List of file dicts from Google Drive API
            query: Original search query (optional)
            folder_id: Folder ID for listing (optional)
            from_cache: Whether results came from cache
            user_timezone: User's IANA timezone (e.g., "Europe/Paris")
            locale: User's locale for date formatting (e.g., "fr", "en")

        Returns:
            UnifiedToolOutput with files in registry and minimal summary for debug
        """
        registry_updates: dict[str, RegistryItem] = {}
        item_ids: list[str] = []
        item_names: list[str] = []

        for idx, file in enumerate(files, 1):
            file_id = file.get("id", "")
            if not file_id:
                continue

            # Add file_id alias for consistency with get_file_details_tool parameter
            # (same pattern as contacts with resource_name - see line 315)
            if "file_id" not in file:
                file["file_id"] = file_id

            # Add 1-based index for ordinal reference resolution
            # (e.g., "the second one" → index=2)
            file["index"] = idx

            # Convert dates to user's timezone
            convert_file_dates_in_payload(file, user_timezone, locale)

            item_id, registry_item = self.create_registry_item(
                item_type=RegistryItemType.FILE,
                unique_key=file_id,
                payload=file,
                source="google_drive",
                domain=CONTEXT_DOMAIN_FILES,  # "files" - matches result_key in domain_taxonomy
            )
            registry_updates[item_id] = registry_item
            item_ids.append(item_id)
            item_names.append(file.get("name") or item_id)

        # Minimal summary for debug/logs only (not displayed to user)
        summary = f"[search] {len(files)} file(s): {self._build_item_preview(item_names)}"

        logger.debug(
            "build_files_output",
            query=query,
            files_count=len(files),
            folder_id=folder_id,
            user_timezone=user_timezone,
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata={
                "from_cache": from_cache,
                "query": query,
                "folder_id": folder_id,
                "total_count": len(files),
                "user_timezone": user_timezone,
            },
        )

    def build_weather_output(
        self,
        weather_data: dict[str, Any],
        location: str | None = None,
        from_cache: bool = False,
        user_timezone: str = "UTC",
        locale: str = settings.default_language,
    ) -> UnifiedToolOutput:
        """
        Build UnifiedToolOutput for weather results.

        TIMEZONE: Converts dt/sunrise/sunset timestamps to user's timezone.

        Args:
            weather_data: Weather data dict from OpenWeatherMap API
            location: Location query (optional)
            from_cache: Whether results came from cache
            user_timezone: User's IANA timezone (e.g., "Europe/Paris")
            locale: User's locale for date formatting (e.g., "fr", "en")

        Returns:
            UnifiedToolOutput with weather in registry and minimal summary for debug
        """
        registry_updates: dict[str, RegistryItem] = {}

        # Convert dates to user's timezone
        convert_weather_dates_in_payload(weather_data, user_timezone, locale)

        # Generate unique key from location or coordinates
        unique_key = location or f"{weather_data.get('coord', {})}"
        item_id, registry_item = self.create_registry_item(
            item_type=RegistryItemType.WEATHER,
            unique_key=unique_key,
            payload=weather_data,
            source="openweathermap",
            domain=CONTEXT_DOMAIN_WEATHER,  # "weathers" - matches result_key in domain_taxonomy
        )
        registry_updates[item_id] = registry_item

        # Minimal summary for debug/logs only
        city_name = weather_data.get("name", location or "Unknown")
        summary = f"[weather] {city_name}: {item_id}"

        logger.debug(
            "build_weather_output",
            location=location,
            city_name=city_name,
            user_timezone=user_timezone,
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata={
                "from_cache": from_cache,
                "location": location,
                "user_timezone": user_timezone,
            },
        )


def create_tool_formatter(
    item_type: RegistryItemType,
    source: str,
    unique_key_field: str,
    preview_field: str,
    domain: str | None = None,
) -> Callable[[list[dict[str, Any]], str | None], UnifiedToolOutput]:
    """
    Factory function to create a formatter for any item type.

    Returns a function that converts a list of items to UnifiedToolOutput.

    Args:
        item_type: Type of items
        source: Source system name
        unique_key_field: Field containing unique ID
        preview_field: Field to use for preview
        domain: Optional domain context

    Returns:
        Formatter function

    Example:
        format_events = create_tool_formatter(
            item_type=RegistryItemType.EVENT,
            source="google_calendar",
            unique_key_field="id",
            preview_field="summary",
            domain=CONTEXT_DOMAIN_EVENTS,  # "events" - use constant from constants.py
        )

        output = format_events(events, query="meeting")
    """

    def formatter(
        items: list[dict[str, Any]],
        query: str | None = None,
    ) -> UnifiedToolOutput:
        registry_updates: dict[str, RegistryItem] = {}
        preview_parts: list[str] = []

        for item in items:
            unique_key = item.get(unique_key_field, str(id(item)))
            item_id = generate_registry_id(item_type, unique_key)

            registry_item = RegistryItem(
                id=item_id,
                type=item_type,
                payload=item,
                meta=RegistryItemMeta(source=source, domain=domain),
            )
            registry_updates[item_id] = registry_item

            if len(preview_parts) < 3:
                preview_value = item.get(preview_field, "")
                if preview_value:
                    preview_parts.append(f"{preview_value} ({item_id})")

        preview = ", ".join(preview_parts)
        if len(items) > 3:
            preview += f", ... (+{len(items) - 3} more)"

        type_name = item_type.value.lower() + "s"
        query_part = f" matching '{query}'" if query else ""
        summary = f"Found {len(items)} {type_name}{query_part}: {preview}"

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
        )

    return formatter
