"""
Concrete HITL resumption strategy implementations.

Implements two strategies following the HitlResumptionStrategy Protocol:
1. ConversationalHitlResumption: Natural language approval (main user flow)
2. ButtonBasedHitlResumption: UI button approval (future enhancement)

Architecture pattern: Strategy pattern via Protocol
- Each strategy is independent and swappable
- Shared logic factored into private methods
- Type-safe via Protocol (PEP 544)

Example:
    >>> strategy = ConversationalHitlResumption(...)
    >>> async for chunk in strategy.resume_and_stream(...):
    ...     # Stream to frontend
"""

import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from src.core.field_names import (
    FIELD_CONTENT,
    FIELD_CONVERSATION_ID,
    FIELD_RUN_ID,
    FIELD_TURN_ID,
    FIELD_USER_ID,
)
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.domain_schemas import ToolApprovalDecision
from src.domains.agents.prompts import get_hitl_resumption_error_message
from src.domains.agents.services.hitl.validator import HitlValidator
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.chat.service import TrackingContext
from src.domains.conversations.service import ConversationService
from src.infrastructure.observability.callbacks import TokenTrackingCallback
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _build_plan_modifications_from_classifier(
    edited_params: dict[str, Any],
    pending_action_requests: list[dict],
    run_id: str,
) -> list[dict[str, Any]]:
    """
    Convert classifier's edited_params to PlanModification format.

    Issue #60 Fix: Bridge the gap between classifier output (edited_params)
    and approval_gate_node expectations (modifications).

    The classifier produces:
        {"count": 4, "max_results": 10}

    approval_gate_node expects:
        [{"modification_type": "edit_params", "step_id": "step_2", "new_parameters": {"count": 4}}]

    Strategy for step identification:
    1. Get plan_summary.steps from pending_action_requests
    2. For each edited param, find the step whose parameters contain that key
    3. Create a PlanModification for each matched step

    Args:
        edited_params: Parameters extracted by classifier (e.g., {"max_results": 4})
        pending_action_requests: Contains plan_summary with steps
        run_id: Run ID for logging

    Returns:
        List of PlanModification dicts ready for approval_gate_node
    """
    if not edited_params:
        return []

    modifications = []

    # Extract plan_summary from pending_action_requests
    plan_summary = None
    for action in pending_action_requests:
        if action.get("type") == "plan_approval":
            plan_summary = action.get("plan_summary", {})
            break

    if not plan_summary:
        logger.warning(
            "hitl_edit_no_plan_summary_found",
            run_id=run_id,
            edited_params=edited_params,
        )
        return []

    steps = plan_summary.get("steps", [])
    if not steps:
        logger.warning(
            "hitl_edit_no_steps_in_plan_summary",
            run_id=run_id,
            edited_params=edited_params,
        )
        return []

    # Match edited params to steps
    # Strategy: For each step, check if its parameters contain any edited param key
    params_to_match = set(edited_params.keys())
    matched_params: set[str] = set()

    # Debug: Log all steps and their parameters for troubleshooting
    logger.info(
        "hitl_edit_matching_debug",
        run_id=run_id,
        edited_params=edited_params,
        params_to_match=list(params_to_match),
        steps_count=len(steps),
        steps_details=[
            {
                "step_id": s.get("step_id"),
                "tool_name": s.get("tool_name"),
                "params_keys": list(s.get("parameters", {}).keys()),
            }
            for s in steps
        ],
    )

    for step in steps:
        step_id = step.get("step_id")
        step_params = step.get("parameters", {})

        # Find which edited params match this step's parameter keys
        matching_keys = params_to_match & set(step_params.keys())

        if matching_keys:
            # Create modification for this step with only matching params
            step_modifications = {k: edited_params[k] for k in matching_keys}

            modifications.append(
                {
                    "modification_type": "edit_params",
                    "step_id": step_id,
                    "new_parameters": step_modifications,
                }
            )

            matched_params.update(matching_keys)

            logger.info(
                "hitl_edit_matched_params_to_step",
                run_id=run_id,
                step_id=step_id,
                matched_keys=list(matching_keys),
                new_values=step_modifications,
            )

    # Handle unmatched params (params that don't match any step)
    unmatched_params = params_to_match - matched_params
    if unmatched_params:
        # Try to find a reasonable default step (first step with parameters)
        # This handles edge cases where param names differ slightly
        logger.warning(
            "hitl_edit_unmatched_params_attempting_fuzzy_match",
            run_id=run_id,
            unmatched_params=list(unmatched_params),
        )

        # Apply unmatched params to first step that has any parameters
        for step in steps:
            step_id = step.get("step_id")
            step_params = step.get("parameters", {})
            if step_params:
                unmatched_modifications = {k: edited_params[k] for k in unmatched_params}
                modifications.append(
                    {
                        "modification_type": "edit_params",
                        "step_id": step_id,
                        "new_parameters": unmatched_modifications,
                    }
                )
                logger.info(
                    "hitl_edit_unmatched_params_applied_to_first_step",
                    run_id=run_id,
                    step_id=step_id,
                    unmatched_modifications=unmatched_modifications,
                )
                break

    logger.info(
        "hitl_edit_modifications_built",
        run_id=run_id,
        total_modifications=len(modifications),
        edited_params_count=len(edited_params),
        matched_params_count=len(matched_params),
    )

    return modifications


