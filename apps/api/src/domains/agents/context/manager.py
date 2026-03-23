"""
Generic Tool Context Manager for LangGraph BaseStore.

Provides CRUD operations for tool context management with zero tool-specific code.
All operations are configuration-driven via ContextTypeRegistry.

Architecture (Phase 5 - Session Isolation + Phase 3.2.9 - Multi-Keys Store Pattern):
    - Hierarchical namespaces: (user_id, session_id, "context", domain)
    - Three keys per domain (Multi-Keys Store Pattern):
        * "list" → ToolContextList (search results, overwrite behavior)
        * "details" → ToolContextDetails (item details, LRU merge, max 10)
        * "current" → ToolContextCurrentItem (single item or null)
    - Auto-enrichment: Adds "index" field to all items
    - Type-safe: Uses Pydantic schemas for validation
    - Auto-set current_item: When 1 result → automatic selection
    - Session isolation: Each conversation has its own context
    - Convention-based classification: Tool name patterns route to list vs details

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
    ToolContextDetails,
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
    # LEGACY COMPATIBILITY (V1)
    # ==========================================

    async def auto_save(
        self,
        context_type: str,
        result_data: dict[str, Any],
        config: RunnableConfig,
        store: BaseStore,
        explicit_mode: ContextSaveMode | None = None,
    ) -> None:
        """
        Auto-save context from tool result (called by @auto_save_context decorator).

        V2 - Multi-Keys Store Pattern:
            - Classifies tool results (LIST vs DETAILS)
            - Routes to save_list() or save_details() accordingly
            - LIST mode: Overwrites existing (search results)
            - DETAILS mode: Merges with existing (detail views)

        Convention:
            - Tool result must have key "{domain}s" (plural)
            - Example: domain="contacts" → result["contacts"]
            - Example: domain="email" → result["emails"]

        Args:
            context_type: Context type identifier (maps to domain).
            result_data: Parsed JSON result from tool (dict).
            config: RunnableConfig with user_id and metadata.
            store: LangGraph BaseStore instance.
            explicit_mode: Explicit LIST/DETAILS override from ToolManifest.context_save_mode.
                If None, uses name-based heuristic in classify_save_mode().

        Example:
            >>> # Called by decorator after tool execution
            >>> result = {"success": True, "contacts": [...], "tool_name": "search_contacts_tool"}
            >>> await manager.auto_save(
            ...     context_type="contacts",
            ...     result_data=result,
            ...     config=config,
            ...     store=store
            ... )
            >>> # Classifies as LIST mode → calls save_list()

            >>> result = {"success": True, "contacts": [...], "tool_name": "get_contact_details_tool"}
            >>> await manager.auto_save(...)
            >>> # Classifies as DETAILS mode → calls save_details()
        """
        # DEBUG: Log entry to trace if auto_save is called
        logger.info(
            "auto_save_entered",
            context_type=context_type,
            result_data_keys=list(result_data.keys()),
            has_store=store is not None,
            config_keys=list(config.keys()) if config else [],
            tool_name=result_data.get(FIELD_TOOL_NAME),
        )

        # Map context_type to domain (1:1 in V1)
        domain = context_type

        # Validate domain exists (raises ValueError if not found)
        try:
            _ = ContextTypeRegistry.get_definition(domain)
        except ValueError as e:
            logger.error("auto_save_domain_invalid", domain=domain, error=str(e))
            return

        # Extract items from result
        # CRITICAL: ToolResponse schema wraps data in {"success": bool, "data": {...}}
        # So we need to extract from result_data["data"]["{domain}s"]
        # NOT directly from result_data["{domain}s"]
        data_payload = result_data.get("data", result_data)  # Fallback for legacy tools
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

        # Extract session_id from config (Phase 5 - Session Isolation)
        # session_id is stored in configurable by LangGraph
        # CRITICAL: session_id is REQUIRED for data isolation - NO fallback to empty string
        session_id = config.get("configurable", {}).get("thread_id")
        if not session_id:
            # FAIL-FAST: session_id is MANDATORY for namespace isolation
            # Using empty string would cause data collisions across sessions
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

        # Extract metadata from config
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

        # ========================================
        # PHASE 3.2.9: MULTI-KEYS STORE PATTERN
        # ========================================
        # Classify save mode based on tool name and result count
        save_mode = self.classify_save_mode(
            tool_name=tool_name or "unknown_tool",
            result_count=len(items),
            explicit_mode=explicit_mode,
        )

        # DEBUG: Log classification result to trace persistence issue
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
            # Route to appropriate save method
            if save_mode == ContextSaveMode.LIST:
                # LIST mode: Overwrites existing (search/list results)
                await self.save_list(
                    user_id=user_id,
                    session_id=session_id,
                    domain=domain,
                    items=items,
                    metadata=metadata,
                    store=store,
                )
            elif save_mode == ContextSaveMode.DETAILS:
                # DETAILS mode: Merges with existing (detail views)
                await self.save_details(
                    user_id=user_id,
                    session_id=session_id,
                    domain=domain,
                    items=items,
                    metadata=metadata,
                    store=store,
                    max_items=settings.tool_context_details_max_items,
                )
            elif save_mode == ContextSaveMode.NONE:
                # NONE mode: Skip save (tool doesn't produce context-worthy results)
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
        # Note: ContextSaveMode.CURRENT is not used in auto_save (manual only)

    # ==========================================
    # MULTI-KEYS STORE PATTERN (V2 - Phase 3.2.9)
    # ==========================================

    @staticmethod
    def classify_save_mode(
        tool_name: str,
        result_count: int,
        explicit_mode: ContextSaveMode | None = None,
    ) -> ContextSaveMode:
        """
        Classify which Store key to use based on convention and result structure.

        This is the core routing logic for the Multi-Keys Store Pattern.
        It determines whether tool results should go to "list", "details", or nowhere.

        Classification Rules (priority order):
            1. Explicit mode from manifest → Use explicit mode
            2. Tool name contains "search", "list", "find" → LIST
            3. Tool name contains "get", "show", "detail", "fetch" → DETAILS
            4. Result count > 10 → LIST (large result set)
            5. Result count <= 10 → DETAILS (small result set)
            6. Default → DETAILS (safe fallback)

        Args:
            tool_name: Name of the tool that produced results.
            result_count: Number of items in result.
            explicit_mode: Optional explicit mode from ToolManifest.context_save_mode.

        Returns:
            ContextSaveMode enum value (LIST, DETAILS, CURRENT, or NONE).

        Examples:
            >>> classify_save_mode("search_contacts_tool", 10)
            ContextSaveMode.LIST

            >>> classify_save_mode("get_contact_details_tool", 2)
            ContextSaveMode.DETAILS

            >>> classify_save_mode("list_contacts_tool", 50)
            ContextSaveMode.LIST

            >>> classify_save_mode("update_contact_tool", 1, explicit_mode=ContextSaveMode.NONE)
            ContextSaveMode.NONE
        """
        # Rule 1: Explicit mode from manifest (highest priority)
        if explicit_mode is not None:
            logger.debug(
                "classify_save_mode_explicit",
                tool_name=tool_name,
                result_count=result_count,
                mode=explicit_mode.value,
            )
            return explicit_mode

        tool_name_lower = tool_name.lower()

        # Rule 2: Tool name pattern - LIST keywords
        list_keywords = ["search", "list", "find", "query"]
        if any(keyword in tool_name_lower for keyword in list_keywords):
            logger.debug(
                "classify_save_mode_by_name",
                tool_name=tool_name,
                result_count=result_count,
                mode="list",
                reason="tool_name_contains_list_keyword",
            )
            return ContextSaveMode.LIST

        # Rule 3: Tool name pattern - DETAILS keywords
        details_keywords = ["get", "show", "detail", "fetch", "retrieve"]
        if any(keyword in tool_name_lower for keyword in details_keywords):
            logger.debug(
                "classify_save_mode_by_name",
                tool_name=tool_name,
                result_count=result_count,
                mode="details",
                reason="tool_name_contains_details_keyword",
            )
            return ContextSaveMode.DETAILS

        # Rule 4: Result count > 10 → LIST (large result set)
        if result_count > 10:
            # Debug log removed - classification logic is clear from conditional
            return ContextSaveMode.LIST

        # Rule 5: Result count <= 10 → DETAILS (small result set)
        # Debug log removed - classification logic is clear from conditional
        return ContextSaveMode.DETAILS

    async def save_details(
        self,
        user_id: str | UUID,
        session_id: str,
        domain: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any],
        store: BaseStore,
        max_items: int = 10,
    ) -> None:
        """
        Save item details to Store with LRU merge logic.

        Unlike save_list() which OVERWRITES, save_details() MERGES new items
        with existing details, deduplicates, reindexes, and evicts oldest items
        when max_items is exceeded.

        Current Item Management (based on NEW items, not cache size):
            - If 1 new item → Auto-set that item as current (user is viewing it)
            - If > 1 new items → Clear current_item (ambiguous which one)
            - If 0 new items → Don't touch current_item
            This differs from save_list() because save_details() uses LRU merge.
            The current_item represents "what the user is currently viewing",
            so it should be the newly saved item, regardless of cache size.

        LRU Merge Algorithm:
            1. Fetch existing ToolContextDetails from Store key "details"
            2. Merge new items with existing (deduplicate by primary_id_field)
            3. Keep most recent version of each unique item
            4. Reindex items (1-based sequential)
            5. Evict oldest items if count > max_items
            6. Update metadata (total_count, timestamp)
            7. Save back to Store key "details"

        Args:
            user_id: User identifier.
            session_id: Session/thread identifier.
            domain: Domain identifier (must exist in ContextTypeRegistry).
            items: List of item dicts to save (will be enriched with "index").
            metadata: Metadata dict (turn_id, query, tool_name, timestamp).
            store: LangGraph BaseStore instance.
            max_items: Maximum items to keep in details cache (default 10).

        Example:
            >>> # First call: Save 1 contact detail
            >>> await manager.save_details(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="contacts",
            ...     items=[{"resource_name": "people/c123", "name": "Jean"}],
            ...     metadata={FIELD_TURN_ID: 5, ...},
            ...     store=store,
            ... )
            >>> # Store["details"] = {items: [{"index": 1, "resource_name": "people/c123", ...}]}

            >>> # Second call: Save 2 more contact details
            >>> await manager.save_details(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="contacts",
            ...     items=[
            ...         {"resource_name": "people/c456", "name": "Marie"},
            ...         {"resource_name": "people/c789", "name": "Paul"},
            ...     ],
            ...     metadata={FIELD_TURN_ID: 6, ...},
            ...     store=store,
            ... )
            >>> # Store["details"] = {items: [
            >>> #     {"index": 1, "resource_name": "people/c123", ...},  # Existing
            >>> #     {"index": 2, "resource_name": "people/c456", ...},  # New
            >>> #     {"index": 3, "resource_name": "people/c789", ...},  # New
            >>> # ]}

        Deduplication Logic:
            If new item has same primary_id_field as existing item → Replace existing.
            Example: get_contact_details("people/c123") twice → Only 1 item kept.
        """
        # Validate domain
        definition = ContextTypeRegistry.get_definition(domain)

        # Build namespace
        namespace = self._build_namespace(str(user_id), session_id, domain)

        # Fetch existing details (if any)
        existing_item = await store.aget(namespace, "details")
        existing_details: ToolContextDetails | None = None

        if existing_item and existing_item.value:
            try:
                existing_details = ToolContextDetails(**existing_item.value)
            except Exception as exc:
                logger.warning(
                    "save_details_invalid_existing",
                    domain=domain,
                    error=str(exc),
                    message="Existing details corrupted, starting fresh",
                )

        # Merge items (deduplicate by primary_id_field)
        primary_id_field = definition.primary_id_field
        merged_items_map: dict[Any, dict[str, Any]] = {}

        # Add existing items to map
        if existing_details:
            for item in existing_details.items:
                primary_id = item.get(primary_id_field)
                if primary_id:
                    merged_items_map[primary_id] = item

        # Add/overwrite with new items
        for item in items:
            primary_id = item.get(primary_id_field)
            if primary_id:
                merged_items_map[primary_id] = item
            else:
                logger.warning(
                    "save_details_missing_primary_id",
                    domain=domain,
                    primary_id_field=primary_id_field,
                    item=item,
                )

        # Convert map back to list (preserves insertion order in Python 3.7+)
        merged_items = list(merged_items_map.values())

        # Evict oldest items if exceeds max_items
        if len(merged_items) > max_items:
            # Debug log removed - LRU eviction is expected behavior, no actionable info
            # Keep most recent max_items (assumes list order = insertion order)
            merged_items = merged_items[-max_items:]

        # Reindex items (1-based sequential)
        indexed_items = [{FIELD_INDEX: i + 1, **item} for i, item in enumerate(merged_items)]

        # Create ToolContextDetails schema
        context_metadata = ContextMetadata(**metadata)
        context_metadata.total_count = len(indexed_items)  # Update to merged count

        context_details = ToolContextDetails(
            domain=domain,
            items=indexed_items,
            metadata=context_metadata,
        )

        # Save to Store key "details"
        await store.aput(namespace, "details", context_details.model_dump())

        # ============================================================
        # AUTO-MANAGE current_item based on NEW items (not cache size)
        # ============================================================
        # IMPORTANT: Unlike save_list(), save_details() uses LRU merge.
        # The current_item should be based on NEW items being saved:
        # - If 1 new item → Set that item as current (user is viewing it)
        # - If > 1 new items → Clear current (ambiguous which one user wants)
        # - If 0 new items → Don't touch current_item
        #
        # This fixes the bug where "detail of the 2nd" would clear current_item
        # because the LRU cache had multiple items from previous detail views.
        # ============================================================
        if len(items) == 1:
            # Single NEW item → Auto-set as current
            # Find this item in indexed_items by primary_id
            primary_id = items[0].get(primary_id_field)
            new_item = next(
                (item for item in indexed_items if item.get(primary_id_field) == primary_id),
                indexed_items[-1] if indexed_items else None,  # Fallback to last
            )
            if new_item:
                await self.set_current_item(
                    user_id=user_id,
                    session_id=session_id,
                    domain=domain,
                    item=new_item,
                    set_by="auto",
                    turn_id=metadata.get(FIELD_TURN_ID, 0),
                    store=store,
                )
                logger.info(
                    "current_item_auto_set_from_details",
                    user_id=str(user_id),
                    session_id=session_id,
                    domain=domain,
                    reason="single_new_detail_item",
                    item_index=new_item.get(FIELD_INDEX),
                    cache_size=len(indexed_items),
                )
        elif len(items) > 1:
            # Multiple NEW items → Clear current_item (ambiguous)
            await self.clear_current_item(user_id, session_id, domain, store)
            logger.debug(
                "current_item_cleared_multiple_new",
                user_id=str(user_id),
                domain=domain,
                new_items_count=len(items),
            )
        else:
            # len(items) == 0: Edge case - empty save should clear current for consistency
            # with save_list() behavior. This shouldn't normally happen in practice.
            await self.clear_current_item(user_id, session_id, domain, store)

        logger.info(
            "details_saved",
            domain=domain,
            user_id=str(user_id),
            session_id=session_id,
            items_count=len(indexed_items),
            turn_id=metadata.get(FIELD_TURN_ID),
            tool_name=metadata.get(FIELD_TOOL_NAME),
        )

    async def get_details(
        self, user_id: str | UUID, session_id: str, domain: str, store: BaseStore
    ) -> ToolContextDetails | None:
        """
        Get item details from Store key "details".

        Args:
            user_id: User identifier.
            session_id: Session/thread identifier.
            domain: Domain identifier.
            store: LangGraph BaseStore instance.

        Returns:
            ToolContextDetails if exists, None otherwise.

        Example:
            >>> details = await manager.get_details(
            ...     user_id="user123",
            ...     session_id="sess456",
            ...     domain="contacts",
            ...     store=store
            ... )
            >>> if details:
            ...     print(f"Details cache: {len(details.items)} items")
        """
        namespace = self._build_namespace(str(user_id), session_id, domain)
        item = await store.aget(namespace, "details")

        if not item or not item.value:
            return None

        try:
            return ToolContextDetails(**item.value)
        except Exception as exc:
            logger.error(
                "get_details_parse_error",
                domain=domain,
                user_id=str(user_id),
                session_id=session_id,
                error=str(exc),
            )
            return None

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

        This removes ALL keys (list, details, current) for ALL domains.

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
                # item.key is one of: "list", "details", "current"
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
