"""
Tool Context Management for LangGraph Agents.

This module provides a generic, domain-based system for managing contextual references
to tool results, allowing agents to understand and resolve references like "the 2nd one",
"the last email", "Jean Dupont" by maintaining type-safe context stores.

Architecture (V2 - Domain-based):
    - Registry: Auto-discovery of domains (contacts, emails, events)
    - Store: LangGraph BaseStore/InMemoryStore for persistence
    - Decorators: Auto-save tool results with zero boilerplate
    - Resolvers: Generic reference resolution (index, keyword, fuzzy match)
    - Current Item: Auto-set when 1 result, explicit selection otherwise

Namespace Structure:
    (user_id, "context", domain)
    ├─ key="list" → ToolContextList (all items indexed)
    └─ key="current" → ToolContextCurrentItem (single item or null)

Usage:
    # 1. Register domain (in tool module)
    from src.domains.agents.constants import CONTEXT_DOMAIN_CONTACTS

    ContextTypeRegistry.register(
        ContextTypeDefinition(
            domain=CONTEXT_DOMAIN_CONTACTS,
            agent_name="contacts_agent",
            item_schema=ContactItem,
            primary_id_field="resource_name",
            display_name_field="name",
            reference_fields=["name", "emails"]
        )
    )

    # 2. Apply decorator to tools
    @tool
    @auto_save_context("contacts")
    async def search_contacts_tool(...) -> str:
        ...

    # 3. Use context tools in agent
    tools = [
        search_contacts_tool,
        resolve_reference,      # Auto-detects domain if not specified
        set_current_item,       # Explicitly mark item as current
        get_context_state,      # Get current state for a domain
        list_active_domains,    # List all active domains
    ]

Example Flow:
    User: "liste mes contacts"
    → Tool returns [Jean, Marie, Paul]
    → Auto-saved to Store with indexes
    → PAS d'item courant (plusieurs résultats)

    User: "affiche le détail du 2ème"
    → resolve_reference("2") → Auto-detects domain="contacts"
    → Resolves to Marie → Item marked as current
    → get_contact_details("people/c456")

    User: "affiche son email"
    → get_context_state("contacts") → current_item exists (Marie)
    → Uses Marie's resource_name directly

Best Practices:
    - One domain per data entity (contacts, emails, events)
    - Use auto_save_context decorator for automatic persistence
    - Define clear reference_fields for fuzzy matching
    - Let resolve_reference auto-detect domain when possible
    - Always check get_context_state for implicit references
"""

from src.domains.agents.context.decorators import auto_save_context
from src.domains.agents.context.entity_resolution import (
    DisambiguationContext,
    DisambiguationType,
    EntityResolutionService,
    ResolutionStatus,
    ResolvedEntity,
    get_entity_resolution_service,
)
from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.prompts import get_context_instructions
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.context.schemas import (
    ContextSaveMode,
    ToolContextCurrentItem,
    ToolContextDetails,
    ToolContextList,
)
from src.domains.agents.context.store import cleanup_tool_context_store, get_tool_context_store

__all__ = [
    "ContextSaveMode",
    "ContextTypeDefinition",
    "ContextTypeRegistry",
    "DisambiguationContext",
    "DisambiguationType",
    "EntityResolutionService",
    "ResolvedEntity",
    "ResolutionStatus",
    "ToolContextCurrentItem",
    "ToolContextDetails",
    "ToolContextList",
    "ToolContextManager",
    "auto_save_context",
    "cleanup_tool_context_store",
    "get_context_instructions",
    "get_entity_resolution_service",
    "get_tool_context_store",
    # NOTE: Legacy manifest exports removed (Phase 5 cleanup).
    # All manifests now loaded via registry/catalogue_loader.py
    # See: src/domains/agents/context/catalogue_manifests.py
]