def build_edit_reformulated_intent(modifications: list[dict[str, Any]]) -> str | None:
    """
    Build a reformulated user intent from EDIT modifications.

    When a user EDITs parameters via HITL (e.g., "recherche plutot jean" instead of "jean"),
    we need to update the HumanMessage to match the new parameters. Otherwise, the
    response_node sees the original message but agent_results from modified query,
    causing LLM confusion.

    This is a LangGraph v1.0.3+ best practice for HITL with Command(update={...}).

    Args:
        modifications: List of modification dicts from HITL classifier.
                      Format: [{"modification_type": "edit_params", "step_id": "...",
                               "new_parameters": {"query": "jean"}}]

    Returns:
        Reformulated intent string, or None if no reformulation needed.
        Examples:
        - "recherche jean" (contacts query)
        - "recherche emails factures" (emails search_query)
        - "envoie à jean@example.com" (email recipient)
        - "exécute avec: count=10, max_results=5" (generic fallback)

    Example:
        >>> mods = [{"modification_type": "edit_params", "new_parameters": {"query": "jean"}}]
        >>> build_edit_reformulated_intent(mods)
        'recherche jean'
    """
    for mod in modifications:
        if mod.get("modification_type") != "edit_params":
            continue

        new_params = mod.get("new_parameters", {})
        if not new_params:
            continue

        # Contacts domain: query parameter
        if "query" in new_params:
            return f"recherche {new_params['query']}"

        # Emails domain: search_query parameter
        if "search_query" in new_params:
            return f"recherche emails {new_params['search_query']}"

        # Emails domain: recipient parameter (for send)
        if "to" in new_params or "recipient" in new_params:
            recipient = new_params.get("to") or new_params.get("recipient")
            return f"envoie à {recipient}"

        # Calendar domain: event search
        if "event_query" in new_params:
            return f"recherche événements {new_params['event_query']}"

        # Generic fallback for other parameter types
        param_parts = []
        for k, v in new_params.items():
            if isinstance(v, str) and len(v) < 50:
                param_parts.append(f"{k}={v}")
            elif isinstance(v, int | float | bool):
                param_parts.append(f"{k}={v}")

        if param_parts:
            param_str = ", ".join(param_parts)
            return f"exécute avec: {param_str}"

        return "exécute avec les paramètres modifiés"

    return None


def _build_resume_value(
    approval_decision: ToolApprovalDecision,
    pending_action_requests: list[dict] | None,
    run_id: str,
) -> dict[str, Any]:
    """
    Build resume value dict from approval_decision and pending_action_requests.

    Session 24 - Phase A - Helper #15: Extracted from resume_and_stream().
    Issue #60 Fix: Added support for EDIT plan-level with edited_params conversion.

    Handles two HITL formats:
    - Plan-level: {"decision": "APPROVE"|"REJECT"|"EDIT", ...}
    - Tool-level: {"approved": bool, "edited_args": dict | None, "decisions": [...]}

    Args:
        approval_decision: User's approval decision from classifier
        pending_action_requests: Pending tool approval requests from interrupt
        run_id: Run ID for logging

    Returns:
        Dict with resume value formatted for Command(resume=...)

    Example:
        >>> # Plan-level HITL (approval_gate_node)
        >>> decision = ToolApprovalDecision(decisions=[{"type": "approve"}])
        >>> pending = [{"type": "plan_approval"}]
        >>> resume = _build_resume_value(decision, pending, "run_123")
        >>> # resume == {"decision": "APPROVE"}

        >>> # Tool-level HITL (plan_executor)
        >>> decision = ToolApprovalDecision(decisions=[{"type": "edit", "edited_action": {"args": {"query": "new"}}}])
        >>> pending = [{"type": "tool_approval"}]
        >>> resume = _build_resume_value(decision, pending, "run_456")
        >>> # resume == {"approved": True, "edited_args": {"query": "new"}, "decisions": [...]}
    """
    decisions = approval_decision.decisions

    # Detect HITL type from pending_action_requests
    # PHASE 8: Plan-level vs Tool-level vs Draft-level HITL format detection
    # - Tool-level: interrupt() in plan_executor.py expects {"approved": bool, "edited_args": dict | None}
    # - Plan-level: interrupt() in approval_gate_node.py expects {"decision": "APPROVE"|"REJECT"|"EDIT", ...}
    # - Draft-level (LOT 6): interrupt() in draft_critique_node expects {"action": "confirm"|"edit"|"cancel", ...}
    is_plan_approval = False
    is_draft_critique = False
    if pending_action_requests:
        first_action = pending_action_requests[0]
        action_type = first_action.get("type", "")
        is_plan_approval = action_type == "plan_approval"
        is_draft_critique = action_type == "draft_critique"

    logger.info(
        "hitl_resumption_format_detection",
        run_id=run_id,
        is_plan_approval=is_plan_approval,
        is_draft_critique=is_draft_critique,
        decision_count=len(decisions),
    )

    if is_draft_critique:
        # === DRAFT CRITIQUE HITL (LOT 6): Format for draft_critique_node ===
        # draft_critique_node expects: {"action": "confirm"|"edit"|"cancel", "draft_id": "...", "updated_content": {...} | None}
        # The decision comes pre-structured from frontend (no classification needed)
        first_decision = decisions[0] if decisions else {}

        # Extract action from decision - frontend sends as {"type": "confirm"} or as raw action
        draft_action = first_decision.get("type", first_decision.get("action", "cancel"))

        # Map decision types to draft actions
        action_mapping = {
            "approve": "confirm",
            "confirm": "confirm",
            "edit": "edit",
            "reject": "cancel",
            "cancel": "cancel",
        }
        draft_action = action_mapping.get(draft_action.lower(), "cancel")

        # Get draft_id from pending request (or from decision if available)
        draft_id = first_decision.get("draft_id")
        if not draft_id and pending_action_requests:
            draft_id = pending_action_requests[0].get("draft_id", "unknown")

        # Get updated_content for edit action
        updated_content = first_decision.get("updated_content") or first_decision.get(
            "edited_content"
        )

        resume_value = {
            "action": draft_action,
            "draft_id": draft_id,
            "updated_content": updated_content,
        }

        logger.info(
            "hitl_draft_critique_resume_value_built",
            run_id=run_id,
            action=draft_action,
            draft_id=draft_id,
            has_updated_content=updated_content is not None,
        )

    elif is_plan_approval:
        # === PLAN-LEVEL HITL: Format for approval_gate_node ===
        # Extract decision type from first decision
        first_decision = decisions[0] if decisions else {}
        decision_type = first_decision.get("type", "reject").upper()  # APPROVE, REJECT, EDIT

        # Build decision data matching approval_gate_node expectations
        resume_value = {"decision": decision_type}

        if decision_type == "REJECT":
            # Extract rejection reason from decision or use default
            resume_value["rejection_reason"] = first_decision.get(
                "rejection_reason", "User rejected plan"
            )
            logger.info(
                "hitl_plan_level_reject",
                run_id=run_id,
                reason=resume_value["rejection_reason"],
            )

        elif decision_type == "EDIT":
            # === Issue #60 Fix: Convert edited_params to modifications ===
            # Classifier produces edited_params, approval_gate expects modifications
            modifications = first_decision.get("modifications", [])

            if not modifications:
                # Issue #60 Fix (v2): Use edited_params directly if available
                # For plan-level HITL, edited_action.args may be empty because
                # the action is plan_approval (no tool_args), so we need the raw edited_params
                edited_params = first_decision.get("edited_params", {})

                # Fallback to edited_action.args for tool-level HITL compatibility
                if not edited_params:
                    edited_action = first_decision.get("edited_action", {})
                    edited_params = edited_action.get("args", {})

                if edited_params and pending_action_requests:
                    modifications = _build_plan_modifications_from_classifier(
                        edited_params=edited_params,
                        pending_action_requests=pending_action_requests,
                        run_id=run_id,
                    )
                    logger.info(
                        "hitl_plan_edit_converted_edited_params",
                        run_id=run_id,
                        edited_params=edited_params,
                        modifications_count=len(modifications),
                    )

            resume_value["modifications"] = modifications
            logger.info(
                "hitl_plan_level_edit",
                run_id=run_id,
                modifications_count=len(modifications),
            )

        elif decision_type == "APPROVE":
            logger.info(
                "hitl_plan_level_approve",
                run_id=run_id,
            )

    else:
        # === TOOL-LEVEL HITL: Format for plan_executor ===
        # Check if ANY decision is approve or edit (edit counts as approved with modifications)
        is_approved = any(d.get("type") in ("approve", "edit") for d in decisions)

        # Extract edited args from EDIT decisions (for plan_executor to apply)
        # Format: {"query": "jean"} extracted from {"type": "edit", "edited_action": {"name": "...", "args": {...}}}
        edited_args = None
        for decision in decisions:
            if decision.get("type") == "edit":
                edited_action = decision.get("edited_action", {})
                edited_args = edited_action.get("args")
                if edited_args:
                    logger.info(
                        "hitl_resumption_extracted_edited_args",
                        run_id=run_id,
                        edited_args=edited_args,
                    )
                break  # Only support single tool edit for now

        resume_value = {
            "approved": is_approved,
            "edited_args": edited_args,  # Pass edited args to interrupt() for application
            "decisions": decisions,  # Keep for potential future use
        }

    return resume_value


