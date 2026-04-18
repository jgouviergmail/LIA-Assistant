"""
HITL Dispatch Node - Generic Human-in-the-Loop Dispatcher.

Routes pending HITL requests to appropriate handlers based on type.
Supports multiple HITL interaction types with priority ordering.

Architecture:
    1. Check pending HITL requests in priority order:
       - Draft Critique (highest priority)
       - Entity Disambiguation (medium priority)
       - Tool Confirmation (lowest priority)
    2. Dispatch to appropriate handler
    3. Return state updates from handler

Priority Rationale:
    Draft > Disambiguation > Confirmation because:
    - Don't confirm an action if we don't know which "Jean" to apply it to
    - Don't show draft preview if entity selection is still pending

Flow:
    TaskOrchestrator → HitlDispatchNode → [DraftCritique | EntityDisambiguation | ToolConfirmation]
                                        ↓
                               interrupt() → User Decision → Resume
                                        ↓
                               State update → Next node

References:
    - draft_critique_node.py: Original draft critique implementation
    - EntityDisambiguationInteraction: HITL for multiple matches
    - ToolConfirmationInteraction: HITL for tools without drafts

Created: 2025-12-23
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.core.config import settings
from src.domains.agents.constants import (
    DEFAULT_CONTACT_NAME,
    PEOPLE_API_FIELD_DISPLAY_NAME,
    PEOPLE_API_FIELD_EMAIL_ADDRESSES,
    PEOPLE_API_FIELD_NAMES,
    PEOPLE_API_FIELD_VALUE,
    REGISTRY_TYPE_CONTACT,
)
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.utils.state_tracking import track_state_updates
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
)

logger = structlog.get_logger(__name__)

# ============================================================================
# STATE KEYS
# ============================================================================

# Draft Critique (existing)
STATE_KEY_PENDING_DRAFT_CRITIQUE = "pending_draft_critique"
STATE_KEY_PENDING_DRAFTS_QUEUE = "pending_drafts_queue"
STATE_KEY_DRAFT_ACTION_RESULT = "draft_action_result"

# Entity Disambiguation (new)
STATE_KEY_PENDING_ENTITY_DISAMBIGUATION = "pending_entity_disambiguation"
STATE_KEY_ENTITY_DISAMBIGUATION_RESULT = "entity_disambiguation_result"
STATE_KEY_PENDING_DISAMBIGUATIONS_QUEUE = "pending_disambiguations_queue"

# Tool Confirmation (new)
STATE_KEY_PENDING_TOOL_CONFIRMATION = "pending_tool_confirmation"
STATE_KEY_TOOL_CONFIRMATION_RESULT = "tool_confirmation_result"

STATE_KEY_REGISTRY = "registry"

# Draft type change mappings (2026-04 — homogenized draft structures)
_TYPE_TO_DELETE: dict[str, str] = {
    "event_update": "event_delete",
    "contact_update": "contact_delete",
    "task_update": "task_delete",
    "email_reply": "email_delete",
    "email_forward": "email_delete",
}
_UPDATABLE_DELETE_TYPES: dict[str, str] = {
    "event_delete": "event_update",
    "contact_delete": "contact_update",
    "task_delete": "task_update",
}
_DRAFT_TYPE_TO_TOOL: dict[str, str] = {
    "event_update": "update_event_tool",
    "event_delete": "delete_event_tool",
    "contact_update": "update_contact_tool",
    "contact_delete": "delete_contact_tool",
    "task_update": "update_task_tool",
    "task_delete": "delete_task_tool",
    "email_delete": "delete_email_tool",
}
_PRESERVED_FIELDS_FOR_DIFF: set[str] = {
    "event_id",
    "calendar_id",
    "timezone",
    "send_updates",
    "resource_name",
    "task_id",
    "task_list_id",
    "current_event",
    "current_contact",
    "current_task",
    "related_registry_ids",
    "user_language",
    "user_timezone",
}


# ============================================================================
# HELPER FUNCTIONS - DRAFT CRITIQUE
# ============================================================================


async def _build_contact_context(
    state: MessagesState,
    registry_ids: list[str] | None = None,  # noqa: ARG001 - kept for API compat
) -> list[dict[str, Any]] | None:
    """
    Build contact context from registry for draft modification.

    FIX 2026-01-11: Extracts contact email addresses from the ENTIRE registry
    to enable resolution of references like "@carven" during draft modification.

    BUG FIX 2026-01-11: Previously searched only in registry_ids which only
    contained draft_id. Now searches ALL registry items to find contacts
    added by previous steps (e.g., get_contacts_tool).

    Args:
        state: Graph state containing registry
        registry_ids: DEPRECATED - kept for API compatibility but no longer used.
            The function now scans all registry items.

    Returns:
        List of contact dicts with name and emails, or None if no contacts found
    """
    registry = state.get(STATE_KEY_REGISTRY, {})
    if not registry:
        return None

    contacts: list[dict[str, Any]] = []

    # FIX: Scan ALL registry items, not just the limited registry_ids
    for reg_id, item in registry.items():
        if not item:
            continue

        # Handle both dict and RegistryItem object formats
        # FIX 2026-01-11: Use "payload" (not "data") - RegistryItem structure
        if isinstance(item, dict):
            item_type = item.get("type", "")
            payload = item.get("payload", {})
        else:
            item_type = getattr(item, "type", "")
            payload = getattr(item, "payload", {})

        # Handle RegistryItemType enum (value is uppercase: "CONTACT")
        if hasattr(item_type, "value"):
            item_type = item_type.value

        # Only process contact items (case-insensitive comparison)
        # RegistryItemType.CONTACT.value = "CONTACT", REGISTRY_TYPE_CONTACT = "contact"
        if item_type.upper() != REGISTRY_TYPE_CONTACT.upper():
            continue

        # Extract contact name using Google People API field names
        names = payload.get(PEOPLE_API_FIELD_NAMES, [])
        name = (
            names[0].get(PEOPLE_API_FIELD_DISPLAY_NAME, DEFAULT_CONTACT_NAME)
            if names
            else DEFAULT_CONTACT_NAME
        )

        # Extract all email addresses
        email_addresses = payload.get(PEOPLE_API_FIELD_EMAIL_ADDRESSES, [])
        emails = [
            e.get(PEOPLE_API_FIELD_VALUE, "")
            for e in email_addresses
            if e.get(PEOPLE_API_FIELD_VALUE)
        ]

        if emails:
            contacts.append({"name": name, "emails": emails})
            logger.debug(
                "contact_context_extracted",
                registry_id=reg_id,
                name=name,
                email_count=len(emails),
            )

    if contacts:
        logger.info(
            "contact_context_built",
            total_contacts=len(contacts),
            total_emails=sum(len(c["emails"]) for c in contacts),
            registry_size=len(registry),
        )
    else:
        logger.debug(
            "contact_context_empty",
            registry_size=len(registry),
            registry_types=[
                item.get("type") if isinstance(item, dict) else getattr(item, "type", "unknown")
                for item in registry.values()
                if item
            ],
        )

    return contacts if contacts else None


def _build_draft_critique_payload(
    pending_draft: PendingDraftInfo,
    user_language: str = "fr",
    batch_total: int = 1,
    batch_drafts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build interrupt payload for draft critique HITL.

    The payload structure is compatible with StreamingService which will:
    1. Detect action_requests[type="draft_critique"]
    2. Create DraftCritiqueInteraction via registry
    3. Stream the contextual review question (generated via LLM for single,
       static for batch)
    4. Wait for user action (confirm/edit/cancel)

    Args:
        pending_draft: Draft information from parallel_executor (first item)
        user_language: User's language for question generation
        batch_total: Total number of items in batch (1 = single draft, >1 = batch)
        batch_drafts: All draft contents for batch display (when batch_total > 1)

    Returns:
        Interrupt payload for HITL processing
    """
    action_request: dict[str, Any] = {
        "type": "draft_critique",
        "draft_id": pending_draft.draft_id,
        "draft_type": pending_draft.draft_type,
        "draft_content": pending_draft.draft_content,
        "registry_ids": pending_draft.registry_ids,
        "tool_name": pending_draft.tool_name,
        "step_id": pending_draft.step_id,
    }

    # Batch context: passes all draft contents for static batch confirmation
    if batch_total > 1:
        action_request["batch_total"] = batch_total
        action_request["batch_drafts"] = batch_drafts or []

    return {
        "action_requests": [action_request],
        "generate_question_streaming": True,
        "user_language": user_language,
        "hitl_type": HitlInteractionType.DRAFT_CRITIQUE.value,
    }


