"""
Entity Resolution Service - Automatic entity resolution with disambiguation.

This module provides intelligent entity resolution when users mention names or
references that need to be resolved to specific data (email addresses, phone
numbers, event IDs, etc.) for completing actions.

Use Cases:
    1. "Envoie un email à Jean Dupont"
       → Search contacts, find Jean, extract email for send_email_tool

    2. "Planifie un rdv avec Marie Martin demain"
       → Search contacts, find Marie, extract email for calendar invitation

    3. Contact has multiple emails
       → Detect ambiguity, trigger HITL to ask user which email to use

Architecture:
    User mentions name → Planner creates search step → Search executes
    → EntityResolutionService analyzes results:
        - 1 result with unique target field → Auto-resolve, continue
        - 1 result with multiple target fields → HITL for field choice
        - Multiple results → HITL for entity choice
        - No results → Error feedback

Features:
    - Generic resolution for any domain (contacts, emails, events)
    - Action-aware field extraction (email for send_email, phone for call, etc.)
    - Confidence-based auto-resolution with configurable threshold
    - HITL integration for disambiguation
    - Multilingual support via i18n_hitl

Configuration:
    Settings control resolution behavior:
    - entity_resolution_auto_threshold: Confidence for auto-resolution (default: 0.9)
    - entity_resolution_max_candidates: Max candidates to show user (default: 5)

References:
    - context/resolver.py: Base ReferenceResolver for fuzzy matching
    - context/registry.py: ContextTypeDefinition for domain configuration
    - hitl/interactions/entity_disambiguation.py: HITL interaction

Created: 2025-12-07
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.config import get_settings
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.context.registry import ContextTypeRegistry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ResolutionStatus(str, Enum):
    """Status of entity resolution attempt."""

    RESOLVED = "resolved"  # Successfully resolved to single value
    DISAMBIGUATION_NEEDED = "disambiguation_needed"  # Multiple options, need user input
    NOT_FOUND = "not_found"  # No matching entities found
    NO_TARGET_FIELD = "no_target_field"  # Entity found but doesn't have required field
    ERROR = "error"  # Resolution error


class DisambiguationType(str, Enum):
    """Type of disambiguation needed."""

    MULTIPLE_ENTITIES = "multiple_entities"  # Multiple contacts/events match query
    MULTIPLE_FIELDS = "multiple_fields"  # One entity has multiple values for target field


@dataclass
class ResolvedEntity:
    """
    Result of entity resolution.

    Attributes:
        status: Resolution status (resolved, disambiguation_needed, not_found, etc.)
        resolved_value: The resolved value if status is RESOLVED (e.g., email address)
        resolved_item: Full item dict if resolved (for additional context)
        disambiguation_context: Context for HITL if disambiguation needed
        error_message: Error description if resolution failed
    """

    status: ResolutionStatus
    resolved_value: str | None = None
    resolved_item: dict[str, Any] | None = None
    disambiguation_context: dict[str, Any] | None = None
    error_message: str | None = None
    confidence: float = 0.0


@dataclass
class DisambiguationContext:
    """
    Context for HITL disambiguation.

    Contains all information needed to generate a disambiguation question
    and process the user's response.

    Attributes:
        disambiguation_type: Type of disambiguation (multiple_entities or multiple_fields)
        domain: Entity domain (contacts, emails, events, etc.)
        original_query: User's original search term
        intended_action: Action the user wants to perform
        target_field: Field type needed for the action (email, phone, etc.)
        candidates: List of candidate items with display info
        registry_ids: Data registry IDs for rich rendering
    """

    disambiguation_type: DisambiguationType
    domain: str
    original_query: str
    intended_action: str
    target_field: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    registry_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for HITL context."""
        return {
            "disambiguation_type": self.disambiguation_type.value,
            "domain": self.domain,
            "original_query": self.original_query,
            "intended_action": self.intended_action,
            "target_field": self.target_field,
            "candidates": self.candidates,
            "registry_ids": self.registry_ids,
        }


# Mapping of action types to required field types
ACTION_TO_FIELD_MAPPING: dict[str, list[str]] = {
    # Email actions need email addresses
    "send_email": ["email", "emails"],
    "reply_email": ["email", "emails"],
    "forward_email": ["email", "emails"],
    # Calendar actions may need email for invitations
    "create_event": ["email", "emails"],
    "invite_to_event": ["email", "emails"],
    # Phone actions need phone numbers
    "call": ["phone", "phones", "phoneNumbers"],
    "send_sms": ["phone", "phones", "phoneNumbers"],
    # Contact details - any identifier
    "get_details": ["resource_name", "id"],
    # Default: accept primary identifier
    "default": ["id", "resource_name", "message_id", "event_id"],
}


