"""
Mappers for orchestration layer.

This module provides mapping functions to convert between different
result formats in the orchestration layer.

Phase 3.2.3: Extracted from task_orchestrator_node.py for better separation of concerns.
Phase 3.2.5: Updated to use Pydantic AgentResult for runtime validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.field_names import (
    FIELD_PLAN_ID,
    FIELD_RESOURCE_NAME,
    FIELD_TIMESTAMP,
    FIELD_TOOL_NAME,
)
from src.domains.agents.constants import make_agent_result_key
from src.domains.agents.orchestration.schemas import (
    AgentResult,
    AgentResultData,
    ContactsResultData,
    EmailsResultData,
    MultiDomainResultData,
    PlacesResultData,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.orchestration.schemas import ExecutionResult

logger = get_logger(__name__)


# ============================================================================
# GENERIC RESULT NORMALIZATION (Phase 5.2B)
# ============================================================================


def _merge_contact_field(existing_value: Any, new_value: Any) -> Any:
    """Return the "richer" of two values for one contact field.

    Richness rule (order-independent — ROOT CAUSE FIX #2025-11-13): a present
    value beats ``None``; a longer list, a dict with more keys, or a longer
    (stripped) string beats a shorter one; on a tie or a type mismatch the
    existing value is kept for stability. Each per-type rule collapses to a
    single "keep the larger" comparison, provably equivalent to the former
    explicit empty/longer/equal ladder (pinned by the merge characterization
    tests).

    Args:
        existing_value: Value already accumulated for the field.
        new_value: Value from the contact being merged in.

    Returns:
        Whichever value is richer, per the rule above.
    """
    if existing_value is None:
        return new_value
    if new_value is None:
        return existing_value
    if isinstance(existing_value, list) and isinstance(new_value, list):
        return new_value if len(new_value) > len(existing_value) else existing_value
    if isinstance(existing_value, dict) and isinstance(new_value, dict):
        return new_value if len(new_value) > len(existing_value) else existing_value
    if isinstance(existing_value, str) and isinstance(new_value, str):
        return new_value if len(new_value.strip()) > len(existing_value.strip()) else existing_value
    return existing_value


def _merge_contacts(
    resource_name: str, existing: dict[str, Any], contact: dict[str, Any]
) -> dict[str, Any]:
    """Merge two contacts sharing a ``resource_name`` field-by-field.

    Applies :func:`_merge_contact_field` to every key present in either contact,
    so the richer value wins per field regardless of which contact carried it
    (search vs. get_details). Emits the same ``contact_merged_intelligent`` debug
    trace as before the extraction.

    Args:
        resource_name: Shared identifier (for the debug trace).
        existing: Contact already stored under ``resource_name``.
        contact: Newly seen contact to merge in.

    Returns:
        A new dict holding the richer value for every field.
    """
    merged: dict[str, Any] = {}
    all_keys = set(existing.keys()) | set(contact.keys())
    for key in all_keys:
        merged[key] = _merge_contact_field(existing.get(key), contact.get(key))

    logger.debug(
        "contact_merged_intelligent",
        resource_name=resource_name,
        existing_fields=list(existing.keys()),
        new_fields=list(contact.keys()),
        merged_fields=list(merged.keys()),
        preserved_non_empty=sum(1 for k in all_keys if existing.get(k) and not contact.get(k)),
    )
    return merged


def _upsert_contact(contacts_dict: dict[str, dict[str, Any]], contact: dict[str, Any]) -> None:
    """Insert ``contact`` into ``contacts_dict``, deduplicating by resource_name.

    ``resource_name`` (Google People API) is the dedup key; a synthetic key is
    minted when it is absent so no contact is dropped. A repeat ``resource_name``
    triggers an intelligent field-by-field merge (:func:`_merge_contacts`).

    Args:
        contacts_dict: Accumulator mapping resource_name -> merged contact
            (mutated in place).
        contact: Contact to add or merge.
    """
    resource_name = contact.get(FIELD_RESOURCE_NAME)
    if not resource_name:
        # Fallback: If no resource_name (should never happen with Google API),
        # use a synthetic key to avoid losing the contact
        resource_name = f"_synthetic_{len(contacts_dict)}"
        logger.warning(
            "contact_without_resource_name",
            contact_preview=str(contact)[:200],
        )

    if resource_name in contacts_dict:
        existing = contacts_dict[resource_name]
        contacts_dict[resource_name] = _merge_contacts(resource_name, existing, contact)
    else:
        # New contact -> Add to dict
        contacts_dict[resource_name] = contact


def _extract_contacts_from_registry(
    data_registry: dict[str, Any], contacts_dict: dict[str, dict[str, Any]]
) -> None:
    """Extract CONTACT items from the data registry into ``contacts_dict``.

    Data-registry fallback (Phase 5.2 BugFix 2025-11-26): registry-enabled tools
    leave only ``summary_for_llm`` text in the step results, storing the
    structured contact under a ``type="CONTACT"`` RegistryItem. This pulls those
    payloads in, keyed by resource_name (or item_id when absent) and
    deduplicated against contacts already present.

    Args:
        data_registry: Registry mapping item_id -> RegistryItem dict.
        contacts_dict: Accumulator mapping key -> contact (mutated in place).
    """
    for item_id, item in data_registry.items():
        # RegistryItem structure: {"id": ..., "type": "CONTACT", "payload": {...}, "meta": {...}}
        item_type = item.get("type", "")
        if item_type == "CONTACT":
            payload = item.get("payload", {})
            if payload:
                resource_name = payload.get(FIELD_RESOURCE_NAME)
                if resource_name:
                    # Use same deduplication logic
                    if resource_name not in contacts_dict:
                        contacts_dict[resource_name] = payload
                        logger.debug(
                            "registry_contact_extracted_from_registry",
                            item_id=item_id,
                            resource_name=resource_name,
                        )
                else:
                    # Fallback: Use item_id as key if no resource_name
                    contacts_dict[item_id] = payload
                    logger.debug(
                        "registry_contact_extracted_without_resource_name",
                        item_id=item_id,
                    )


def _detect_and_normalize_contacts_result(
    step_results: list[dict[str, Any]],
    data_registry: dict[str, Any] | None = None,
) -> ContactsResultData | None:
    """
    Detect and normalize contacts-related results from planner execution.

    This function provides **generic detection** of contacts data across
    different tool outputs (search, list, get_details, etc.) and normalizes
    them to the ContactsResultData schema expected by response_node.

    **Data Registry Mode Support** (Phase 5.2 BugFix 2025-11-26):
    When registry-enabled tools are used (registry_enabled=True), the step_results only
    contain summary_for_llm text, not structured contacts data. The actual
    contacts data is in data_registry as RegistryItems with type="CONTACT".
    This function now extracts contacts from data_registry as fallback.

    **Extensibility Pattern**:
    - Add similar functions for other domains: _detect_and_normalize_emails_result, etc.
    - Keep detection logic centralized for maintainability
    - Preserves all metadata (freshness, cache age, etc.)

    Args:
        step_results: List of tool result data dicts from completed steps.
                     Expected format: [{"contacts": [...], "total": N}, ...]
        data_registry: Optional data registry dict with RegistryItems.
                      Used as fallback when step_results don't contain structured data.

    Returns:
        ContactsResultData if contacts detected, None otherwise.

    Algorithm:
        1. Scan all step results for "contacts" key
        2. Aggregate all contacts from multiple steps (e.g., search + get_details)
        3. Preserve freshness metadata (data_source, timestamp, cache_age)
        4. Build ContactsResultData with normalized schema

    Example:
        >>> results = [
        ...     {"contacts": [{"name": "John"}, {"name": "Jane"}], "total": 2},
        ...     {"contacts": [{"name": "Bob"}], "total": 1}
        ... ]
        >>> normalized = _detect_and_normalize_contacts_result(results)
        >>> normalized.total_count
        3
        >>> len(normalized.contacts)
        3
    """
    if not step_results:
        return None

    # Collect all contacts from all steps WITH DEDUPLICATION
    # FIX #BUG-2025-11-13-PHOTOS: Merge duplicate contacts by resource_name
    # Context: Planner often executes search_contacts (light fields) + get_contact_details (full fields)
    # This creates duplicates: same contact appears twice (once light, once full)
    # Solution: Use resource_name as unique key and merge all fields
    contacts_dict: dict[str, dict[str, Any]] = {}  # resource_name → merged contact
    data_source = "api"  # Default
    timestamp = None
    cache_age_seconds = None

    for result_index, result in enumerate(step_results):
        if not isinstance(result, dict):
            continue

        # Detect contacts key (generic across search/list/get_details tools)
        if "contacts" in result and isinstance(result["contacts"], list):
            contacts_count_in_result = len(result["contacts"])
            logger.debug(
                "processing_contacts_result",
                result_index=result_index,
                contacts_count=contacts_count_in_result,
                tool_name=result.get(FIELD_TOOL_NAME, "unknown"),
            )

            for contact in result["contacts"]:
                _upsert_contact(contacts_dict, contact)

            # Preserve freshness metadata from first result
            if timestamp is None:
                data_source = result.get("data_source", "api")
                timestamp = result.get(FIELD_TIMESTAMP)
                cache_age_seconds = result.get("cache_age_seconds")

    # Convert dict to list (order doesn't matter for response formatting)
    all_contacts = list(contacts_dict.values())

    # ============================================================================
    # Data Registry MODE FALLBACK (Phase 5.2 BugFix 2025-11-26)
    # ============================================================================
    # When registry-enabled tools are used, step_results only contain summary_for_llm text.
    # The actual contacts data is stored in data_registry as RegistryItems.
    # Extract contacts from registry if:
    # 1. No contacts found in step_results (Data Registry mode)
    # 2. data_registry is provided and non-empty
    # ============================================================================
    if not all_contacts and data_registry:
        logger.info(
            "registry_fallback_extracting_contacts_from_registry",
            registry_items_count=len(data_registry),
        )
        _extract_contacts_from_registry(data_registry, contacts_dict)

        # Update all_contacts with extracted data
        all_contacts = list(contacts_dict.values())
        data_source = "data_registry"  # Mark as from data registry

        if all_contacts:
            logger.info(
                "registry_contacts_extracted_successfully",
                contacts_count=len(all_contacts),
            )

    # If no contacts found, not a contacts result
    if not all_contacts:
        return None

    # Build ContactsResultData with all aggregated contacts
    from datetime import UTC, datetime

    return ContactsResultData(
        contacts=all_contacts,
        total_count=len(all_contacts),
        has_more=False,  # Planner executes complete plan, no pagination
        query=None,  # May span multiple queries
        data_source=data_source,
        timestamp=timestamp or datetime.now(UTC).isoformat(),
        cache_age_seconds=cache_age_seconds,
    )


def _detect_and_normalize_emails_result(
    step_results: list[dict[str, Any]],
    data_registry: dict[str, Any] | None = None,
) -> EmailsResultData | None:
    """
    Detect and normalize emails-related results from planner execution.

    Similar to _detect_and_normalize_contacts_result but for Gmail data.

    **Data Registry Mode Support** (Phase 5.2 BugFix 2025-11-26):
    When registry-enabled tools are used, step_results only contain summary_for_llm text.
    The actual emails data is in data_registry as RegistryItems with type="EMAIL".

    Args:
        step_results: List of tool result data dicts from completed steps.
        data_registry: Optional data registry dict with RegistryItems.
                      Used as fallback when step_results don't contain structured data.

    Returns:
        EmailsResultData if emails detected, None otherwise.
    """
    if not step_results and not data_registry:
        return None

    all_emails: list[dict[str, Any]] = []
    emails_dict: dict[str, dict[str, Any]] = {}  # message_id → email for deduplication
    data_source = "api"
    timestamp = None
    cache_age_seconds = None

    for result in step_results or []:
        if not isinstance(result, dict):
            continue

        # Detect emails key - check both root level and nested "data" structure
        # StepResult.result can be either:
        # - Direct data: {"emails": [...], "total": N}
        # - Wrapped: {"success": True, "data": {"emails": [...], "total": N}}
        emails_data = None
        metadata_source = result  # Where to get freshness metadata

        if "emails" in result and isinstance(result["emails"], list):
            # Direct structure
            emails_data = result["emails"]
        elif "data" in result and isinstance(result["data"], dict):
            # Wrapped structure - extract from "data"
            nested = result["data"]
            if "emails" in nested and isinstance(nested["emails"], list):
                emails_data = nested["emails"]
                metadata_source = nested

        if emails_data:
            for email in emails_data:
                message_id = email.get("id") or email.get("message_id")
                if message_id:
                    emails_dict[message_id] = email
                else:
                    all_emails.append(email)
        else:
            # Preserve freshness metadata from first result
            if timestamp is None:
                data_source = metadata_source.get("data_source", "api")
                timestamp = metadata_source.get(FIELD_TIMESTAMP)
                cache_age_seconds = metadata_source.get("cache_age_seconds")

    # Add deduplicated emails
    all_emails.extend(emails_dict.values())

    # ============================================================================
    # Data Registry MODE FALLBACK (Phase 5.2 BugFix 2025-11-26)
    # ============================================================================
    if not all_emails and data_registry:
        logger.info(
            "registry_fallback_extracting_emails_from_registry",
            registry_items_count=len(data_registry),
        )
        for item_id, item in data_registry.items():
            item_type = item.get("type", "")
            if item_type == "EMAIL":
                payload = item.get("payload", {})
                if payload:
                    message_id = payload.get("id") or payload.get("message_id") or item_id
                    if message_id not in emails_dict:
                        emails_dict[message_id] = payload
                        logger.debug(
                            "registry_email_extracted_from_registry",
                            item_id=item_id,
                            message_id=message_id,
                        )

        all_emails = list(emails_dict.values())
        data_source = "data_registry"

        if all_emails:
            logger.info(
                "registry_emails_extracted_successfully",
                emails_count=len(all_emails),
            )

    if not all_emails:
        return None

    from datetime import UTC, datetime

    return EmailsResultData(
        emails=all_emails,
        total=len(all_emails),
        query=None,
        data_source=data_source,
        timestamp=timestamp or datetime.now(UTC).isoformat(),
        cache_age_seconds=cache_age_seconds,
    )


def _detect_and_normalize_places_result(
    step_results: list[dict[str, Any]],
    data_registry: dict[str, Any] | None = None,
) -> PlacesResultData | None:
    """
    Detect and normalize places-related results from planner execution.

    Similar to _detect_and_normalize_contacts_result but for Google Places data.

    **Data Registry Mode Support**:
    When registry-enabled tools are used, step_results only contain summary_for_llm text.
    The actual places data is in data_registry as RegistryItems with type="PLACE".

    Args:
        step_results: List of tool result data dicts from completed steps.
        data_registry: Optional data registry dict with RegistryItems.
                      Used as fallback when step_results don't contain structured data.

    Returns:
        PlacesResultData if places detected, None otherwise.
    """
    if not step_results and not data_registry:
        return None

    all_places: list[dict[str, Any]] = []
    places_dict: dict[str, dict[str, Any]] = {}  # place_id → place for deduplication
    data_source = "api"
    timestamp = None
    cache_age_seconds = None
    location = None

    for result in step_results or []:
        if not isinstance(result, dict):
            continue

        # Detect places key - check both root level and nested "data" structure
        # StepResult.result can be either:
        # - Direct data: {"places": [...], "total": N}
        # - Wrapped: {"success": True, "data": {"places": [...], "total": N}}
        places_data = None
        metadata_source = result  # Where to get freshness metadata

        if "places" in result and isinstance(result["places"], list):
            # Direct structure
            places_data = result["places"]
        elif "data" in result and isinstance(result["data"], dict):
            # Wrapped structure - extract from "data"
            nested = result["data"]
            if "places" in nested and isinstance(nested["places"], list):
                places_data = nested["places"]
                metadata_source = nested

        if places_data:
            for place in places_data:
                place_id = place.get("id") or place.get("place_id")
                if place_id:
                    places_dict[place_id] = place
                else:
                    all_places.append(place)

            # Preserve freshness metadata from first result
            if timestamp is None:
                data_source = metadata_source.get("data_source", "api")
                timestamp = metadata_source.get(FIELD_TIMESTAMP)
                cache_age_seconds = metadata_source.get("cache_age_seconds")
                location = metadata_source.get("location")

    # Add deduplicated places
    all_places.extend(places_dict.values())

    # ============================================================================
    # Data Registry MODE FALLBACK
    # ============================================================================
    if not all_places and data_registry:
        logger.info(
            "registry_fallback_extracting_places_from_registry",
            registry_items_count=len(data_registry),
        )
        for item_id, item in data_registry.items():
            item_type = item.get("type", "")
            if item_type == "PLACE":
                payload = item.get("payload", {})
                if payload:
                    place_id = payload.get("id") or payload.get("place_id") or item_id
                    if place_id not in places_dict:
                        places_dict[place_id] = payload
                        logger.debug(
                            "registry_place_extracted_from_registry",
                            item_id=item_id,
                            place_id=place_id,
                        )

        all_places = list(places_dict.values())
        data_source = "data_registry"

        if all_places:
            logger.info(
                "registry_places_extracted_successfully",
                places_count=len(all_places),
            )

    if not all_places:
        return None

    from datetime import UTC, datetime

    return PlacesResultData(
        places=all_places,
        total_count=len(all_places),
        query=None,
        location=location,
        data_source=data_source,
        timestamp=timestamp or datetime.now(UTC).isoformat(),
        cache_age_seconds=cache_age_seconds,
    )


def map_execution_result_to_agent_result(
    execution_result: ExecutionResult,
    plan_id: str,
    turn_id: int,
    data_registry: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Map PlanExecutor ExecutionResult to agent_results format.

    This function converts the ExecutionResult from PlanExecutor into the
    agent_results format expected by the state graph and response_node.

    The agent_results format uses composite keys built by
    :func:`~src.domains.agents.constants.make_agent_result_key`:
    ``"{turn_id}:{agent_name}"`` — colon, not underscore — to track multiple
    agent executions within the same turn.

    **Phase 5.2B Enhancement - Generic Result Normalization**:
    Detects domain-specific results (contacts, emails, calendar, etc.) and
    normalizes them to domain-specific schemas (ContactsResultData, etc.)
    for consistent response_node handling.

    **Data Registry Mode Support** (Phase 5.2 BugFix 2025-11-26):
    When registry-enabled tools are used, step_results only contain summary_for_llm text.
    The data_registry parameter contains the full structured data from RegistryItems.
    This registry is passed to detection functions as fallback for data extraction.

    Args:
        execution_result: Result from PlanExecutor.execute_plan()
        plan_id: Unique identifier for the execution plan
        turn_id: Current turn ID in the conversation
        data_registry: Optional data registry dict with RegistryItems from parallel_executor.
                      Contains full structured data when tools run in Data Registry mode.

    Returns:
        Dict mapping composite_key → agent_result dict with structure:
        {
            "{turn_id}:plan_executor": {
                "agent_name": "plan_executor",
                "status": "success" | "failed",
                "data": ContactsResultData | dict,  // Normalized to domain schema if detected
                "error": str | None
            }
        }

    Example:
        >>> from orchestration.schemas import ExecutionResult, StepResult
        >>> result = ExecutionResult(
        ...     success=True,
        ...     completed_steps=2,
        ...     total_steps=2,
        ...     step_results=[
        ...         StepResult(
        ...             step_id="search",
        ...             success=True,
        ...             result={"data": {"contacts": [...], "total": 5}}
        ...         )
        ...     ]
        ... )
        >>> agent_results = map_execution_result_to_agent_result(
        ...     result, "plan123", turn_id=5
        ... )
        >>> agent_results["5_plan_executor"]["status"]
        'success'
        >>> agent_results["5_plan_executor"]["data"]["total_count"]
        5

    Note:
        - Aggregates all successful step results into aggregated_results
        - Extracts "data" field from tool results (standard tool response format)
        - **Auto-detects contacts results and normalizes to ContactsResultData**
        - **Registry mode: Extracts from data_registry when step_results contain only text**
        - Uses composite key pattern for state management
        - Does NOT add messages (response_node handles that)
    """
    # Aggregate all step results that contain data
    all_results_data = []
    # Data Registry LOT 5.2: Use data_registry directly as registry_updates
    # BugFix 2025-11-30: step_results are LegacyStepResult without registry_updates field.
    # The data_registry parameter contains the accumulated registry from parallel_executor.
    # This is the correct source for response_node to filter by current turn items.
    aggregated_registry_updates: dict[str, Any] = data_registry.copy() if data_registry else {}

    logger.info(
        "processing_step_results",
        plan_id=plan_id,
        total_steps=len(execution_result.step_results),
        step_details=[
            {
                "step_id": getattr(sr, "step_id", None) or getattr(sr, "step_index", None),
                "success": sr.success,
                "has_result": sr.result is not None,
                "result_type": type(sr.result).__name__ if sr.result else None,
                "has_data_key": (
                    isinstance(sr.result, dict) and "data" in sr.result if sr.result else False
                ),
                "has_registry_updates": getattr(sr, "registry_updates", None) is not None,
            }
            for sr in execution_result.step_results
        ],
    )

    for step_result in execution_result.step_results:
        if step_result.success and step_result.result:
            step_id = getattr(step_result, "step_id", None) or getattr(
                step_result, "step_index", None
            )

            # Data Registry LOT 5.2: Collect registry_updates from each step
            step_registry = getattr(step_result, "registry_updates", None)
            if step_registry:
                aggregated_registry_updates.update(step_registry)
                logger.debug(
                    "step_registry_updates_collected",
                    step_id=step_id,
                    items_count=len(step_registry),
                    item_ids=list(step_registry.keys()),
                )

            # Append the tool result AS THE EXECUTOR STORED IT — the full
            # ToolResponse envelope (`{"success", "message", "data", ...}`).
            # The previous comment claimed the executor had already unwrapped
            # `data`; it has not (`parallel_executor` passes `tool_result`
            # straight through, and reads `success`/`error` off it right above),
            # so consumers must go through `["data"]`.
            if isinstance(step_result.result, dict):
                # Skip CONDITIONAL steps (they have condition_result, not contacts data)
                if "condition_result" in step_result.result:
                    logger.debug(
                        "skipping_conditional_step",
                        step_id=step_id,
                    )
                    continue

                # This is a TOOL step result - add it directly
                all_results_data.append(step_result.result)
                logger.debug(
                    "step_result_added",
                    step_id=step_id,
                    result_keys=list(step_result.result.keys()),
                )

    # Create composite key for state tracking using standard format
    # FIX: Use make_agent_result_key() to ensure consistent colon format
    # Previous bug: Manual f"{turn_id}_plan_executor" used underscore instead of colon
    composite_key = make_agent_result_key(turn_id, "plan_executor")

    # ====================================================================
    # GENERIC RESULT NORMALIZATION (Phase 5.2B)
    # ====================================================================
    # Detect domain-specific results and normalize to typed schemas
    # This enables response_node to handle planner results the same way
    # as direct agent results.
    #
    # Strategy: Detect domain-specific keys and normalize to typed schemas
    # - "contacts" → ContactsResultData
    # - "emails" → EmailsResultData
    # - "places" → PlacesResultData
    #
    # Data Registry Mode (BugFix 2025-11-26): When tools run with registry_enabled=True,
    # step_results only contain summary_for_llm text. The data_registry
    # parameter contains the full structured data and is passed as fallback.
    # ====================================================================

    normalized_data: (
        ContactsResultData
        | EmailsResultData
        | PlacesResultData
        | MultiDomainResultData
        | dict[str, Any]
    )

    # Check if this is a contacts-related result
    logger.info(
        "attempting_result_normalization",
        composite_key=composite_key,
        results_count=len(all_results_data),
        results_preview=str(all_results_data)[:500] if all_results_data else "EMPTY",
        data_registry_provided=data_registry is not None,
        data_registry_items=len(data_registry) if data_registry else 0,
    )

    # Pass data_registry as fallback for Data Registry mode (BugFix 2025-11-26)
    contacts_result = _detect_and_normalize_contacts_result(all_results_data, data_registry)
    emails_result = _detect_and_normalize_emails_result(all_results_data, data_registry)
    places_result = _detect_and_normalize_places_result(all_results_data, data_registry)

    # Count how many domain results we have
    domain_results_count = sum(
        1 for r in [contacts_result, emails_result, places_result] if r is not None
    )

    # MULTI-DOMAIN CHECK: If 2+ domains exist, use MultiDomainResultData
    # This ensures Pydantic doesn't accidentally coerce to single-domain schema
    if domain_results_count >= 2:
        # Build completed_steps dict from step_results
        completed_steps_dict: dict[str, Any] = {}
        for step_result in execution_result.step_results:
            if step_result.success and step_result.result:
                step_id = getattr(step_result, "step_id", None) or str(
                    getattr(step_result, "step_index", 0)
                )
                completed_steps_dict[step_id] = step_result.result

        # Multi-domain: Use dedicated schema with distinct field names
        normalized_data = MultiDomainResultData(
            plan_id=plan_id,
            completed_steps=completed_steps_dict,
            total_steps=execution_result.total_steps,
            execution_time_ms=execution_result.total_execution_time_ms,
            # Contacts data with distinct field names
            contacts=contacts_result.contacts if contacts_result else [],
            contacts_total=contacts_result.total_count if contacts_result else 0,
            # Emails data with distinct field names
            emails=emails_result.emails if emails_result else [],
            emails_total=emails_result.total if emails_result else 0,
            # Places data with distinct field names
            places=places_result.places if places_result else [],
            places_total=places_result.total_count if places_result else 0,
            # Metadata (use first available)
            data_source=(
                contacts_result.data_source
                if contacts_result
                else (
                    emails_result.data_source
                    if emails_result
                    else (places_result.data_source if places_result else "api")
                )
            ),
            timestamp=(
                contacts_result.timestamp
                if contacts_result
                else (
                    emails_result.timestamp
                    if emails_result
                    else (places_result.timestamp if places_result else "")
                )
            ),
        )
        logger.info(
            "planner_result_multi_domain",
            composite_key=composite_key,
            contacts_count=contacts_result.total_count if contacts_result else 0,
            emails_count=emails_result.total if emails_result else 0,
            places_count=places_result.total_count if places_result else 0,
        )
    elif contacts_result:
        normalized_data = contacts_result
        logger.info(
            "planner_result_normalized_to_contacts",
            composite_key=composite_key,
            total_count=contacts_result.total_count,
        )
    elif emails_result:
        normalized_data = emails_result
        logger.info(
            "planner_result_normalized_to_emails",
            composite_key=composite_key,
            total_count=emails_result.total,
        )
    elif places_result:
        normalized_data = places_result
        logger.info(
            "planner_result_normalized_to_places",
            composite_key=composite_key,
            total_count=places_result.total_count,
        )
    else:
        # Fallback: Generic format (future agents will add their own detection)
        normalized_data = {
            FIELD_PLAN_ID: plan_id,
            "completed_steps": execution_result.completed_steps,
            "total_steps": execution_result.total_steps,
            "execution_time_ms": execution_result.total_execution_time_ms,
            "step_results": all_results_data,
            # For response synthesis: combine all results
            "aggregated_results": all_results_data,
        }

    # Whatever shape the normalization chose, the tools' own words survive.
    # Each typed branch above REPLACES the generic envelope, and only the
    # fallback carried `step_results` — so a plan touching two known domains
    # silently dropped every action confirmation, sub-agent analysis and the
    # 360° briefing (measured 2026-08-01: the assistant answered "I have no
    # data at hand" while holding the whole payload). The field lives on
    # `AgentResultData` precisely so this holds for every subclass, present
    # and future.
    if isinstance(normalized_data, AgentResultData):
        normalized_data.step_results = all_results_data

    # Build agent_result entry (Phase 3.2.5: Use Pydantic AgentResult)
    # Data Registry LOT 5.2: Include aggregated registry_updates for response_node filtering

    # Aggregate tokens from all step results
    # Tools may report tokens in their result dict (tokens_in, tokens_out)
    total_tokens_in = 0
    total_tokens_out = 0
    for step_result in execution_result.step_results:
        if hasattr(step_result, "result") and isinstance(step_result.result, dict):
            total_tokens_in += step_result.result.get("tokens_in", 0)
            total_tokens_out += step_result.result.get("tokens_out", 0)

    agent_result = AgentResult(
        agent_name="plan_executor",
        status="success" if execution_result.success else "failed",
        data=normalized_data,
        error=execution_result.error if not execution_result.success else None,
        tokens_in=total_tokens_in,  # Aggregated from step results
        tokens_out=total_tokens_out,
        duration_ms=execution_result.total_execution_time_ms,
        registry_updates=aggregated_registry_updates if aggregated_registry_updates else None,
    )

    if aggregated_registry_updates:
        logger.info(
            "agent_result_registry_updates_included",
            composite_key=composite_key,
            registry_items_count=len(aggregated_registry_updates),
            registry_item_ids=list(aggregated_registry_updates.keys()),
        )

    logger.debug(
        "execution_result_mapped_to_agent_result",
        composite_key=composite_key,
        status=agent_result.status,
        completed_steps=execution_result.completed_steps,
        total_steps=execution_result.total_steps,
        aggregated_count=len(all_results_data),
        normalized_format=type(normalized_data).__name__,
    )

    # Return as dict for state compatibility (Phase 3.2.5: model_dump() for serialization)
    return {composite_key: agent_result.model_dump()}


__all__ = ["map_execution_result_to_agent_result"]