def _process_draft_action(
    decision_data: dict[str, Any],
    pending_draft: PendingDraftInfo,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """
    Process user's draft action decision.

    Args:
        decision_data: User decision from interrupt resume
        pending_draft: Original draft information

    Returns:
        Tuple (action, updated_content, error_message)
    """
    action = decision_data.get("action", "cancel")
    draft_id = decision_data.get("draft_id", pending_draft.draft_id)

    if draft_id != pending_draft.draft_id:
        logger.warning(
            "draft_action_id_mismatch",
            expected_id=pending_draft.draft_id,
            received_id=draft_id,
        )
        return "cancel", None, f"Draft ID mismatch: expected {pending_draft.draft_id}"

    if action == "confirm":
        logger.info(
            "draft_action_confirmed",
            draft_id=draft_id,
            draft_type=pending_draft.draft_type,
        )
        return "confirm", None, None

    elif action == "edit":
        updated_content = decision_data.get("updated_content", {})
        if not updated_content:
            return "edit", pending_draft.draft_content, None
        logger.info(
            "draft_action_edited",
            draft_id=draft_id,
            draft_type=pending_draft.draft_type,
            updated_fields=list(updated_content.keys()),
        )
        return "edit", updated_content, None

    elif action == "cancel":
        logger.info(
            "draft_action_cancelled",
            draft_id=draft_id,
            draft_type=pending_draft.draft_type,
        )
        return "cancel", None, None

    else:
        logger.warning(
            "draft_action_unknown",
            draft_id=draft_id,
            action=action,
        )
        return "cancel", None, f"Unknown action: {action}"


# ============================================================================
# HELPER FUNCTIONS - ENTITY DISAMBIGUATION
# ============================================================================


def _build_entity_disambiguation_payload(
    pending_disambiguation: dict[str, Any],
    user_language: str = "fr",
) -> dict[str, Any]:
    """
    Build interrupt payload for entity disambiguation HITL.

    Args:
        pending_disambiguation: DisambiguationContext from entity resolution
        user_language: User's language for question generation

    Returns:
        Interrupt payload for HITL processing
    """
    return {
        "action_requests": [
            {
                "type": "entity_disambiguation",
                "disambiguation_type": pending_disambiguation.get(
                    "disambiguation_type", "multiple_entities"
                ),
                "candidates": pending_disambiguation.get("candidates", []),
                "original_query": pending_disambiguation.get("original_query", ""),
                "domain": pending_disambiguation.get("domain", "contacts"),
                "target_field": pending_disambiguation.get("target_field"),
            }
        ],
        "generate_question_streaming": True,
        "user_language": user_language,
        "hitl_type": HitlInteractionType.ENTITY_DISAMBIGUATION.value,
    }


def _process_entity_disambiguation_decision(
    decision_data: dict[str, Any],
    pending_disambiguation: dict[str, Any],
) -> tuple[str, dict[str, Any] | None, str | None]:
    """
    Process user's entity disambiguation decision.

    Args:
        decision_data: User decision from interrupt resume
        pending_disambiguation: Original disambiguation context

    Returns:
        Tuple (action, selected_entity, error_message)
    """
    action = decision_data.get("action", "cancel")

    if action == "select":
        selected_index = decision_data.get("selected_index")
        selected_value = decision_data.get("selected_value")

        candidates = pending_disambiguation.get("candidates", [])

        if selected_index is not None and 0 <= selected_index < len(candidates):
            selected_entity = candidates[selected_index]
            logger.info(
                "entity_disambiguation_selected",
                selected_index=selected_index,
                domain=pending_disambiguation.get("domain"),
            )
            return "select", selected_entity, None
        elif selected_value:
            logger.info(
                "entity_disambiguation_value_selected",
                selected_value=selected_value[:50] if selected_value else None,
            )
            return "select", {"value": selected_value}, None
        else:
            logger.warning(
                "entity_disambiguation_invalid_selection",
                selected_index=selected_index,
                candidates_count=len(candidates),
            )
            return "cancel", None, "Invalid selection"

    elif action == "cancel":
        logger.info("entity_disambiguation_cancelled")
        return "cancel", None, None

    else:
        logger.warning(
            "entity_disambiguation_unknown_action",
            action=action,
        )
        return "cancel", None, f"Unknown action: {action}"


# ============================================================================
# HELPER FUNCTIONS - TOOL CONFIRMATION
# ============================================================================


def _build_tool_confirmation_payload(
    pending_confirmation: dict[str, Any],
    user_language: str = "fr",
) -> dict[str, Any]:
    """
    Build interrupt payload for tool confirmation HITL.

    Args:
        pending_confirmation: ToolConfirmationContext from tool executor
        user_language: User's language for question generation

    Returns:
        Interrupt payload for HITL processing
    """
    return {
        "action_requests": [
            {
                "type": "tool_confirmation",
                "tool_name": pending_confirmation.get("tool_name", ""),
                "tool_args": pending_confirmation.get("tool_args", {}),
                "confirmation_message": pending_confirmation.get("confirmation_message", ""),
                "step_id": pending_confirmation.get("step_id"),
            }
        ],
        "generate_question_streaming": True,
        "user_language": user_language,
        "hitl_type": HitlInteractionType.TOOL_CONFIRMATION.value,
    }


def _process_tool_confirmation_decision(
    decision_data: dict[str, Any],
    pending_confirmation: dict[str, Any],
) -> tuple[str, str | None]:
    """
    Process user's tool confirmation decision.

    Args:
        decision_data: User decision from interrupt resume
        pending_confirmation: Original confirmation context

    Returns:
        Tuple (action, error_message)
    """
    action = decision_data.get("action", "cancel")

    if action == "confirm":
        logger.info(
            "tool_confirmation_confirmed",
            tool_name=pending_confirmation.get("tool_name"),
        )
        return "confirm", None

    elif action == "cancel":
        logger.info(
            "tool_confirmation_cancelled",
            tool_name=pending_confirmation.get("tool_name"),
        )
        return "cancel", None

    else:
        logger.warning(
            "tool_confirmation_unknown_action",
            action=action,
        )
        return "cancel", f"Unknown action: {action}"


# ============================================================================
# STATE TRACKING
# ============================================================================


# ============================================================================
# HITL DISPATCH NODE
# ============================================================================


@track_metrics(
    node_name="hitl_dispatch",
    duration_metric=agent_node_duration_seconds,
    counter_metric=agent_node_executions_total,
    log_execution=True,
    log_errors=True,
)
async def hitl_dispatch_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """
    HITL Dispatch Node - Routes to appropriate HITL handler.

    Checks pending HITL requests in priority order:
    1. Draft Critique (highest) - don't preview draft if entity unclear
    2. Entity Disambiguation (medium) - resolve entities before confirmation
    3. Tool Confirmation (lowest) - only confirm when all context is clear

    NOTE: Tool approval is always enabled (no kill switch).

    Args:
        state: Graph state with potential pending HITL requests
        config: LangGraph configuration

    Returns:
        State update with appropriate result key set
    """
    start_time = time.time()

    user_language = state.get("user_language", "fr")

    # =========================================================================
    # PRIORITY 1: Draft Critique
    # =========================================================================
    pending_draft_data = state.get(STATE_KEY_PENDING_DRAFT_CRITIQUE)
    if pending_draft_data:
        return await _handle_draft_critique(state, pending_draft_data, user_language, start_time)

    # =========================================================================
    # PRIORITY 2: Entity Disambiguation
    # =========================================================================
    pending_disambiguation = state.get(STATE_KEY_PENDING_ENTITY_DISAMBIGUATION)
    if pending_disambiguation:
        return await _handle_entity_disambiguation(
            state, pending_disambiguation, user_language, start_time
        )

    # =========================================================================
    # PRIORITY 3: Tool Confirmation
    # =========================================================================
    pending_confirmation = state.get(STATE_KEY_PENDING_TOOL_CONFIRMATION)
    if pending_confirmation:
        return await _handle_tool_confirmation(
            state, pending_confirmation, user_language, start_time
        )

    # No pending HITL requests - pass through
    logger.debug("hitl_dispatch_no_pending_requests")
    return {}


async def _handle_draft_critique(
    state: MessagesState,
    pending_draft_data: dict[str, Any],
    user_language: str,
    start_time: float,
) -> dict[str, Any]:
    """Handle draft critique HITL flow with iterative modification support.

    This function implements the iterative draft modification loop:
    1. Present draft for validation
    2. User can: confirm, cancel, or request modification
    3. If modification requested:
       - Regenerate content using DraftModificationService
       - Re-present the modified draft for validation
       - Loop until user confirms or cancels
    """
    if isinstance(pending_draft_data, dict):
        pending_draft = PendingDraftInfo(**pending_draft_data)
    else:
        pending_draft = pending_draft_data

    logger.info(
        "hitl_dispatch_draft_critique",
        draft_id=pending_draft.draft_id,
        draft_type=pending_draft.draft_type,
    )

    # Iterative modification loop
    # User can request multiple modifications before confirming
    # Safety limit: max iterations = max items possible in a request
    max_iterations = settings.api_max_items_per_request
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # Build and send interrupt (include batch context for UX)
        drafts_queue = state.get(STATE_KEY_PENDING_DRAFTS_QUEUE, [])
        batch_total = 1 + len(drafts_queue)
        # For batch: collect all draft contents (current + queued) for display
        batch_drafts = [pending_draft.model_dump()] + drafts_queue if batch_total > 1 else None
        interrupt_payload = _build_draft_critique_payload(
            pending_draft,
            user_language,
            batch_total=batch_total,
            batch_drafts=batch_drafts,
        )
        decision_data = interrupt(interrupt_payload)

        elapsed_time = time.time() - start_time
        logger.info(
            "hitl_dispatch_draft_decision_received",
            draft_id=pending_draft.draft_id,
            action=decision_data.get("action") if decision_data else None,
            iteration=iteration,
            latency_seconds=elapsed_time,
        )

        # Handle no decision
        if not decision_data:
            result: dict[str, Any] = {
                STATE_KEY_DRAFT_ACTION_RESULT: {
                    "action": "cancel",
                    "draft_id": pending_draft.draft_id,
                    "reason": "No decision received",
                },
                STATE_KEY_PENDING_DRAFT_CRITIQUE: None,
            }
            track_state_updates(state, result, "hitl_dispatch", pending_draft.draft_id)
            return result

        action = decision_data.get("action", "cancel")

        # === CONFIRM: Execute the draft (+ queued batch if any) ===
        if action == "confirm":
            # Build batch result: current draft + all queued drafts
            # When a FOR_EACH HITL was already approved, the user confirmed
            # the batch operation. The per-item draft critique shows the first
            # item; on confirm, ALL queued items are auto-confirmed too.
            drafts_queue = state.get(STATE_KEY_PENDING_DRAFTS_QUEUE, [])

            batch_results = [
                {
                    "action": "confirm",
                    "draft_id": pending_draft.draft_id,
                    "draft_type": pending_draft.draft_type,
                    "draft_content": pending_draft.draft_content,
                },
            ]

            # Auto-confirm queued drafts from the same FOR_EACH batch
            for queued_draft_data in drafts_queue:
                batch_results.append(
                    {
                        "action": "confirm",
                        "draft_id": queued_draft_data.get("draft_id", ""),
                        "draft_type": queued_draft_data.get("draft_type", ""),
                        "draft_content": queued_draft_data.get("draft_content", {}),
                    }
                )

            if len(batch_results) > 1:
                logger.info(
                    "hitl_dispatch_batch_draft_confirmed",
                    primary_draft_id=pending_draft.draft_id,
                    batch_size=len(batch_results),
                    draft_ids=[r["draft_id"] for r in batch_results],
                )

            result = {
                STATE_KEY_PENDING_DRAFT_CRITIQUE: None,
                STATE_KEY_PENDING_DRAFTS_QUEUE: [],
                STATE_KEY_DRAFT_ACTION_RESULT: (
                    batch_results[0]
                    if len(batch_results) == 1
                    else {
                        "action": DraftAction.CONFIRM_BATCH.value,
                        "batch": batch_results,
                    }
                ),
            }
            track_state_updates(state, result, "hitl_dispatch", pending_draft.draft_id)
            return result

        # === CANCEL: Abort the draft (+ cancel all queued) ===
        elif action == "cancel":
            reason = decision_data.get("reason", "User cancelled")
            result = {
                STATE_KEY_PENDING_DRAFT_CRITIQUE: None,
                STATE_KEY_PENDING_DRAFTS_QUEUE: [],
                STATE_KEY_DRAFT_ACTION_RESULT: {
                    "action": "cancel",
                    "draft_id": pending_draft.draft_id,
                    "draft_type": pending_draft.draft_type,
                    "reason": reason,
                },
            }
            track_state_updates(state, result, "hitl_dispatch", pending_draft.draft_id)
            return result

        # === REPLAN: User wants a different action type (LLM classifier detected) ===
        elif action == "replan":
            new_type = _TYPE_TO_DELETE.get(pending_draft.draft_type)
            if new_type:
                logger.info(
                    "hitl_draft_type_changed_via_replan",
                    draft_id=pending_draft.draft_id,
                    from_type=pending_draft.draft_type,
                    to_type=new_type,
                    instructions=decision_data.get("modification_instructions", "")[:80],
                )
                pending_draft = PendingDraftInfo(
                    draft_id=pending_draft.draft_id,
                    draft_type=new_type,
                    draft_content=pending_draft.draft_content,
                    draft_summary="",
                    registry_ids=pending_draft.registry_ids,
                    tool_name=_DRAFT_TYPE_TO_TOOL.get(new_type, pending_draft.tool_name),
                    step_id=pending_draft.step_id,
                )
                continue
            else:
                logger.warning(
                    "hitl_replan_no_target_type",
                    draft_id=pending_draft.draft_id,
                    draft_type=pending_draft.draft_type,
                )
                continue

        # === EDIT: Modify the draft and re-present for validation ===
        elif action == "edit":
            modification_instructions = decision_data.get("modification_instructions", "")

            if not modification_instructions:
                logger.warning(
                    "hitl_dispatch_draft_edit_no_instructions",
                    draft_id=pending_draft.draft_id,
                    iteration=iteration,
                )
                continue

            logger.info(
                "hitl_dispatch_draft_modification_requested",
                draft_id=pending_draft.draft_id,
                draft_type=pending_draft.draft_type,
                instructions=modification_instructions[:100],
                iteration=iteration,
            )

            new_draft_type = pending_draft.draft_type

            try:
                from src.domains.agents.services.hitl.draft_modifier import (
                    get_draft_modification_service,
                )

                contact_context = await _build_contact_context(state, pending_draft.registry_ids)

                modifier = get_draft_modification_service()
                modified_content = await modifier.modify(
                    original_draft=pending_draft.draft_content,
                    instructions=modification_instructions,
                    draft_type=pending_draft.draft_type,
                    user_language=user_language,
                    run_id=pending_draft.draft_id,
                    contact_context=contact_context,
                )

                # Detect DELETE → UPDATE: modifier produced content changes
                # on a delete draft → user wants to update, not delete
                if pending_draft.draft_type in _UPDATABLE_DELETE_TYPES:
                    content_changes = [
                        k
                        for k in modified_content
                        if k not in _PRESERVED_FIELDS_FOR_DIFF
                        and (
                            k not in pending_draft.draft_content
                            or modified_content[k] != pending_draft.draft_content.get(k)
                        )
                    ]
                    if content_changes:
                        new_draft_type = _UPDATABLE_DELETE_TYPES[pending_draft.draft_type]
                        logger.info(
                            "hitl_draft_type_changed_to_update",
                            draft_id=pending_draft.draft_id,
                            from_type=pending_draft.draft_type,
                            to_type=new_draft_type,
                            content_changes=content_changes,
                        )

                logger.info(
                    "hitl_dispatch_draft_modified",
                    draft_id=pending_draft.draft_id,
                    draft_type=new_draft_type,
                    original_type=pending_draft.draft_type,
                    type_changed=new_draft_type != pending_draft.draft_type,
                    modified_fields=list(modified_content.keys()),
                    iteration=iteration,
                )

                pending_draft = PendingDraftInfo(
                    draft_id=pending_draft.draft_id,
                    draft_type=new_draft_type,
                    draft_content=modified_content,
                    draft_summary="",
                    registry_ids=pending_draft.registry_ids,
                    tool_name=_DRAFT_TYPE_TO_TOOL.get(new_draft_type, pending_draft.tool_name),
                    step_id=pending_draft.step_id,
                )

                # Continue loop to re-present for validation

            except Exception as e:
                logger.error(
                    "hitl_dispatch_draft_modification_failed",
                    draft_id=pending_draft.draft_id,
                    error=str(e),
                    iteration=iteration,
                )
                # On error, treat as cancel (clear queue too)
                result = {
                    STATE_KEY_PENDING_DRAFT_CRITIQUE: None,
                    STATE_KEY_PENDING_DRAFTS_QUEUE: [],
                    STATE_KEY_DRAFT_ACTION_RESULT: {
                        "action": "cancel",
                        "draft_id": pending_draft.draft_id,
                        "draft_type": pending_draft.draft_type,
                        "reason": f"Modification error: {e!s}",
                    },
                }
                track_state_updates(state, result, "hitl_dispatch", pending_draft.draft_id)
                return result

        # === CLARIFY: Ask user to clarify their request ===
        elif action == "clarify":
            clarification_question = decision_data.get(
                "clarification_question", "Peux-tu préciser ce que tu veux modifier ?"
            )
            logger.info(
                "hitl_dispatch_draft_clarification_needed",
                draft_id=pending_draft.draft_id,
                clarification_question=clarification_question[:100],
                iteration=iteration,
            )
            # For now, continue the loop to re-ask
            # In the future, we could send the clarification question to the user
            continue

        else:
            # Unknown action - treat as cancel (clear queue too)
            logger.warning(
                "hitl_dispatch_draft_unknown_action",
                draft_id=pending_draft.draft_id,
                action=action,
                iteration=iteration,
            )
            result = {
                STATE_KEY_PENDING_DRAFT_CRITIQUE: None,
                STATE_KEY_PENDING_DRAFTS_QUEUE: [],
                STATE_KEY_DRAFT_ACTION_RESULT: {
                    "action": "cancel",
                    "draft_id": pending_draft.draft_id,
                    "draft_type": pending_draft.draft_type,
                    "reason": f"Unknown action: {action}",
                },
            }
            track_state_updates(state, result, "hitl_dispatch", pending_draft.draft_id)
            return result

    # Max iterations reached - safety cancel (clear queue too)
    logger.warning(
        "hitl_dispatch_draft_max_iterations",
        draft_id=pending_draft.draft_id,
        max_iterations=max_iterations,
    )
    result = {
        STATE_KEY_PENDING_DRAFT_CRITIQUE: None,
        STATE_KEY_PENDING_DRAFTS_QUEUE: [],
        STATE_KEY_DRAFT_ACTION_RESULT: {
            "action": "cancel",
            "draft_id": pending_draft.draft_id,
            "draft_type": pending_draft.draft_type,
            "reason": "Maximum modification iterations reached",
        },
    }
    track_state_updates(state, result, "hitl_dispatch", pending_draft.draft_id)
    return result


async def _handle_entity_disambiguation(
    state: MessagesState,
    pending_disambiguation: dict[str, Any],
    user_language: str,
    start_time: float,
) -> dict[str, Any]:
    """Handle entity disambiguation HITL flow."""
    logger.info(
        "hitl_dispatch_entity_disambiguation",
        domain=pending_disambiguation.get("domain"),
        candidates_count=len(pending_disambiguation.get("candidates", [])),
    )

    # Build and send interrupt
    interrupt_payload = _build_entity_disambiguation_payload(pending_disambiguation, user_language)
    decision_data = interrupt(interrupt_payload)

    elapsed_time = time.time() - start_time
    logger.info(
        "hitl_dispatch_disambiguation_decision_received",
        action=decision_data.get("action") if decision_data else None,
        latency_seconds=elapsed_time,
    )

    # Handle no decision
    if not decision_data:
        no_decision_result: dict[str, Any] = {
            STATE_KEY_ENTITY_DISAMBIGUATION_RESULT: {
                "action": "cancel",
                "reason": "No decision received",
            },
            STATE_KEY_PENDING_ENTITY_DISAMBIGUATION: None,
        }
        track_state_updates(state, no_decision_result, "hitl_dispatch")
        return no_decision_result

    # Process decision
    action, selected_entity, error = _process_entity_disambiguation_decision(
        decision_data, pending_disambiguation
    )

    result: dict[str, Any] = {STATE_KEY_PENDING_ENTITY_DISAMBIGUATION: None}

    if action == "select":
        result[STATE_KEY_ENTITY_DISAMBIGUATION_RESULT] = {
            "action": "select",
            "selected_entity": selected_entity,
            "domain": pending_disambiguation.get("domain"),
        }
    elif action == "cancel":
        result[STATE_KEY_ENTITY_DISAMBIGUATION_RESULT] = {
            "action": "cancel",
            "reason": error or "User cancelled",
        }

    # Check disambiguation queue for multi-disambiguation protection
    queue = state.get(STATE_KEY_PENDING_DISAMBIGUATIONS_QUEUE, [])
    if queue:
        # Pop next disambiguation from queue
        next_disambiguation = queue[0]
        remaining_queue = queue[1:]
        result[STATE_KEY_PENDING_ENTITY_DISAMBIGUATION] = next_disambiguation
        result[STATE_KEY_PENDING_DISAMBIGUATIONS_QUEUE] = remaining_queue
        logger.info(
            "hitl_dispatch_disambiguation_queue_pop",
            remaining_in_queue=len(remaining_queue),
        )

    track_state_updates(state, result, "hitl_dispatch")
    return result


async def _handle_tool_confirmation(
    state: MessagesState,
    pending_confirmation: dict[str, Any],
    user_language: str,
    start_time: float,
) -> dict[str, Any]:
    """Handle tool confirmation HITL flow."""
    logger.info(
        "hitl_dispatch_tool_confirmation",
        tool_name=pending_confirmation.get("tool_name"),
    )

    # Build and send interrupt
    interrupt_payload = _build_tool_confirmation_payload(pending_confirmation, user_language)
    decision_data = interrupt(interrupt_payload)

    elapsed_time = time.time() - start_time
    logger.info(
        "hitl_dispatch_confirmation_decision_received",
        action=decision_data.get("action") if decision_data else None,
        latency_seconds=elapsed_time,
    )

    # Handle no decision
    if not decision_data:
        no_decision_result: dict[str, Any] = {
            STATE_KEY_TOOL_CONFIRMATION_RESULT: {
                "action": "cancel",
                "reason": "No decision received",
            },
            STATE_KEY_PENDING_TOOL_CONFIRMATION: None,
        }
        track_state_updates(state, no_decision_result, "hitl_dispatch")
        return no_decision_result

    # Process decision
    action, error = _process_tool_confirmation_decision(decision_data, pending_confirmation)

    result: dict[str, Any] = {STATE_KEY_PENDING_TOOL_CONFIRMATION: None}

    if action == "confirm":
        result[STATE_KEY_TOOL_CONFIRMATION_RESULT] = {
            "action": "confirm",
            "tool_name": pending_confirmation.get("tool_name"),
            "tool_args": pending_confirmation.get("tool_args"),
        }
    elif action == "cancel":
        result[STATE_KEY_TOOL_CONFIRMATION_RESULT] = {
            "action": "cancel",
            "reason": error or "User cancelled",
        }

    track_state_updates(state, result, "hitl_dispatch")
    return result


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "hitl_dispatch_node",
    # State keys
    "STATE_KEY_PENDING_DRAFT_CRITIQUE",
    "STATE_KEY_PENDING_DRAFTS_QUEUE",
    "STATE_KEY_DRAFT_ACTION_RESULT",
    "STATE_KEY_PENDING_ENTITY_DISAMBIGUATION",
    "STATE_KEY_ENTITY_DISAMBIGUATION_RESULT",
    "STATE_KEY_PENDING_DISAMBIGUATIONS_QUEUE",
    "STATE_KEY_PENDING_TOOL_CONFIRMATION",
    "STATE_KEY_TOOL_CONFIRMATION_RESULT",
]