class EntityResolutionService:
    """
    Service for intelligent entity resolution with disambiguation.

    Analyzes search results and determines if automatic resolution is possible
    or if user disambiguation is needed.

    Thread-safe: No mutable instance state.

    Example:
        >>> service = EntityResolutionService()
        >>> result = service.resolve_for_action(
        ...     items=[
        ...         {"name": "Jean Dupont", "emails": ["jean@work.com", "jean@home.com"]},
        ...     ],
        ...     domain="contacts",
        ...     original_query="Jean Dupont",
        ...     intended_action="send_email",
        ... )
        >>> if result.status == ResolutionStatus.DISAMBIGUATION_NEEDED:
        ...     # Trigger HITL with result.disambiguation_context
        ...     pass
        >>> elif result.status == ResolutionStatus.RESOLVED:
        ...     # Use result.resolved_value (email address)
        ...     pass
    """

    def __init__(self) -> None:
        """Initialize EntityResolutionService."""
        self._settings = get_settings()

    def resolve_for_action(
        self,
        items: list[dict[str, Any]],
        domain: str,
        original_query: str,
        intended_action: str,
        target_field_override: str | None = None,
    ) -> ResolvedEntity:
        """
        Resolve entity for a specific action.

        Analyzes search results and determines if automatic resolution is possible
        based on the intended action and available data.

        Args:
            items: Search result items (from search_contacts_tool, etc.)
            domain: Entity domain (contacts, emails, events)
            original_query: User's original search term (e.g., "Jean Dupont")
            intended_action: Action type (send_email, create_event, call, etc.)
            target_field_override: Override automatic field detection

        Returns:
            ResolvedEntity with resolution status and data

        Logic:
            1. No items → NOT_FOUND
            2. One item with single target value → RESOLVED
            3. One item with multiple target values → DISAMBIGUATION_NEEDED (multiple_fields)
            4. Multiple items → DISAMBIGUATION_NEEDED (multiple_entities)
        """
        logger.info(
            "entity_resolution_started",
            domain=domain,
            query=original_query,
            action=intended_action,
            items_count=len(items),
        )

        # Handle empty results
        if not items:
            logger.debug(
                "entity_resolution_not_found",
                query=original_query,
                domain=domain,
            )
            return ResolvedEntity(
                status=ResolutionStatus.NOT_FOUND,
                error_message=APIMessages.entity_not_found(domain, original_query),
            )

        # Determine target field based on action
        target_fields = self._get_target_fields(intended_action, target_field_override)

        # Single item case
        if len(items) == 1:
            return self._resolve_single_item(
                item=items[0],
                domain=domain,
                original_query=original_query,
                intended_action=intended_action,
                target_fields=target_fields,
            )

        # Multiple items case - need disambiguation
        return self._handle_multiple_items(
            items=items,
            domain=domain,
            original_query=original_query,
            intended_action=intended_action,
            target_fields=target_fields,
        )

    def _get_target_fields(
        self,
        intended_action: str,
        override: str | None = None,
    ) -> list[str]:
        """
        Get target field names for an action.

        Args:
            intended_action: Action type (send_email, call, etc.)
            override: Optional field name override

        Returns:
            List of field names to look for (in priority order)
        """
        if override:
            return [override]

        # Normalize action name (remove _tool suffix, lowercase)
        action_key = intended_action.lower().replace("_tool", "")

        return ACTION_TO_FIELD_MAPPING.get(
            action_key,
            ACTION_TO_FIELD_MAPPING["default"],
        )

    def _resolve_single_item(
        self,
        item: dict[str, Any],
        domain: str,
        original_query: str,
        intended_action: str,
        target_fields: list[str],
    ) -> ResolvedEntity:
        """
        Resolve a single item for the target action.

        Checks if the item has the required field and handles multiple values.

        Args:
            item: Single search result item
            domain: Entity domain
            original_query: User's search term
            intended_action: Target action
            target_fields: Fields to extract

        Returns:
            ResolvedEntity with resolution result
        """
        # Try to find target field value
        for field_name in target_fields:
            value = item.get(field_name)

            if value is None:
                continue

            # Handle list of values (e.g., multiple emails)
            if isinstance(value, list):
                if len(value) == 0:
                    continue
                elif len(value) == 1:
                    # Single value in list - auto-resolve
                    resolved_value = self._extract_value(value[0])
                    logger.info(
                        "entity_resolution_auto_resolved",
                        domain=domain,
                        field=field_name,
                        value=resolved_value,
                    )
                    return ResolvedEntity(
                        status=ResolutionStatus.RESOLVED,
                        resolved_value=resolved_value,
                        resolved_item=item,
                        confidence=1.0,
                    )
                else:
                    # Multiple values - need disambiguation
                    return self._create_field_disambiguation(
                        item=item,
                        domain=domain,
                        original_query=original_query,
                        intended_action=intended_action,
                        field_name=field_name,
                        field_values=value,
                    )

            # Single value - auto-resolve
            resolved_value = self._extract_value(value)
            logger.info(
                "entity_resolution_auto_resolved",
                domain=domain,
                field=field_name,
                value=resolved_value,
            )
            return ResolvedEntity(
                status=ResolutionStatus.RESOLVED,
                resolved_value=resolved_value,
                resolved_item=item,
                confidence=1.0,
            )

        # No target field found
        logger.warning(
            "entity_resolution_no_target_field",
            domain=domain,
            query=original_query,
            target_fields=target_fields,
            available_fields=list(item.keys()),
        )
        return ResolvedEntity(
            status=ResolutionStatus.NO_TARGET_FIELD,
            resolved_item=item,
            error_message=f"Le {domain} trouvé n'a pas de {target_fields[0]}",
        )

    def _extract_value(self, value: Any) -> str:
        """
        Extract string value from various formats.

        Handles:
        - Plain strings
        - Dicts with 'value' key (e.g., {"value": "jean@example.com", "type": "work"})

        Args:
            value: Value to extract from

        Returns:
            Extracted string value
        """
        if isinstance(value, str):
            return value
        elif isinstance(value, dict):
            # Try common value keys
            for key in ("value", "email", "phone", "address", "formatted"):
                if key in value:
                    return str(value[key])
            # Fallback to first non-type value
            for k, v in value.items():
                if k not in ("type", "label", "metadata") and isinstance(v, str):
                    return v
        return str(value)

    def _create_field_disambiguation(
        self,
        item: dict[str, Any],
        domain: str,
        original_query: str,
        intended_action: str,
        field_name: str,
        field_values: list[Any],
    ) -> ResolvedEntity:
        """
        Create disambiguation context for multiple field values.

        E.g., contact has work email and personal email - ask user which to use.

        Args:
            item: The entity item
            domain: Entity domain
            original_query: User's search term
            intended_action: Target action
            field_name: Field with multiple values
            field_values: List of field values

        Returns:
            ResolvedEntity with disambiguation context
        """
        # Get display name for the entity
        try:
            definition = ContextTypeRegistry.get_definition(domain)
            display_name = item.get(definition.display_name_field, original_query)
        except ValueError:
            display_name = item.get("name", original_query)

        # Build candidates list
        candidates = []
        for i, val in enumerate(field_values[: self._settings.entity_resolution_max_candidates]):
            extracted_value = self._extract_value(val)
            label = ""
            if isinstance(val, dict):
                label = val.get("type", val.get("label", ""))

            candidates.append(
                {
                    "index": i + 1,
                    "value": extracted_value,
                    "label": label,
                    "parent_name": display_name,
                }
            )

        context = DisambiguationContext(
            disambiguation_type=DisambiguationType.MULTIPLE_FIELDS,
            domain=domain,
            original_query=original_query,
            intended_action=intended_action,
            target_field=field_name.rstrip("s"),  # emails -> email
            candidates=candidates,
            registry_ids=[item.get("resource_name", item.get("id", ""))],
        )

        logger.info(
            "entity_resolution_disambiguation_needed",
            disambiguation_type="multiple_fields",
            domain=domain,
            entity_name=display_name,
            field=field_name,
            options_count=len(candidates),
        )

        return ResolvedEntity(
            status=ResolutionStatus.DISAMBIGUATION_NEEDED,
            disambiguation_context=context.to_dict(),
            resolved_item=item,
        )

    def _handle_multiple_items(
        self,
        items: list[dict[str, Any]],
        domain: str,
        original_query: str,
        intended_action: str,
        target_fields: list[str],
    ) -> ResolvedEntity:
        """
        Handle case with multiple matching items.

        Creates disambiguation context for user to choose which entity.

        Args:
            items: Multiple matching items
            domain: Entity domain
            original_query: User's search term
            intended_action: Target action
            target_fields: Fields needed for action

        Returns:
            ResolvedEntity with disambiguation context
        """
        # Get context definition for display field
        try:
            definition = ContextTypeRegistry.get_definition(domain)
            display_field = definition.display_name_field
            id_field = definition.primary_id_field
        except ValueError:
            display_field = "name"
            id_field = "id"

        # Build candidates list with display info
        candidates = []
        registry_ids = []
        max_candidates = self._settings.entity_resolution_max_candidates

        for i, item in enumerate(items[:max_candidates]):
            # Extract display info
            name = item.get(display_field, item.get("name", f"Item {i + 1}"))
            item_id = item.get(id_field, item.get("id", ""))

            # Extract target field value for display (e.g., email)
            target_value = None
            for field_name in target_fields:
                val = item.get(field_name)
                if val:
                    if isinstance(val, list) and val:
                        target_value = self._extract_value(val[0])
                    else:
                        target_value = self._extract_value(val)
                    break

            candidate = {
                "index": i + 1,
                "name": name,
                id_field: item_id,
            }

            # Add target field info if available
            if target_value:
                if target_fields[0] in ("email", "emails"):
                    candidate["email"] = target_value
                elif target_fields[0] in ("phone", "phones", "phoneNumbers"):
                    candidate["phone"] = target_value

            candidates.append(candidate)
            if item_id:
                registry_ids.append(item_id)

        context = DisambiguationContext(
            disambiguation_type=DisambiguationType.MULTIPLE_ENTITIES,
            domain=domain,
            original_query=original_query,
            intended_action=intended_action,
            target_field=target_fields[0] if target_fields else "",
            candidates=candidates,
            registry_ids=registry_ids,
        )

        logger.info(
            "entity_resolution_disambiguation_needed",
            disambiguation_type="multiple_entities",
            domain=domain,
            query=original_query,
            candidates_count=len(candidates),
            total_items=len(items),
        )

        return ResolvedEntity(
            status=ResolutionStatus.DISAMBIGUATION_NEEDED,
            disambiguation_context=context.to_dict(),
        )

    def resolve_user_choice(
        self,
        choice: str | int,
        disambiguation_context: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> ResolvedEntity:
        """
        Resolve user's disambiguation choice.

        Called after user selects from disambiguation options.

        Args:
            choice: User's choice (index number or ordinal like "2", "le premier")
            disambiguation_context: Original disambiguation context
            items: Original items list

        Returns:
            ResolvedEntity with resolved value
        """
        candidates = disambiguation_context.get("candidates", [])
        disambiguation_type = disambiguation_context.get("disambiguation_type", "")

        # Parse choice to index
        try:
            if isinstance(choice, int):
                index = choice
            else:
                # Try to parse as number
                choice_str = str(choice).strip().lower()
                # Remove ordinal suffixes
                for suffix in ("er", "ère", "ème", "e", "st", "nd", "rd", "th"):
                    choice_str = choice_str.rstrip(suffix)
                index = int(choice_str)
        except ValueError:
            return ResolvedEntity(
                status=ResolutionStatus.ERROR,
                error_message=APIMessages.invalid_choice(str(choice)),
            )

        # Validate index range
        if index < 1 or index > len(candidates):
            return ResolvedEntity(
                status=ResolutionStatus.ERROR,
                error_message=APIMessages.choice_out_of_bounds(index, len(candidates)),
            )

        selected = candidates[index - 1]

        # For multiple_fields, the value is directly in the candidate
        if disambiguation_type == "multiple_fields":
            return ResolvedEntity(
                status=ResolutionStatus.RESOLVED,
                resolved_value=selected.get("value"),
                confidence=1.0,
            )

        # For multiple_entities, return the selected item
        # Find the corresponding item in the original list
        item_id = selected.get("resource_name") or selected.get("id")
        resolved_item = None
        for item in items:
            if item.get("resource_name") == item_id or item.get("id") == item_id:
                resolved_item = item
                break

        # Extract the target field value
        resolved_value = selected.get("email") or selected.get("phone") or selected.get("value")

        return ResolvedEntity(
            status=ResolutionStatus.RESOLVED,
            resolved_value=resolved_value,
            resolved_item=resolved_item or selected,
            confidence=1.0,
        )


# Singleton instance
_entity_resolution_service: EntityResolutionService | None = None


def get_entity_resolution_service() -> EntityResolutionService:
    """
    Get singleton EntityResolutionService instance.

    Returns:
        EntityResolutionService singleton
    """
    global _entity_resolution_service
    if _entity_resolution_service is None:
        _entity_resolution_service = EntityResolutionService()
    return _entity_resolution_service
