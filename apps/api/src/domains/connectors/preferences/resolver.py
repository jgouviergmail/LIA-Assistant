"""
Generic preference resolver with case-insensitive name matching.

Resolves user-configured preference names (e.g., "Famille") to API IDs
(e.g., "calendar_id_123") with case-insensitive matching.

Architecture:
    - PreferenceResolver: Generic resolver supporting any connector type
    - Pluggable fetchers: Each connector registers how to fetch its items
    - Case-insensitive: "Famille" = "famille" = "FAMILLE"

Usage:
    >>> resolver = PreferenceResolver()
    >>> calendar_id = await resolver.resolve_calendar_name(
    ...     client, "famille"  # User typed lowercase
    ... )
    >>> print(calendar_id)  # Returns ID of calendar named "Famille"
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class ResolvedItem:
    """Result of name resolution."""

    id: str
    name: str
    exact_match: bool  # True if case matched exactly


class NameResolverStrategy(ABC, Generic[T]):  # noqa: UP046
    """
    Abstract strategy for resolving names to IDs.

    Each connector type implements its own strategy for fetching
    available items and extracting name/ID pairs.
    """

    @abstractmethod
    async def fetch_items(self, client: T) -> list[dict[str, Any]]:
        """Fetch available items from the API."""
        ...

    @abstractmethod
    def get_item_name(self, item: dict[str, Any]) -> str:
        """Extract the display name from an item."""
        ...

    @abstractmethod
    def get_item_id(self, item: dict[str, Any]) -> str:
        """Extract the ID from an item."""
        ...


class GoogleCalendarNameResolver(NameResolverStrategy[Any]):
    """Resolver for Google Calendar names."""

    async def fetch_items(self, client: Any) -> list[dict[str, Any]]:
        """Fetch calendar list from Google Calendar API."""
        response = await client.list_calendars(max_results=100)
        return response.get("items", [])

    def get_item_name(self, item: dict[str, Any]) -> str:
        """Calendar name is in 'summary' field."""
        return item.get("summary", "")

    def get_item_id(self, item: dict[str, Any]) -> str:
        """Calendar ID is in 'id' field."""
        return item.get("id", "")


class AppleCalendarNameResolver(NameResolverStrategy[Any]):
    """Resolver for Apple Calendar names (CalDAV)."""

    async def fetch_items(self, client: Any) -> list[dict[str, Any]]:
        """Fetch calendar list from CalDAV (same interface as Google)."""
        response = await client.list_calendars(max_results=100)
        return response.get("items", [])

    def get_item_name(self, item: dict[str, Any]) -> str:
        """Calendar name is in 'summary' field (normalized format)."""
        return item.get("summary", "")

    def get_item_id(self, item: dict[str, Any]) -> str:
        """Calendar ID is in 'id' field (CalDAV URL)."""
        return item.get("id", "")


class GoogleTasksListNameResolver(NameResolverStrategy[Any]):
    """Resolver for Google Tasks list names."""

    async def fetch_items(self, client: Any) -> list[dict[str, Any]]:
        """Fetch task lists from Google Tasks API."""
        response = await client.list_task_lists(max_results=100)
        return response.get("items", [])

    def get_item_name(self, item: dict[str, Any]) -> str:
        """Task list name is in 'title' field."""
        return item.get("title", "")

    def get_item_id(self, item: dict[str, Any]) -> str:
        """Task list ID is in 'id' field."""
        return item.get("id", "")


class MicrosoftCalendarNameResolver(NameResolverStrategy[Any]):
    """Resolver for Microsoft Calendar names."""

    async def fetch_items(self, client: Any) -> list[dict[str, Any]]:
        """Fetch calendar list from Microsoft Graph API (normalized format)."""
        response = await client.list_calendars(max_results=100)
        return response.get("items", [])

    def get_item_name(self, item: dict[str, Any]) -> str:
        """Calendar name is in 'summary' field (normalized from Microsoft)."""
        return item.get("summary", "")

    def get_item_id(self, item: dict[str, Any]) -> str:
        """Calendar ID is in 'id' field."""
        return item.get("id", "")


class MicrosoftTasksListNameResolver(NameResolverStrategy[Any]):
    """Resolver for Microsoft To Do task list names."""

    async def fetch_items(self, client: Any) -> list[dict[str, Any]]:
        """Fetch task lists from Microsoft To Do API (normalized format)."""
        response = await client.list_task_lists(max_results=100)
        return response.get("items", [])

    def get_item_name(self, item: dict[str, Any]) -> str:
        """Task list name is in 'title' field (normalized from Microsoft)."""
        return item.get("title", "")

    def get_item_id(self, item: dict[str, Any]) -> str:
        """Task list ID is in 'id' field."""
        return item.get("id", "")


class PreferenceNameResolver:
    """
    Generic preference resolver with case-insensitive matching.

    Resolves user-configured names to API IDs by:
    1. Fetching available items from the API
    2. Matching by name (case-insensitive)
    3. Returning the corresponding ID

    Example:
        >>> resolver = PreferenceNameResolver()
        >>> # User configured "famille" but calendar is named "Famille"
        >>> calendar_id = await resolver.resolve(
        ...     client=calendar_client,
        ...     name="famille",
        ...     strategy=GoogleCalendarNameResolver(),
        ... )
        >>> print(calendar_id.id)  # Returns actual calendar ID
    """

    @staticmethod
    async def resolve(
        client: Any,
        name: str,
        strategy: NameResolverStrategy[Any],
        fallback_id: str | None = None,
    ) -> ResolvedItem | None:
        """
        Resolve a name to an ID using case-insensitive matching.

        Args:
            client: API client instance (GoogleCalendarClient, GoogleTasksClient, etc.)
            name: User-configured name to resolve
            strategy: Resolution strategy for the connector type
            fallback_id: ID to return if name not found (e.g., "primary", "@default")

        Returns:
            ResolvedItem with ID and match info, or None if not found and no fallback
        """
        if not name:
            if fallback_id:
                return ResolvedItem(id=fallback_id, name="", exact_match=False)
            return None

        try:
            items = await strategy.fetch_items(client)

            # Normalize search name for case-insensitive comparison
            name_lower = name.lower().strip()

            # First pass: exact case match
            for item in items:
                item_name = strategy.get_item_name(item)
                if item_name == name:
                    item_id = strategy.get_item_id(item)
                    logger.debug(
                        "preference_name_resolved_exact",
                        name=name,
                        resolved_id=item_id,
                    )
                    return ResolvedItem(id=item_id, name=item_name, exact_match=True)

            # Second pass: case-insensitive match
            for item in items:
                item_name = strategy.get_item_name(item)
                if item_name.lower().strip() == name_lower:
                    item_id = strategy.get_item_id(item)
                    logger.debug(
                        "preference_name_resolved_case_insensitive",
                        name=name,
                        resolved_name=item_name,
                        resolved_id=item_id,
                    )
                    return ResolvedItem(id=item_id, name=item_name, exact_match=False)

            # Not found
            logger.warning(
                "preference_name_not_found",
                name=name,
                available_count=len(items),
            )

            if fallback_id:
                return ResolvedItem(id=fallback_id, name="", exact_match=False)
            return None

        except Exception as e:
            logger.error(
                "preference_name_resolution_failed",
                name=name,
                error=str(e),
            )
            if fallback_id:
                return ResolvedItem(id=fallback_id, name="", exact_match=False)
            return None


# Convenience functions for common use cases


async def resolve_calendar_name(
    client: Any,
    name: str | None,
    fallback: str = "primary",
) -> str:
    """
    Resolve calendar name to calendar ID (case-insensitive).

    Works with both Google Calendar and Apple Calendar clients
    (both implement the same list_calendars interface).

    Args:
        client: Calendar client instance (Google or Apple).
        name: User-configured calendar name (e.g., "Famille") or calendar ID.
        fallback: Fallback ID if not found (default: "primary").

    Returns:
        Calendar ID string.
    """
    if not name:
        return fallback

    # If it's already a valid calendar ID, return it directly
    # Google Calendar IDs: "primary", "user@gmail.com", "abc@group.calendar.google.com"
    # Apple CalDAV IDs: URLs starting with "https://"
    if name == "primary" or "@" in name or name.startswith("https://"):
        logger.debug(
            "calendar_id_already_valid",
            input=name,
            reason="recognized as ID format",
        )
        return name

    # Determine which resolver strategy to use based on provider
    provider_prefix = ""
    if hasattr(client, "connector_type"):
        provider_prefix = getattr(client.connector_type, "value", "")

    if provider_prefix.startswith("apple_"):
        strategy: NameResolverStrategy[Any] = AppleCalendarNameResolver()
    elif provider_prefix.startswith("microsoft_"):
        strategy = MicrosoftCalendarNameResolver()
    else:
        strategy = GoogleCalendarNameResolver()

    result = await PreferenceNameResolver.resolve(
        client=client,
        name=name,
        strategy=strategy,
        fallback_id=fallback,
    )
    return result.id if result else fallback


async def resolve_task_list_name(
    client: Any,
    name: str | None,
    fallback: str = "@default",
) -> str:
    """
    Resolve task list name to task list ID (case-insensitive).

    Works with both Google Tasks and Microsoft To Do clients
    (both implement the same list_task_lists interface).

    Args:
        client: Tasks client instance (Google Tasks or Microsoft To Do).
        name: User-configured task list name (e.g., "My Tasks")
        fallback: Fallback ID if not found (default: "@default")

    Returns:
        Task list ID string
    """
    if not name:
        return fallback

    # Determine strategy based on provider
    provider_prefix = ""
    if hasattr(client, "connector_type"):
        provider_prefix = getattr(client.connector_type, "value", "")

    strategy: NameResolverStrategy[Any] = (
        MicrosoftTasksListNameResolver()
        if provider_prefix.startswith("microsoft_")
        else GoogleTasksListNameResolver()
    )

    result = await PreferenceNameResolver.resolve(
        client=client,
        name=name,
        strategy=strategy,
        fallback_id=fallback,
    )
    return result.id if result else fallback


__all__ = [
    "AppleCalendarNameResolver",
    "GoogleCalendarNameResolver",
    "GoogleTasksListNameResolver",
    "MicrosoftCalendarNameResolver",
    "MicrosoftTasksListNameResolver",
    "NameResolverStrategy",
    "PreferenceNameResolver",
    "ResolvedItem",
    "resolve_calendar_name",
    "resolve_task_list_name",
]
