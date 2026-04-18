"""
Generic Tool Context Manager for LangGraph BaseStore.

Provides CRUD operations for tool context management with zero tool-specific code.
All operations are configuration-driven via ContextTypeRegistry.

Architecture (two-keys design, 2026-04):
    - Hierarchical namespaces: (user_id, session_id, "context", domain)
    - Two keys per domain:
        * "list" → ToolContextList (results of last bulk operation, overwrite behavior)
        * "current" → ToolContextCurrentItem (single focused item)
    - Auto-enrichment: Adds "index" field to all items
    - Type-safe: Uses Pydantic schemas for validation
    - Auto-set current_item: When 1 result → automatic selection
    - Session isolation: Each conversation has its own context
    - Explicit save mode: Tools opt into LIST, CURRENT, or NONE via UnifiedToolOutput

Write Rules:
    - Search/list operations → LIST (overwrite, auto-manage current)
    - Direct ID fetch (single) → CURRENT only (LIST preserved)
    - Direct ID fetch (batch) → CURRENT=clear (LIST preserved)
    - Create/Update via HITL → set_current_item() directly
    - Delete via HITL → remove_item_from_list() directly

Usage:
    manager = ToolContextManager()

    # Save list (overwrites existing, auto-sets current_item if 1 result)
    await manager.save_list(
        user_id="user123",
        session_id="sess456",
        domain="contacts",
        items=[{"resource_name": "...", "name": "..."}],
        metadata={FIELD_TURN_ID: 5, ...},
        store=store
    )

    # Get list
    context_list = await manager.get_list(
        user_id="user123",
        session_id="sess456",
        domain="contacts",
        store=store
    )

    # Set current item explicitly
    await manager.set_current_item(
        user_id="user123",
        session_id="sess456",
        domain="contacts",
        item={"index": 2, "name": "Marie", ...},
        set_by="explicit",
        turn_id=5,
        store=store
    )

    # Get current item
    current = await manager.get_current_item(
        user_id="user123",
        session_id="sess456",
        domain="contacts",
        store=store
    )
"""

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from src.core.config import settings
from src.core.field_names import (
    FIELD_INDEX,
    FIELD_METADATA,
    FIELD_QUERY,
    FIELD_TIMESTAMP,
    FIELD_TOOL_NAME,
    FIELD_TURN_ID,
    FIELD_USER_ID,
)
from src.domains.agents.context.registry import ContextTypeRegistry
from src.domains.agents.context.schemas import (
    ContextMetadata,
    ContextSaveMode,
    ToolContextCurrentItem,
    ToolContextList,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.profiling import profile_performance

logger = get_logger(__name__)


class ToolContextManager:
    """
    Generic manager for domain-based context persistence in LangGraph BaseStore.

    All methods are 100% generic - work for ANY domain (contacts, emails, events).
    Configuration is driven by ContextTypeRegistry.

    Example:
        >>> manager = ToolContextManager()
        >>> await manager.save_list(
        ...     user_id="user123",
        ...     domain="contacts",
        ...     items=[...],
        ...     metadata={...},
        ...     store=store
        ... )
    """

    @staticmethod
    def _build_namespace(user_id: str, session_id: str, domain: str) -> tuple[str, ...]:
        """
        Build hierarchical namespace for Store isolation.

        Namespace structure (Phase 5 - Session Isolation):
            (user_id, session_id, "context", domain)

        Examples:
            ("user123", "sess456", "context", "contacts")
            ("user456", "sess789", "context", "emails")

        Benefits:
            - User isolation (different users can't see each other)
            - Session isolation (NEW: each conversation has its own context)
            - Domain isolation (contacts != emails)
            - Efficient cleanup (delete by namespace prefix)
            - Scalable (adding domains doesn't change structure)

        Args:
            user_id: User UUID or identifier.
            session_id: Session UUID for conversation isolation.
            domain: Domain identifier ("contacts", "emails", "events").

        Returns:
            Tuple namespace for BaseStore.aput/aget operations.
        """
        return (str(user_id), str(session_id), "context", domain)

    @staticmethod
    def _apply_intelligent_truncation(
        items: list[dict[str, Any]], max_items: int, domain: str
    ) -> list[dict[str, Any]]:
        """
        Apply intelligent truncation to keep most valuable context items.

        Strategy: Keep 70% most recent items + 30% highest confidence items.
        This preserves both recency and quality while preventing memory bloat.

        Args:
            items: List of items to truncate (NOT yet indexed).
            max_items: Maximum number of items to keep (from settings.tool_context_max_items).
            domain: Domain identifier for logging.

        Returns:
            Truncated list of items (maintains original order).

        Example:
            >>> items = [{"name": "A", "confidence": 0.9}, ...]  # 200 items
            >>> truncated = _apply_intelligent_truncation(items, 100, "contacts")
            >>> len(truncated)  # 100
            >>> # Result: 70 most recent + 30 highest confidence (deduplicated)
        """
        if len(items) <= max_items:
            return items  # No truncation needed

        # Strategy: 70% most recent, 30% highest confidence
        recent_count = int(max_items * 0.7)
        high_conf_count = max_items - recent_count

        # Most recent items (preserve order - already sorted by tool result)
        recent_items = items[-recent_count:]  # Last N items (most recent)

        # Highest confidence items (from items NOT in recent selection)
        remaining = items[:-recent_count] if recent_count > 0 else items

        # Sort by confidence if available, otherwise use first items as fallback
        def get_confidence(item: dict[str, Any]) -> float:
            """Extract confidence score, default to settings if missing."""
            # Try common confidence field names
            for key in ["confidence", "score", "relevance", "rank"]:
                if key in item and isinstance(item[key], int | float):
                    return float(item[key])
            return settings.default_item_confidence

        sorted_by_conf = sorted(remaining, key=get_confidence, reverse=True)
        high_conf_items = sorted_by_conf[:high_conf_count]

        # Combine and restore original order
        # Use set of ids/keys to deduplicate if items have unique identifiers
        selected_items = recent_items + high_conf_items

        # Restore original order based on position in source list
        item_to_index = {id(item): idx for idx, item in enumerate(items)}
        selected_items.sort(key=lambda x: item_to_index[id(x)])

        # Log truncation event
        logger.warning(
            "context_items_truncated",
            domain=domain,
            original_count=len(items),
            truncated_count=len(selected_items),
            removed_count=len(items) - len(selected_items),
            max_items=max_items,
            recent_kept=recent_count,
            high_conf_kept=high_conf_count,
            strategy="70_recent_30_confidence",
        )

        return selected_items

    # ==========================================
    # LIST OPERATIONS
    # ==========================================

    async def save_list(
        self,
        user_id: str | UUID,
        session_id: str,
        domain: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any],
        store: BaseStore,
    ) -> None:
        """
        Save list of items for a domain (overwrites existing).

        Rules:
        - Items are automatically enriched with "index" field (1-based)
        - If len(items) == 1 → Auto-set current_item (set_by="auto")
        - If len(items) > 1 → Clear current_item (ambiguous)
        - If len(items) == 0 → Clear both list and current_item

        Args:
            user_id: User UUID or identifier.
            session_id: Session UUID for conversation isolation.
            domain: Domain identifier ("contacts", "emails", "events").
            items: List of items from tool result (NOT yet indexed).
            metadata: Metadata dict (turn_id, query, tool_name, etc.).
            store: LangGraph BaseStore instance.

        Raises:
            ValueError: If domain not registered in ContextTypeRegistry.

        Example:
            >>> await manager.save_list(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="contacts",
            ...     items=[
            ...         {"resource_name": "people/c123", "name": "Jean Dupond"},
            ...         {"resource_name": "people/c456", "name": "Marie Martin"}
            ...     ],
            ...     metadata={
            ...         FIELD_TURN_ID: 5,
            ...         "total_count": 2,
            ...         "query": "liste mes contacts",
            ...         "tool_name": "search_contacts_tool",
            ...         FIELD_TIMESTAMP: "2025-01-26T14:30:00Z"
            ...     },
            ...     store=store
            ... )

        Store Result:
            Namespace: ("user123", "sess456", "context", "contacts")
            Key "list": ToolContextList with indexed items
            Key "current": ToolContextCurrentItem (if 1 item) or deleted (if > 1)
        """
        # Validate domain exists in registry
        ContextTypeRegistry.get_definition(domain)

        namespace = self._build_namespace(str(user_id), session_id, domain)

        # Edge case: Empty list → Clear everything
        if not items:
            await store.adelete(namespace, "list")
            await self.clear_current_item(user_id, session_id, domain, store)
            logger.info(
                "empty_list_cleared", user_id=str(user_id), session_id=session_id, domain=domain
            )
            return

        # Apply intelligent truncation if items exceed max limit
        max_items = settings.tool_context_max_items
        if len(items) > max_items:
            items = self._apply_intelligent_truncation(items, max_items, domain)

        # Enrich items with index (1-based)
        indexed_items = [{**item, FIELD_INDEX: idx} for idx, item in enumerate(items, 1)]

        # Parse metadata to ContextMetadata
        context_metadata = ContextMetadata(
            turn_id=metadata.get(FIELD_TURN_ID, 0),
            total_count=len(indexed_items),
            query=metadata.get(FIELD_QUERY),
            tool_name=metadata.get(FIELD_TOOL_NAME),
            timestamp=metadata.get(FIELD_TIMESTAMP, datetime.now(UTC).isoformat()),
        )

        # Build ToolContextList
        context_list = ToolContextList(
            domain=domain,
            items=indexed_items,
            metadata=context_metadata,
        )

        # Save list to Store
        await store.aput(namespace, "list", context_list.model_dump())

        logger.info(
            "list_saved",
            user_id=str(user_id),
            domain=domain,
            items_count=len(indexed_items),
            turn_id=context_metadata.turn_id,
            tool_name=context_metadata.tool_name,
        )

        # ✅ AUTO-SET current_item if EXACTLY 1 result
        if len(indexed_items) == 1:
            await self.set_current_item(
                user_id=user_id,
                session_id=session_id,
                domain=domain,
                item=indexed_items[0],
                set_by="auto",
                turn_id=context_metadata.turn_id,
                store=store,
            )
            logger.info(
                "current_item_auto_set",
                user_id=str(user_id),
                session_id=session_id,
                domain=domain,
                reason="single_result",
            )
        else:
            # Multiple items → Clear current_item (ambiguous)
            await self.clear_current_item(user_id, session_id, domain, store)
            # Debug log removed - hot path, clearing logic is clear from code

    async def get_list(
        self,
        user_id: str | UUID,
        session_id: str,
        domain: str,
        store: BaseStore,
    ) -> ToolContextList | None:
        """
        Retrieve list of items for a domain.

        Args:
            user_id: User UUID or identifier.
            session_id: Session UUID for conversation isolation.
            domain: Domain identifier ("contacts", "emails", "events").
            store: LangGraph BaseStore instance.

        Returns:
            ToolContextList if exists, None otherwise.

        Example:
            >>> context_list = await manager.get_list(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="contacts",
            ...     store=store
            ... )
            >>> if context_list:
            ...     print(f"Found {len(context_list.items)} items")
        """
        namespace = self._build_namespace(str(user_id), session_id, domain)

        item = await store.aget(namespace, "list")

        if not item:
            # Debug log removed - not actionable, already tracked by context usage metrics
            return None

        try:
            context_list = ToolContextList(**item.value)
            # Debug log removed - hot path, adds overhead without value
            return context_list

        except Exception as e:
            logger.error(
                "list_parse_error",
                user_id=str(user_id),
                domain=domain,
                error=str(e),
                exc_info=True,
            )
            return None

    # ==========================================
    # CURRENT ITEM OPERATIONS
    # ==========================================

    async def set_current_item(
        self,
        user_id: str | UUID,
        session_id: str,
        domain: str,
        item: dict[str, Any],
        set_by: Literal["auto", "explicit"],
        turn_id: int,
        store: BaseStore,
    ) -> None:
        """
        Set current item for a domain.

        Args:
            user_id: User UUID or identifier.
            session_id: Session UUID for conversation isolation.
            domain: Domain identifier.
            item: Complete item dict (must include "index" field).
            set_by: "auto" (1 result auto-set) or "explicit" (user selected).
            turn_id: Turn ID when item is set.
            store: LangGraph BaseStore instance.

        Example:
            >>> await manager.set_current_item(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="contacts",
            ...     item={"index": 2, "name": "Marie Martin", ...},
            ...     set_by="explicit",
            ...     turn_id=5,
            ...     store=store
            ... )
        """
        namespace = self._build_namespace(str(user_id), session_id, domain)

        current_item = ToolContextCurrentItem(
            domain=domain,
            item=item,
            set_at=datetime.now(UTC).isoformat(),
            set_by=set_by,
            turn_id=turn_id,
        )

        await store.aput(namespace, "current", current_item.model_dump())

        logger.info(
            "current_item_set",
            user_id=str(user_id),
            domain=domain,
            item_index=item.get(FIELD_INDEX),
            set_by=set_by,
            turn_id=turn_id,
        )

    async def get_current_item(
        self,
        user_id: str | UUID,
        session_id: str,
        domain: str,
        store: BaseStore,
    ) -> dict[str, Any] | None:
        """
        Retrieve current item for a domain.

        Args:
            user_id: User UUID or identifier.
            session_id: Session UUID for conversation isolation.
            domain: Domain identifier.
            store: LangGraph BaseStore instance.

        Returns:
            Complete item dict if current_item exists, None otherwise.

        Example:
            >>> current = await manager.get_current_item(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="contacts",
            ...     store=store
            ... )
            >>> if current:
            ...     print(f"Current item: {current.get('name')}")
        """
        namespace = self._build_namespace(str(user_id), session_id, domain)

        item = await store.aget(namespace, "current")

        if not item:
            # Debug log removed - hot path, None return is self-explanatory
            return None

        try:
            current = ToolContextCurrentItem(**item.value)
            # Debug log removed - hot path, adds overhead for every context retrieval
            return current.item

        except Exception as e:
            logger.error(
                "current_item_parse_error",
                user_id=str(user_id),
                domain=domain,
                error=str(e),
                exc_info=True,
            )
            return None

    async def remove_item_from_list(
        self,
        user_id: str | UUID,
        session_id: str,
        domain: str,
        item_id: str,
        store: BaseStore,
    ) -> bool:
        """Remove a specific item from the list context (e.g., after confirmed deletion).

        Reads the current list, removes the item matching item_id on the domain's
        primary_id_field, reindexes remaining items, and saves back. Also clears
        current_item if it was the deleted item.

        Args:
            user_id: User UUID or identifier.
            session_id: Session UUID for conversation isolation.
            domain: Domain identifier (e.g., "contacts", "emails").
            item_id: ID value of the item to remove (matched against primary_id_field).
            store: LangGraph BaseStore instance.

        Returns:
            True if item was found and removed, False if not found.

        Example:
            >>> removed = await manager.remove_item_from_list(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="emails",
            ...     item_id="msg_abc123",
            ...     store=store,
            ... )
        """
        namespace = self._build_namespace(str(user_id), session_id, domain)

        try:
            # Get current list
            existing = await store.aget(namespace, "list")
            if not existing or not existing.value:
                return False

            context_list = ToolContextList(**existing.value)
            definition = ContextTypeRegistry.get_definition(domain)
            primary_id_field = definition.primary_id_field

            # Find and remove the item
            original_count = len(context_list.items)
            filtered_items = [
                item for item in context_list.items if item.get(primary_id_field) != item_id
            ]

            if len(filtered_items) == original_count:
                # Item not found
                return False

            # Reindex remaining items (1-based)
            reindexed = [{**item, FIELD_INDEX: i + 1} for i, item in enumerate(filtered_items)]

            # Update and save
            context_list.items = reindexed
            context_list.metadata.total_count = len(reindexed)
            await store.aput(namespace, "list", context_list.model_dump())

            # Clear current_item if it was the deleted item
            current = await store.aget(namespace, "current")
            if current and current.value:
                current_item_data = current.value.get("item", {})
                if current_item_data.get(primary_id_field) == item_id:
                    await self.clear_current_item(user_id, session_id, domain, store)

            logger.info(
                "item_removed_from_list",
                user_id=str(user_id),
                domain=domain,
                removed_count=original_count - len(reindexed),
                remaining_count=len(reindexed),
            )
            return True

        except Exception:
            logger.exception(
                "remove_item_from_list_failed",
                user_id=str(user_id),
                domain=domain,
            )
            return False

    async def update_item_in_list(
        self,
        user_id: str | UUID,
        session_id: str,
        domain: str,
        item_id: str,
        updated_item: dict[str, Any],
        store: BaseStore,
    ) -> bool:
        """Update a specific item in the list context (e.g., after confirmed update).

        Reads the current list, finds the item by primary_id_field, replaces its
        payload in place while preserving its 1-based "index" field. Does NOT
        touch other items or change the list size. If the item is not found in
        the list, it is a no-op (returns False).

        Symmetrical to remove_item_from_list() — both operate on LIST entries
        by primary_id_field and preserve the overall list structure.

        Args:
            user_id: User UUID or identifier.
            session_id: Session UUID for conversation isolation.
            domain: Domain identifier (e.g., "events", "contacts").
            item_id: ID value matched against primary_id_field.
            updated_item: Full replacement item dict (without "index" — preserved).
            store: LangGraph BaseStore instance.

        Returns:
            True if item was found and updated, False if not in list.

        Example:
            >>> updated = await manager.update_item_in_list(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="events",
            ...     item_id="evt_abc",
            ...     updated_item={"id": "evt_abc", "summary": "new title", ...},
            ...     store=store,
            ... )
        """
        namespace = self._build_namespace(str(user_id), session_id, domain)

        try:
            existing = await store.aget(namespace, "list")
            if not existing or not existing.value:
                return False

            context_list = ToolContextList(**existing.value)
            definition = ContextTypeRegistry.get_definition(domain)
            primary_id_field = definition.primary_id_field

            # Locate and replace in place, preserving the "index" field
            replaced = False
            new_items: list[dict[str, Any]] = []
            for item in context_list.items:
                if item.get(primary_id_field) == item_id:
                    preserved_index = item.get(FIELD_INDEX)
                    merged = {**updated_item}
                    if preserved_index is not None:
                        merged[FIELD_INDEX] = preserved_index
                    new_items.append(merged)
                    replaced = True
                else:
                    new_items.append(item)

            if not replaced:
                return False

            context_list.items = new_items
            await store.aput(namespace, "list", context_list.model_dump())

            logger.info(
                "item_updated_in_list",
                user_id=str(user_id),
                domain=domain,
                item_id=item_id,
            )
            return True

        except Exception:
            logger.exception(
                "update_item_in_list_failed",
                user_id=str(user_id),
                domain=domain,
                item_id=item_id,
            )
            return False

    async def clear_current_item(
        self,
        user_id: str | UUID,
        session_id: str,
        domain: str,
        store: BaseStore,
    ) -> None:
        """
        Clear current item for a domain (called when list becomes ambiguous).

        Args:
            user_id: User UUID or identifier.
            session_id: Session UUID for conversation isolation.
            domain: Domain identifier.
            store: LangGraph BaseStore instance.

        Example:
            >>> await manager.clear_current_item(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="contacts",
            ...     store=store
            ... )
        """
        namespace = self._build_namespace(str(user_id), session_id, domain)

        try:
            await store.adelete(namespace, "current")
            logger.debug(
                "current_item_cleared",
                user_id=str(user_id),
                domain=domain,
            )
        except Exception:
            # Ignore if current_item doesn't exist
            pass

    # ==========================================
    # MULTI-DOMAIN OPERATIONS
    # ==========================================

    async def list_active_domains(
        self, user_id: str | UUID, session_id: str, store: BaseStore
    ) -> list[dict[str, Any]]:
        """
        List all active domains for a user in the current session.

        Active domain = has list with items AND/OR has current_item.

        Returns:
            List of domain summaries with metadata:
            [
                {
                    "domain": "contacts",
                    "items_count": 5,
                    "current_item": {...} or None,
                    "last_query": "...",
                    FIELD_TURN_ID: 5,
                    FIELD_TIMESTAMP: "..."
                }
            ]

        Note:
            V1 implementation uses Registry iteration (acceptable for InMemoryStore).
            V2 with PostgresStore will use store.alist_namespaces() for better performance.

        Example:
            >>> active = await manager.list_active_domains("user123", "sess456", store)
            >>> # [{"domain": "contacts", "items_count": 10, ...}]
        """
        active_domains = []

        # Iterate over all registered domains
        for domain in ContextTypeRegistry.list_all():
            context_list = await self.get_list(user_id, session_id, domain, store)

            if context_list and context_list.items:
                current_item = await self.get_current_item(user_id, session_id, domain, store)

                active_domains.append(
                    {
                        "domain": domain,
                        "items_count": len(context_list.items),
                        "current_item": current_item,
                        "last_query": context_list.metadata.query,
                        FIELD_TURN_ID: context_list.metadata.turn_id,
                        FIELD_TIMESTAMP: context_list.metadata.timestamp,
                    }
                )

        # Debug log removed - hot path, return value is self-documenting
        return active_domains

    # ==========================================
    # AUTO-SAVE DISPATCH
    # ==========================================

    async def auto_save(
        self,
        context_type: str,
        result_data: dict[str, Any],
        config: RunnableConfig,
        store: BaseStore,
        explicit_mode: ContextSaveMode | None = None,
    ) -> None:
        """Auto-save context from tool result (called by @auto_save_context decorator).

        Routes to save_list() or set_current_item() based on explicit_mode.
        LIST → overwrite list + auto-manage current.
        CURRENT → set current only when N=1, clear current when N>1, never touch list.
        NONE → no-op.

        Convention:
            Tool result must have key "{domain}s" (plural) in its data payload.
            Example: domain="contacts" → result["contacts"], domain="event" → result["events"].

        Args:
            context_type: Context type identifier (maps to domain).
            result_data: Parsed result from tool (dict). May be wrapped in {"data": {...}}.
            config: RunnableConfig with user_id and metadata.
            store: LangGraph BaseStore instance.
            explicit_mode: Save mode from UnifiedToolOutput.context_save_mode.
                If None, defaults to LIST (conservative).
        """
        logger.info(
            "auto_save_entered",
            context_type=context_type,
            result_data_keys=list(result_data.keys()),
            has_store=store is not None,
            config_keys=list(config.keys()) if config else [],
            tool_name=result_data.get(FIELD_TOOL_NAME),
        )

        domain = context_type

        # Validate domain exists (raises ValueError if not found)
        try:
            _ = ContextTypeRegistry.get_definition(domain)
        except ValueError as e:
            logger.error("auto_save_domain_invalid", domain=domain, error=str(e))
            return

        # Extract items from result
        # ToolResponse may wrap data in {"success": bool, "data": {...}}
        data_payload = result_data.get("data", result_data)
        items_key = f"{domain}s" if not domain.endswith("s") else domain
        items = data_payload.get(items_key, [])

        if not items:
            logger.debug(
                "auto_save_skipped_no_items",
                domain=domain,
                items_key=items_key,
                payload_keys=list(data_payload.keys()),
            )
            return

        # Extract user_id and session_id from config
        user_id = config.get("configurable", {}).get(FIELD_USER_ID)
        if not user_id:
            logger.error(
                "auto_save_failed_missing_user_id",
                domain=domain,
                config_configurable=config.get("configurable"),
            )
            return

        session_id = config.get("configurable", {}).get("thread_id")
        if not session_id:
            # FAIL-FAST: session_id is MANDATORY for namespace isolation
            logger.error(
                "auto_save_critical_missing_session_id",
                domain=domain,
                user_id=str(user_id),
                config_configurable=config.get("configurable"),
            )
            raise ValueError(
                f"auto_save requires session_id (thread_id) for domain '{domain}'. "
                "Data isolation breach prevented. Ensure thread_id is set in config.configurable."
            )

        turn_id = config.get(FIELD_METADATA, {}).get(FIELD_TURN_ID, 0)
        tool_name = result_data.get(FIELD_TOOL_NAME)
        query = result_data.get(FIELD_QUERY)

        metadata = {
            FIELD_TURN_ID: turn_id,
            "total_count": len(items),
            FIELD_QUERY: query,
            FIELD_TOOL_NAME: tool_name,
            FIELD_TIMESTAMP: datetime.now(UTC).isoformat(),
        }

        save_mode = self.classify_save_mode(
            tool_name=tool_name or "unknown_tool",
            result_count=len(items),
            explicit_mode=explicit_mode,
        )

        logger.info(
            "auto_save_classified",
            domain=domain,
            tool_name=tool_name,
            items_count=len(items),
            save_mode=save_mode.value if save_mode else "none",
            user_id=str(user_id),
            session_id=session_id,
        )

        try:
            if save_mode == ContextSaveMode.LIST:
                # LIST: overwrite list + auto-manage current
                await self.save_list(
                    user_id=user_id,
                    session_id=session_id,
                    domain=domain,
                    items=items,
                    metadata=metadata,
                    store=store,
                )
            elif save_mode == ContextSaveMode.CURRENT:
                # CURRENT: set current only, never touch list
                if len(items) == 1:
                    indexed_item = {**items[0], FIELD_INDEX: 1}
                    await self.set_current_item(
                        user_id=user_id,
                        session_id=session_id,
                        domain=domain,
                        item=indexed_item,
                        set_by="auto",
                        turn_id=turn_id,
                        store=store,
                    )
                else:
                    # N > 1: ambiguous focus → clear current, preserve list
                    await self.clear_current_item(user_id, session_id, domain, store)
            elif save_mode == ContextSaveMode.NONE:
                logger.debug(
                    "auto_save_skipped_mode_none",
                    domain=domain,
                    tool_name=tool_name,
                )
        except Exception as e:
            logger.error(
                "auto_save_execution_failed",
                domain=domain,
                save_mode=save_mode.value if save_mode else "none",
                error=str(e),
                exc_info=True,
            )

    @staticmethod
    def classify_save_mode(
        tool_name: str,
        result_count: int,
        explicit_mode: ContextSaveMode | None = None,
    ) -> ContextSaveMode:
        """Classify save mode: explicit if provided, else LIST (conservative default).

        Unified tools opt into LIST/CURRENT/NONE via UnifiedToolOutput.context_save_mode.
        Legacy tools without explicit mode fall back to LIST (overwrite, safe default).

        Args:
            tool_name: Name of the tool (kept for logging).
            result_count: Number of items (kept for logging).
            explicit_mode: Explicit mode from tool output or manifest.

        Returns:
            ContextSaveMode (LIST, CURRENT, or NONE).
        """
        if explicit_mode is not None:
            logger.debug(
                "classify_save_mode_explicit",
                tool_name=tool_name,
                result_count=result_count,
                mode=explicit_mode.value,
            )
            return explicit_mode

        logger.debug(
            "classify_save_mode_default_list",
            tool_name=tool_name,
            result_count=result_count,
        )
        return ContextSaveMode.LIST

    # ==========================================
    # SESSION CLEANUP OPERATIONS
    # ==========================================

    @profile_performance(func_name="context_store_cleanup", log_threshold_ms=100.0)
    async def cleanup_session_contexts(
        self,
        user_id: str | UUID,
        session_id: str,
        store: BaseStore,
    ) -> dict[str, int]:
        """
        Delete all tool contexts for a specific session (conversation reset).

        This method cleans up ALL domains for a given user+session combination.
        Used when user clicks "New conversation" to ensure clean slate.

        Deletes all Store entries with namespace prefix:
            (user_id, session_id, "context", *)

        This removes ALL keys (list, current) for ALL domains.

        Args:
            user_id: User identifier.
            session_id: Session/conversation identifier to cleanup.
            store: LangGraph BaseStore instance.

        Returns:
            Dict with cleanup statistics:
            - domains_cleaned: Number of domains found and cleaned
            - total_items_deleted: Total Store items deleted
            - success: Whether cleanup completed without errors

        Example:
            >>> stats = await manager.cleanup_session_contexts(
            ...     user_id="user123",
            ...     session_id="conv-456",
            ...     store=store
            ... )
            >>> print(f"Cleaned {stats['domains_cleaned']} domains, {stats['total_items_deleted']} items")

        Note:
            - Non-destructive: Only affects the specified session_id
            - Other conversations/sessions remain untouched
            - Uses Store.asearch() to find all matching namespaces
            - Deletes items individually (Store doesn't support bulk delete by prefix)
        """
        user_id_str = str(user_id)
        domains_cleaned = set()
        total_items_deleted = 0

        logger.info(
            "cleanup_session_contexts_started",
            user_id=user_id_str,
            session_id=session_id,
        )

        try:
            # Search for all Store items matching our session prefix
            # Namespace structure: (user_id, session_id, "context", domain)
            # We want to find all domains for this user+session
            namespace_prefix = (user_id_str, session_id, "context")

            # Use asearch with namespace prefix to find all matching items
            # Note: asearch() returns a list, not an async generator
            search_results = await store.asearch(namespace_prefix)

            # Group items by full namespace for efficient deletion
            items_by_namespace: dict[tuple[str, ...], list[str]] = {}

            for item in search_results:
                # item.namespace is the full tuple: (user_id, session_id, "context", domain)
                # item.key is one of: "list", "current"
                namespace = item.namespace
                key = item.key

                if namespace not in items_by_namespace:
                    items_by_namespace[namespace] = []
                items_by_namespace[namespace].append(key)

                # Track which domains we're cleaning
                if len(namespace) >= 4:
                    domain = namespace[3]
                    domains_cleaned.add(domain)

            # Delete all found items (parallelized for performance)
            # OPTIMIZATION: Use asyncio.gather() to delete all items in parallel
            # instead of sequential awaits (5-10x faster for large cleanups)
            delete_tasks = []
            for namespace, keys in items_by_namespace.items():
                for key in keys:
                    delete_tasks.append(store.adelete(namespace, key))
                    total_items_deleted += 1
                    logger.debug(
                        "store_item_queued_for_deletion",
                        namespace=namespace,
                        key=key,
                    )

            # Execute all deletes in parallel
            if delete_tasks:
                await asyncio.gather(*delete_tasks)
                logger.debug(
                    "batch_deletion_completed",
                    total_deletes=len(delete_tasks),
                )

            logger.info(
                "cleanup_session_contexts_completed",
                user_id=user_id_str,
                session_id=session_id,
                domains_cleaned=len(domains_cleaned),
                domains_list=list(domains_cleaned),
                total_items_deleted=total_items_deleted,
            )

            return {
                "domains_cleaned": len(domains_cleaned),
                "total_items_deleted": total_items_deleted,
                "success": True,
            }

        except Exception as cleanup_error:
            logger.error(
                "cleanup_session_contexts_failed",
                user_id=user_id_str,
                session_id=session_id,
                error=str(cleanup_error),
                error_type=type(cleanup_error).__name__,
            )

            return {
                "domains_cleaned": len(domains_cleaned),
                "total_items_deleted": total_items_deleted,
                "success": False,
            }