def _build_runnable_config(
    conversation_id: UUID,
    user_id: UUID,
    tracker: "TrackingContext",
    run_id: str,
    turn_id: int | None = None,
    tool_deps: Any = None,
) -> tuple["RunnableConfig", dict[str, Any]]:
    """
    Build RunnableConfig and context dict for graph execution.

    Session 24 - Phase C - Helper #1.

    Returns:
        Tuple of (runnable_config, context_dict)
    """
    from langchain_core.runnables import RunnableConfig

    # TokenTrackingCallback is imported at module level from
    # src.infrastructure.observability.callbacks
    token_callback = TokenTrackingCallback(tracker, run_id)

    configurable_dict = {
        "thread_id": str(conversation_id),
        FIELD_USER_ID: user_id,
    }

    if turn_id is not None:
        configurable_dict[FIELD_TURN_ID] = turn_id

    if tool_deps is not None:
        configurable_dict["__deps"] = tool_deps

    runnable_config = RunnableConfig(
        configurable=configurable_dict,
        callbacks=[token_callback],
    )

    context_dict = {
        FIELD_USER_ID: str(user_id),
        FIELD_CONVERSATION_ID: str(conversation_id),
        "thread_id": str(conversation_id),
    }

    return runnable_config, context_dict


async def _build_tool_level_command(
    resume_value: dict[str, Any],
    user_response: str | None,
    graph: "CompiledStateGraph",
    runnable_config: "RunnableConfig",
    conversation_id: UUID,
    run_id: str,
) -> "Command":
    """
    Build Command for tool-level HITL with appropriate message injection.

    Session 24 - Phase C - Helper #3: Extracted from _resume_with_tracker().

    Handles three decision types:
    - EDIT: Remove original user message, inject reformulated intent
    - REJECT: Inject enriched HumanMessage explaining user refusal
    - APPROVE: No message injection (avoid router re-processing)

    Args:
        resume_value: Tool-level resume value dict {"approved": bool, "decisions": [...]}
        user_response: User's natural language response (e.g., "non", "oui")
        graph: Compiled LangGraph StateGraph
        runnable_config: RunnableConfig with thread_id, callbacks
        conversation_id: Conversation UUID
        run_id: Unique run ID for logging

    Returns:
        Command object with resume value and optional message updates

    Raises:
        No exceptions raised - all errors handled internally with fallback logic
    """
    from langchain_core.messages import HumanMessage, RemoveMessage
    from langgraph.types import Command

    from src.domains.agents.constants import STATE_KEY_MESSAGES

    # Extract decision types for branching logic
    decision_types = [d.get("type") for d in resume_value["decisions"]]
    has_edit_decision = any(dt == "edit" for dt in decision_types)

    # Log decision analysis for debugging
    logger.info(
        "hitl_resumption_decision_analysis",
        run_id=run_id,
        decision_types=decision_types,
        has_edit_decision=has_edit_decision,
        user_response_present=user_response is not None,
        will_enter_edit_block=user_response and has_edit_decision,
    )

    # === EDIT: Remove original message and replace with reformulated intent ===
    if user_response and has_edit_decision:
        # Get edited params from first decision (POC: single tool)
        edited_action = resume_value["decisions"][0].get("edited_action", {})
        edited_args = edited_action.get("args", {})
        tool_name = edited_action.get("name", "unknown_tool")

        # Build reformulated user intent based on tool and edited params
        if tool_name == "get_contacts_tool" and "query" in edited_args:
            reformulated_intent = f"recherche {edited_args['query']}"
        else:
            # Generic fallback
            reformulated_intent = f"exécute {tool_name} avec les paramètres modifiés"

        # Load state snapshot to get last HumanMessage ID
        try:
            snapshot = await graph.aget_state(runnable_config, subgraphs=False)
            messages = snapshot.values.get(STATE_KEY_MESSAGES, [])

            # Find the last HumanMessage ID (search from end)
            last_human_msg_id = None
            for msg in reversed(messages):
                if hasattr(msg, "type") and msg.type == "human":
                    if hasattr(msg, "id") and msg.id:
                        last_human_msg_id = msg.id
                        break

            # Build message updates: [RemoveMessage(...), HumanMessage(...)]
            from langchain_core.messages import BaseMessage

            messages_to_update: list[BaseMessage] = []

            if last_human_msg_id:
                messages_to_update.append(RemoveMessage(id=last_human_msg_id))
                logger.info(
                    "hitl_edit_removing_original_message",
                    run_id=run_id,
                    message_id=last_human_msg_id,
                    reason="Replacing to avoid LLM confusion",
                )
            else:
                logger.warning(
                    "hitl_edit_no_message_id_found",
                    run_id=run_id,
                    messages_count=len(messages),
                    note="Cannot remove, will add reformulated only",
                )

            # Add reformulated intent
            messages_to_update.append(HumanMessage(content=reformulated_intent))

            # Build Command with message updates
            command_input = Command(
                resume=resume_value, update={STATE_KEY_MESSAGES: messages_to_update}
            )

            logger.info(
                "hitl_resumption_reformulating_for_edit",
                run_id=run_id,
                original_user_response=user_response,
                reformulated_intent=reformulated_intent,
                tool_name=tool_name,
                edited_params=edited_args,
                original_removed=last_human_msg_id is not None,
            )

        except Exception as e:
            # Fallback: If state loading fails, proceed without removal
            logger.error(
                "hitl_edit_state_load_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                fallback="Adding reformulated message without removal",
            )

            command_input = Command(
                resume=resume_value,
                update={STATE_KEY_MESSAGES: [HumanMessage(content=reformulated_intent)]},
            )

            logger.info(
                "hitl_resumption_reformulating_for_edit_fallback",
                run_id=run_id,
                original_user_response=user_response,
                reformulated_intent=reformulated_intent,
                tool_name=tool_name,
                edited_params=edited_args,
            )

        return command_input

    # === REJECT or APPROVE with user_response ===
    elif user_response:
        has_reject_decision = any(dt == "reject" for dt in decision_types)

        if has_reject_decision:
            # REJECT: Inject enriched HumanMessage
            try:
                # Extract tool_call_id from Redis mapping
                import json

                from src.infrastructure.cache.redis import get_redis_cache

                tool_call_id = None
                redis = await get_redis_cache()
                mapping_json = await redis.get(f"hitl_tool_call_mapping:{conversation_id}")

                if mapping_json:
                    tool_call_mapping = json.loads(mapping_json)
                    tool_call_id = tool_call_mapping.get("0") or tool_call_mapping.get(0)

                logger.info(
                    "hitl_reject_tool_call_id_extraction",
                    run_id=run_id,
                    tool_call_id=tool_call_id,
                    found=tool_call_id is not None,
                    mapping_found=mapping_json is not None,
                )

                if tool_call_id:
                    # Inject enriched HumanMessage explaining user refusal
                    enriched_user_message = (
                        f"[REFUS UTILISATEUR]\n"
                        f"L'utilisateur a explicitement refusé l'action proposée en disant : '{user_response}'\n\n"
                        f"IMPORTANT: Ceci est un REFUS UTILISATEUR, PAS une erreur technique.\n"
                        f"Réponse attendue:\n"
                        f"- Accuse réception de manière concise (ex: 'Pas de problème')\n"
                        f"- Demande ce qu'il souhaite faire à la place\n"
                        f"- NE mentionne AUCUN problème technique, erreur système, ou indisponibilité de service"
                    )

                    command_input = Command(
                        resume=resume_value,
                        update={STATE_KEY_MESSAGES: [HumanMessage(content=enriched_user_message)]},
                    )

                    logger.info(
                        "hitl_resumption_injecting_enriched_human_message",
                        run_id=run_id,
                        tool_call_id=tool_call_id,
                        enriched_message=enriched_user_message[:150],
                        original_response=user_response,
                    )
                else:
                    # Fallback: No tool_call_id found
                    logger.warning(
                        "hitl_resumption_reject_no_tool_call_id",
                        run_id=run_id,
                        note="Cannot inject ToolMessage, falling back to HumanMessage only",
                    )

                    command_input = Command(
                        resume=resume_value,
                        update={STATE_KEY_MESSAGES: [HumanMessage(content=user_response)]},
                    )

            except Exception as e:
                # Fallback on error
                logger.error(
                    "hitl_resumption_reject_state_load_failed",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    fallback="Using HumanMessage only",
                )

                command_input = Command(
                    resume=resume_value,
                    update={STATE_KEY_MESSAGES: [HumanMessage(content=user_response)]},
                )
        else:
            # APPROVE: Do NOT inject HumanMessage (avoid router re-processing)
            command_input = Command(resume=resume_value)

            logger.debug(
                "hitl_resumption_approve_without_message_injection",
                run_id=run_id,
                user_response_preview=(
                    user_response[:100] if len(user_response) > 100 else user_response
                ),
                decision_types=decision_types,
                reason="Avoid router re-processing",
            )

        return command_input

    # === No user_response provided ===
    else:
        return Command(resume=resume_value)


class ConversationalHitlResumption:
    """
    Conversational HITL resumption strategy.

    Resumes graph execution after natural language approval (e.g., "oui", "non").
    Used for regular users in production flow.

    This strategy:
    - Extracts decisions from ToolApprovalDecision
    - Builds Command(resume={"decisions": [...]})
    - Streams graph execution with token tracking
    - Archives messages and updates conversation stats
    - Yields "done" chunk with token metrics

    Dependencies:
        - ConversationService: For message archival and stats
        - TrackingContext: For token tracking (optional, can be provided externally)
        - TokenTrackingCallback: For Prometheus metrics

    Example:
        >>> strategy = ConversationalHitlResumption(conversation_service)
        >>> async for chunk in strategy.resume_and_stream(
        ...     graph=graph,
        ...     approval_decision=decision,
        ...     conversation_id=conv_id,
        ...     user_id=user_id,
        ...     run_id=run_id,
        ...     tracker=unified_tracker,  # Optional: for aggregating tokens
        ... ):
        ...     yield chunk  # SSE stream to frontend
    """

    def __init__(self, conversation_service: ConversationService) -> None:
        """
        Initialize conversational HITL strategy.

        Args:
            conversation_service: Service for message archival and stats.
        """
        self.conversation_service = conversation_service

    async def resume_and_stream(
        self,
        graph: CompiledStateGraph,
        approval_decision: ToolApprovalDecision,
        conversation_id: UUID,
        user_id: UUID,
        run_id: str,
        config: RunnableConfig | None = None,
        context: dict[str, Any] | None = None,
        tracker: "TrackingContext | None" = None,
        user_response: str | None = None,
        turn_id: int | None = None,
        pending_action_requests: list[dict] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Resume graph after conversational approval and stream results.

        This is the main entry point for natural language HITL resumption.
        It follows the exact same pattern as button-based resumption, ensuring
        identical behavior for tool execution and token tracking.

        Flow:
            1. Build resume value from approval_decision.decisions
            2. Use provided tracker OR create new TrackingContext for token tracking
            3. Build RunnableConfig with callbacks
            4. Stream graph.astream(Command(resume=...), config)
            5. Archive response messages to database
            6. Update conversation stats (message_count, total_tokens)
            7. Yield "done" chunk with token metrics

        Args:
            graph: Compiled LangGraph StateGraph to resume.
            approval_decision: User's approval decision (from classifier).
            conversation_id: Conversation UUID (thread_id).
            user_id: User UUID.
            run_id: Unique run ID for this execution.
            config: Optional RunnableConfig (unused, built internally).
            context: Optional context dict (unused, built internally).
            tracker: Optional TrackingContext (for unified tracking with classification).
                    If None, creates a new tracker (backward compatibility).
            user_response: User's natural language response to HITL prompt.
            turn_id: Conversation turn ID for tracking.
            pending_action_requests: Pending tool approval requests from interrupt.
            **kwargs: Additional strategy-specific parameters.
                - tool_deps: Optional ToolDependencies for dependency injection.

        Yields:
            ChatStreamChunk: Stream chunks (tokens, metadata, done/error).

        Raises:
            Exception: If graph execution fails or resumption fails.
        """
        logger.info(
            "hitl_conversational_resumption_started",
            conversation_id=str(conversation_id),
            user_id=str(user_id),
            run_id=run_id,
            decision_count=len(approval_decision.decisions),
            using_unified_tracker=tracker is not None,
        )

        start_time = time.time()

        # Step 1: Build resume value from approval_decision
        # Session 24 - Phase A: Extracted to _build_resume_value() helper (Helper #15)
        resume_value = _build_resume_value(
            approval_decision=approval_decision,
            pending_action_requests=pending_action_requests,
            run_id=run_id,
        )

        # Extract tool_deps from kwargs if provided (for dependency injection)
        tool_deps = kwargs.get("tool_deps")

        # Step 2: Use provided tracker OR create new TrackingContext
        # When tracker is provided (unified tracking), auto_commit=False to prevent double commit
        # The parent context (handle_hitl_response) will commit all aggregated tokens
        if tracker is not None:
            # Unified tracking mode: use provided tracker (no auto-commit)
            async for chunk in self._resume_with_tracker(
                graph,
                resume_value,
                conversation_id,
                user_id,
                run_id,
                tracker,
                start_time,
                user_response,
                turn_id,
                pending_action_requests,
                tool_deps,
            ):
                yield chunk
        else:
            # Backward compatibility mode: create new tracker with auto-commit
            async with TrackingContext(
                run_id, user_id, "hitl_approval", conversation_id
            ) as new_tracker:
                async for chunk in self._resume_with_tracker(
                    graph,
                    resume_value,
                    conversation_id,
                    user_id,
                    run_id,
                    new_tracker,
                    start_time,
                    user_response,
                    turn_id,
                    pending_action_requests,
                    tool_deps,
                ):
                    yield chunk

    async def _resume_with_tracker(
        self,
        graph: CompiledStateGraph,
        resume_value: dict,
        conversation_id: UUID,
        user_id: UUID,
        run_id: str,
        tracker: "TrackingContext",
        start_time: float,
        user_response: str | None = None,
        turn_id: int | None = None,
        pending_action_requests: list[dict] | None = None,
        tool_deps: Any = None,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Internal method to resume graph with a given tracker.

        This method contains the actual resumption logic, extracted to avoid
        code duplication between unified tracking and backward compatibility modes.

        Args:
            graph: Compiled LangGraph StateGraph to resume.
            resume_value: Command resume value with tool approval decisions.
            conversation_id: Conversation UUID (thread_id).
            user_id: User UUID.
            run_id: Unique run ID for this execution.
            tracker: TrackingContext for token tracking.
            start_time: Start timestamp for duration metrics.
            user_response: User's natural language response to HITL prompt.
            turn_id: Conversation turn ID for tracking.
            pending_action_requests: Pending tool approval requests from interrupt.
            tool_deps: Optional ToolDependencies for dependency injection into tools.
                If provided, will reuse the DB session from tool_deps for message archival.
        """
        from src.infrastructure.observability.metrics_agents import (
            hitl_resumption_duration_seconds,
            hitl_resumption_total,
        )

        # Step 3: Build RunnableConfig with callbacks
        # Session 24 - Phase C: Extracted to _build_runnable_config() (Helper #1)
        runnable_config, context_dict = _build_runnable_config(
            conversation_id=conversation_id,
            user_id=user_id,
            tracker=tracker,
            run_id=run_id,
            turn_id=turn_id,
            tool_deps=tool_deps,
        )

        # Step 4: Stream graph execution
        # Use Command(resume=...) to resume from interrupt point
        # IMPORTANT: Conditional message handling based on decision type
        # - APPROVE/REJECT: Inject user_response as HumanMessage ("oui", "non")
        # - EDIT: Replace last user message with reformulated intent + add system note
        #   This preserves conversation structure and avoids LLM confusion
        # Stream both "values" (final state) and "messages" (tokens)

        # PHASE 8: Plan-level HITL handling
        # - Plan-level: approval_gate_node handles decision directly via resume_value
        # - CRITICAL FIX: For EDIT decisions, we MUST update the user message
        #   to reflect the modified parameters. Otherwise, response_node sees the
        #   original message (e.g., "recherche jean") but agent_results contain
        #   data from modified query (e.g., "jean"), causing LLM confusion.
        is_plan_level = "decision" in resume_value  # Plan-level has "decision" key
        # LOT 6 FIX: Draft critique has "action" + "draft_id" keys (not "decision" or "decisions")
        is_draft_critique = "action" in resume_value and "draft_id" in resume_value

        # Debug log to trace HITL resumption path
        logger.info(
            "hitl_resumption_format_detection",
            run_id=run_id,
            is_plan_level=is_plan_level,
            is_draft_critique=is_draft_critique,
            resume_value_keys=list(resume_value.keys()) if resume_value else [],
            has_decision="decision" in resume_value if resume_value else False,
            decision_value=resume_value.get("decision") if resume_value else None,
            draft_action=resume_value.get("action") if is_draft_critique else None,
        )

        if is_draft_critique:
            # LOT 6 FIX: Draft critique HITL - Simple Command(resume=resume_value)
            # The draft_critique_node expects resume_value = {"action": "confirm"|"edit"|"cancel", "draft_id": ..., "updated_content": ...}
            # No message manipulation needed - just pass through to interrupt()
            from langgraph.types import Command

            command_input = Command(resume=resume_value)

            logger.info(
                "hitl_resumption_draft_critique",
                run_id=run_id,
                action=resume_value.get("action"),
                draft_id=resume_value.get("draft_id"),
            )
        elif is_plan_level:
            from langchain_core.messages import HumanMessage, RemoveMessage
            from langgraph.types import Command

            from src.domains.agents.constants import STATE_KEY_MESSAGES

            decision_type = resume_value.get("decision", "").upper()

            if decision_type == "EDIT" and resume_value.get("modifications"):
                # === CRITICAL FIX: Plan-level EDIT needs message reformulation ===
                # Extract edited parameters to build reformulated intent
                modifications = resume_value.get("modifications", [])

                # Build reformulated intent using centralized helper
                reformulated_intent = build_edit_reformulated_intent(modifications)

                if reformulated_intent:
                    # Load state snapshot to get last HumanMessage ID
                    try:
                        snapshot = await graph.aget_state(runnable_config, subgraphs=False)
                        messages = snapshot.values.get(STATE_KEY_MESSAGES, [])

                        # Find the last HumanMessage ID (search from end)
                        last_human_msg_id = None
                        original_content = None
                        for msg in reversed(messages):
                            if hasattr(msg, "type") and msg.type == "human":
                                if hasattr(msg, "id") and msg.id:
                                    last_human_msg_id = msg.id
                                    original_content = (
                                        msg.content if hasattr(msg, "content") else None
                                    )
                                    break

                        # Build message updates: [RemoveMessage(...), HumanMessage(...)]
                        from langchain_core.messages import BaseMessage

                        messages_to_update: list[BaseMessage] = []

                        if last_human_msg_id:
                            messages_to_update.append(RemoveMessage(id=last_human_msg_id))
                            logger.info(
                                "hitl_plan_edit_removing_original_message",
                                run_id=run_id,
                                message_id=last_human_msg_id,
                                original_content=(
                                    original_content[:50] if original_content else None
                                ),
                                reason="Replacing to avoid LLM confusion between original query and modified results",
                            )

                        # Add reformulated intent
                        messages_to_update.append(HumanMessage(content=reformulated_intent))

                        # Build Command with message updates AND resume value
                        command_input = Command(
                            resume=resume_value,
                            update={STATE_KEY_MESSAGES: messages_to_update},
                        )

                        logger.info(
                            "hitl_plan_level_edit_with_message_reformulation",
                            run_id=run_id,
                            decision=decision_type,
                            original_message=original_content[:50] if original_content else None,
                            reformulated_intent=reformulated_intent,
                            modifications_count=len(modifications),
                        )

                    except Exception as e:
                        # Fallback: If state loading fails, proceed without message update
                        logger.error(
                            "hitl_plan_edit_state_load_failed",
                            run_id=run_id,
                            error=str(e),
                            error_type=type(e).__name__,
                            fallback="Proceeding without message reformulation",
                        )
                        command_input = Command(resume=resume_value)
                else:
                    # No query parameter found in modifications - proceed without reformulation
                    command_input = Command(resume=resume_value)
                    logger.info(
                        "hitl_plan_level_edit_no_reformulation_needed",
                        run_id=run_id,
                        decision=decision_type,
                        modifications=modifications,
                    )
            else:
                # APPROVE or REJECT: No message injection needed
                command_input = Command(resume=resume_value)

                logger.info(
                    "hitl_resumption_plan_level_standard",
                    run_id=run_id,
                    decision=decision_type,
                )
        else:
            # Tool-level HITL: Build command with message handling
            # Session 24 - Phase C: Extracted to _build_tool_level_command() (Helper #3)
            command_input = await _build_tool_level_command(
                resume_value=resume_value,
                user_response=user_response,
                graph=graph,
                runnable_config=runnable_config,
                conversation_id=conversation_id,
                run_id=run_id,
            )

        assistant_response_content = ""
        first_values_logged = False

        try:
            async for mode, chunk in graph.astream(
                command_input,
                runnable_config,
                stream_mode=["values", "messages"],
                context=context_dict,  # type: ignore[arg-type]
            ):
                # Debug: Log first "values" chunk to verify message injection
                if mode == "values" and not first_values_logged and isinstance(chunk, dict):
                    messages_preview = [
                        f"{type(m).__name__}:{m.content[:50] if hasattr(m, 'content') and isinstance(m.content, str) else str(m)[:50]}"
                        for m in chunk.get("messages", [])
                    ]
                    logger.debug(
                        "hitl_resumption_state_loaded",
                        run_id=run_id,
                        message_count=len(chunk.get("messages", [])),
                        messages_preview=messages_preview,
                        has_user_response_in_command=bool(user_response),
                    )
                    first_values_logged = True

                # === NESTED HITL: Detect interrupt during resume ===
                # If the resumed tool triggers another HITL-requiring tool, we must:
                # 1. Detect the new __interrupt__
                # 2. Store it in Redis (new pending_hitl)
                # 3. Yield hitl_interrupt chunk to frontend
                # 4. Return (pause graph again)
                if mode == "values" and isinstance(chunk, dict) and "__interrupt__" in chunk:
                    interrupt_tuple = chunk["__interrupt__"]

                    if interrupt_tuple and len(interrupt_tuple) > 0:
                        interrupt_obj = interrupt_tuple[0]
                        interrupt_data = interrupt_obj.value

                        if not isinstance(interrupt_data, dict):
                            logger.error(
                                "nested_interrupt_invalid_format",
                                run_id=run_id,
                                conversation_id=str(conversation_id),
                                data_type=type(interrupt_data).__name__,
                            )
                            continue

                        action_requests = interrupt_data.get("action_requests", [])
                        review_configs = interrupt_data.get("review_configs")

                        logger.warning(
                            "nested_interrupt_detected",
                            run_id=run_id,
                            conversation_id=str(conversation_id),
                            action_requests_count=len(action_requests),
                        )

                        if not action_requests:
                            logger.error(
                                "nested_interrupt_missing_actions",
                                run_id=run_id,
                                conversation_id=str(conversation_id),
                            )
                            continue

                        # Store NEW pending_hitl in Redis

                        from src.core.config import settings
                        from src.domains.agents.utils import HITLStore
                        from src.infrastructure.cache.redis import get_redis_cache

                        try:
                            redis = await get_redis_cache()

                            # Use HITLStore for consistent schema and key format
                            hitl_store = HITLStore(
                                redis_client=redis,
                                ttl_seconds=settings.hitl_pending_data_ttl_seconds,
                            )

                            interrupt_data = {
                                "action_requests": action_requests,
                                "review_configs": review_configs,
                                "count": len(action_requests),
                                FIELD_RUN_ID: run_id,
                            }

                            # Save using HITLStore (uses hitl_pending:{thread_id} key format)
                            await hitl_store.save_interrupt(
                                thread_id=str(conversation_id),
                                interrupt_data=interrupt_data,
                            )

                            logger.info(
                                "nested_interrupt_stored_redis",
                                conversation_id=str(conversation_id),
                                run_id=run_id,
                            )
                        except Exception as redis_error:
                            logger.error(
                                "nested_interrupt_redis_failed",
                                run_id=run_id,
                                error=str(redis_error),
                            )
                            yield ChatStreamChunk(
                                type="error",
                                content="Impossible de sauvegarder l'interruption imbriquée. Veuillez réessayer.",
                            )
                            return

                        # Generate HITL question for nested interrupt
                        from src.domains.agents.services.hitl.question_generator import (
                            HitlQuestionGenerator,
                        )

                        # Create generator instance for this nested interrupt
                        question_generator = HitlQuestionGenerator()

                        # Generate question for first action (POC: single action)
                        first_action = action_requests[0]

                        # PHASE 3.2.7: Use centralized validator for tool extraction
                        validator = HitlValidator()
                        try:
                            tool_name = validator.extract_tool_name(first_action)
                        except ValueError:
                            tool_name = "unknown"

                        tool_args = validator.extract_tool_args(first_action)

                        # Extract TokenTrackingCallback for token tracking if available
                        question_tracker = None
                        if tracker:
                            question_tracker = TokenTrackingCallback(tracker, run_id)

                        hitl_question = await question_generator.generate_confirmation_question(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            user_language="fr",  # TODO: Extract from state when available
                            user_timezone="Europe/Paris",  # TODO: Extract from state when available
                            tracker=question_tracker,  # ✅ Pass tracker for token tracking
                        )

                        # Yield hitl_interrupt chunk
                        yield ChatStreamChunk(
                            type="hitl_interrupt",
                            content=hitl_question,
                            metadata={
                                "action_requests": action_requests,
                                "review_configs": review_configs,
                                "count": len(action_requests),
                                "nested": True,  # Flag as nested interrupt
                            },
                        )

                        logger.info(
                            "nested_interrupt_yielded",
                            conversation_id=str(conversation_id),
                            run_id=run_id,
                            question=hitl_question[:100],
                        )

                        # Return immediately - graph is paused again
                        return

                # Mode "messages": Individual message updates (streaming tokens)
                if mode == "messages":
                    # chunk is (message, metadata) tuple
                    if isinstance(chunk, tuple) and len(chunk) == 2:
                        first_item, second_item = chunk

                        # Determine which is the message: AIMessageChunk has .content
                        # Tuple structure from LangGraph: (message_object, metadata_dict)
                        if hasattr(first_item, "content") or (
                            isinstance(first_item, dict) and FIELD_CONTENT in first_item
                        ):
                            message = first_item
                        else:
                            message = second_item

                        # Extract content from message (handle both dict and object)
                        content = None
                        if isinstance(message, dict):
                            content = message.get(FIELD_CONTENT)
                        elif hasattr(message, "content"):
                            content = message.content

                        # Filter: Only stream AIMessageChunk (streaming tokens from response_node)
                        # Skip: HumanMessage, ToolMessage, complete AIMessage
                        message_type_name = type(message).__name__
                        is_streamable = message_type_name == "AIMessageChunk"

                        # Stream only AIMessageChunk content
                        if content and isinstance(content, str) and is_streamable:
                            assistant_response_content += content
                            yield ChatStreamChunk(type="token", content=content)

        except Exception as e:
            # Record resumption error metric
            hitl_resumption_total.labels(strategy="conversational", status="error").inc()

            # PHASE 3.3.2: Track SSE error metric for consistency
            from src.infrastructure.observability.metrics_agents import sse_streaming_errors_total

            sse_streaming_errors_total.labels(
                error_type=type(e).__name__,
                node_name="hitl_resumption",
            ).inc()

            logger.error(
                "hitl_conversational_resumption_error",
                conversation_id=str(conversation_id),
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            yield ChatStreamChunk(type="error", content=get_hitl_resumption_error_message(e))

            # PHASE 3.3.2: Always yield done chunk after error (PHASE 3.1.4 - DTO refactored)
            zero_summary = TokenSummaryDTO.zero()
            yield ChatStreamChunk(
                type="done",
                content="",
                metadata={
                    "error": True,
                    **zero_summary.to_metadata(),  # Clean DTO-based construction
                },
            )
            return

        # Step 5 & 6: Archive response and update stats (PHASE 3.1.4 - DTO refactored)
        summary_dto = tracker.get_summary_dto()
        duration = time.time() - start_time
        total_tokens = summary_dto.tokens_in + summary_dto.tokens_out

        if assistant_response_content.strip():
            from sqlalchemy import select

            from src.domains.chat.models import MessageTokenSummary
            from src.infrastructure.database import get_db_context

            # Reuse DB session from tool_deps if available, otherwise create new one
            if tool_deps is not None:
                db = tool_deps.db
                # Note: We're using the provided session from tool_deps

                # Archive assistant response
                await self.conversation_service.archive_message(
                    conversation_id,
                    "assistant",
                    assistant_response_content,
                    {FIELD_RUN_ID: run_id, "hitl_approved": True},
                    db,
                )

                # Update conversation stats
                await self.conversation_service.increment_conversation_stats(
                    conversation_id, total_tokens, db
                )

                # Link token summary to conversation
                result = await db.execute(
                    select(MessageTokenSummary).where(MessageTokenSummary.run_id == run_id)
                )
                summary_record = result.scalar_one_or_none()
                if summary_record:
                    summary_record.conversation_id = conversation_id

                # Commit all changes
                await db.commit()
            else:
                # Backward compatibility: create new session
                async with get_db_context() as db:
                    # Archive assistant response
                    await self.conversation_service.archive_message(
                        conversation_id,
                        "assistant",
                        assistant_response_content,
                        {FIELD_RUN_ID: run_id, "hitl_approved": True},
                        db,
                    )

                    # Update conversation stats
                    await self.conversation_service.increment_conversation_stats(
                        conversation_id, total_tokens, db
                    )

                    # Link token summary to conversation
                    result = await db.execute(
                        select(MessageTokenSummary).where(MessageTokenSummary.run_id == run_id)
                    )
                    summary_record = result.scalar_one_or_none()
                    if summary_record:
                        summary_record.conversation_id = conversation_id

                    # Commit all changes
                    await db.commit()

        # Step 7: Yield "done" chunk with token metrics
        # Record successful resumption metrics
        hitl_resumption_total.labels(strategy="conversational", status="success").inc()
        hitl_resumption_duration_seconds.labels(strategy="conversational").observe(duration)

        logger.info(
            "hitl_conversational_resumption_completed",
            conversation_id=str(conversation_id),
            run_id=run_id,
            tokens_in=summary_dto.tokens_in,
            tokens_out=summary_dto.tokens_out,
            tokens_cache=summary_dto.tokens_cache,
            cost_eur=summary_dto.cost_eur,
            duration_seconds=round(duration, 2),
        )

        yield ChatStreamChunk(
            type="done",
            content="",  # Required field per schema
            metadata={
                **summary_dto.to_metadata(),  # Clean DTO-based construction
                "duration_seconds": round(duration, 2),
                FIELD_RUN_ID: run_id,
                "resumption_strategy": "conversational",
            },
        )
