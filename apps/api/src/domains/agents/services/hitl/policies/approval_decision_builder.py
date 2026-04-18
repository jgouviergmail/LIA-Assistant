"""
Approval Decision Builder Policy.

This policy orchestrates decision building for HITL approval flows.

Architecture:
- Composes ClassificationExtractor, RejectionDecisionBuilder, EditDecisionBuilder
- Builds ToolApprovalDecision from classification or draft actions
- Handles all decision types: APPROVE, REJECT, EDIT
- LOT 6: Supports structured draft actions (bypass LLM classification)
"""

from typing import Any

from structlog import get_logger

from src.domains.agents.constants import (
    HITL_DECISION_APPROVE,
    HITL_DECISION_EDIT,
    HITL_DECISION_REJECT,
    HITL_DECISION_REPLAN,
)
from src.domains.agents.domain_schemas import ToolApprovalDecision
from src.domains.agents.services.hitl.policies.classification_extractor import (
    ClassificationExtractor,
)
from src.domains.agents.services.hitl.policies.edit_decision_builder import (
    EditDecisionBuilder,
)
from src.domains.agents.services.hitl.policies.rejection_decision_builder import (
    RejectionDecisionBuilder,
)
from src.domains.agents.services.hitl.validator import HitlValidator

logger = get_logger(__name__)


class ApprovalDecisionBuilder:
    """
    Policy class for orchestrating approval decision building.

    Composes:
    - ClassificationExtractor: Extract classification data
    - RejectionDecisionBuilder: Build rejection decisions
    - EditDecisionBuilder: Build edit decisions

    Handles:
    - Draft action decisions (LOT 6 - structured JSON bypass)
    - Classification-based decisions (LLM natural language)
    """

    def __init__(self, agent_type: str = "generic"):
        """
        Initialize approval decision builder with composed builders.

        Args:
            agent_type: Agent type label for metrics (e.g., "contacts_agent")
        """
        self.agent_type = agent_type
        self.extractor = ClassificationExtractor()
        self.rejection_builder = RejectionDecisionBuilder(agent_type=agent_type)
        self.edit_builder = EditDecisionBuilder(agent_type=agent_type)

    def build_from_draft_action(
        self,
        draft_action_json: dict[str, Any],
        action_requests: list[dict],
    ) -> ToolApprovalDecision:
        """
        Build ToolApprovalDecision from structured draft action JSON.

        LOT 6: Draft Critique HITL - Bypasses LLM classification for structured actions.

        The frontend sends draft actions as structured JSON:
            {
                "type": "draft_action",
                "draft_id": "draft_abc123",
                "action": "confirm" | "edit" | "cancel",
                "updated_content": {...} | null
            }

        Args:
            draft_action_json: Parsed JSON from frontend with action details.
            action_requests: List of action_requests from interrupt (contains draft_critique).

        Returns:
            ToolApprovalDecision with single decision matching the draft action.

        Example:
            >>> builder = ApprovalDecisionBuilder(agent_type="email_agent")
            >>> json_action = {"type": "draft_action", "action": "confirm", "draft_id": "d123"}
            >>> decision = builder.build_from_draft_action(json_action, pending)
            >>> decision.decisions  # [{"type": "confirm", "draft_id": "d123"}]
        """
        action = draft_action_json.get("action", "cancel")
        draft_id = draft_action_json.get("draft_id", "unknown")
        updated_content = draft_action_json.get("updated_content")

        # Map draft actions to ToolApprovalDecision types
        # Draft actions: confirm, edit, cancel
        # ToolApprovalDecision types: approve, edit, reject
        action_mapping = {
            "confirm": "approve",
            "edit": "edit",
            "cancel": "reject",
        }
        decision_type = action_mapping.get(action, "reject")

        # Build decision based on action type
        decision: dict[str, Any] = {
            "type": decision_type,  # approve, edit, or reject
            "draft_id": draft_id,
            "original_action": action,  # Keep original action for downstream processing
        }

        if action == "edit":
            # For edit actions, ToolApprovalDecision validator requires 'edited_action'
            # Create a minimal edited_action structure for draft edits
            decision["edited_action"] = {
                "name": "draft_edit",  # Placeholder name for draft edits
                "args": updated_content or {},
            }
            if updated_content:
                decision["updated_content"] = updated_content
                decision["edited_content"] = updated_content  # Alias for compatibility

        logger.info(
            "hitl_draft_action_decision_built",
            action=action,
            draft_id=draft_id,
            has_updated_content=updated_content is not None,
        )

        return ToolApprovalDecision(
            decisions=[decision],
            action_indices=[0],  # Single action
            rejection_messages=None,
        )

    def build_from_classification(
        self,
        classification: Any,  # ClassificationResult or dict
        action_requests: list[dict],
        user_response: str = "",
        user_language: str = "en",
    ) -> ToolApprovalDecision:
        """
        Build ToolApprovalDecision from ClassificationResult.

        Converts natural language classification (APPROVE/REJECT/EDIT/AMBIGUOUS)
        into structured ToolApprovalDecision format expected by HumanInTheLoopMiddleware.

        Uses composed builders:
        1. ClassificationExtractor: Extract classification fields
        2. RejectionDecisionBuilder: Build rejection decisions with i18n
        3. EditDecisionBuilder: Build edit decisions with parameter merging

        Args:
            classification: ClassificationResult from HitlResponseClassifier (or dict for compatibility).
            action_requests: List of action_requests from interrupt.
            user_response: User's original natural language response (for rejection type inference).
            user_language: User's language code for i18n messages (e.g., "fr", "en"). Default: "en".

        Returns:
            ToolApprovalDecision with decisions list and action_indices.

        Note:
            - APPROVE: Execute tool as-is
            - REJECT: Skip tool execution, add rejection message
            - EDIT: Execute tool with modified arguments

        Example:
            >>> builder = ApprovalDecisionBuilder(agent_type="contacts_agent")
            >>> decision = builder.build_from_classification(
            ...     classification=classification_result,
            ...     action_requests=action_requests,
            ...     user_response="non annule ça",
            ...     user_language="fr"
            ... )
            >>> decision.decisions[0]["type"]  # "reject"
        """
        # Extract classification data (uses ClassificationExtractor)
        decision, reasoning, edited_params, clarification_question = self.extractor.extract(
            classification
        )

        decisions: list[dict[str, Any]] = []
        action_indices = list(range(len(action_requests)))
        validator = HitlValidator()

        for action in action_requests:
            if decision == HITL_DECISION_APPROVE:
                decisions.append({"type": "approve"})
            elif decision == HITL_DECISION_REJECT:
                # Build rejection decision (uses RejectionDecisionBuilder)
                decision_dict = self.rejection_builder.build(
                    action=action,
                    reasoning=reasoning,
                    user_response=user_response,
                    classification=classification,
                    validator=validator,
                    user_language=user_language,
                )
                decisions.append(decision_dict)
            elif decision == HITL_DECISION_REPLAN:
                # REPLAN = user wants a different action type (e.g., delete → update)
                # Pass modification_instructions through for hitl_dispatch_node
                replan_instructions = ""
                if edited_params and "modification_instructions" in edited_params:
                    replan_instructions = edited_params["modification_instructions"]
                decisions.append(
                    {
                        "type": "replan",
                        "modification_instructions": replan_instructions,
                    }
                )
            elif decision == HITL_DECISION_EDIT:
                # Ensure edited_params is not None
                if edited_params is None:
                    logger.error(
                        "hitl_edit_missing_params_in_classification",
                        classification=(
                            classification.model_dump()
                            if hasattr(classification, "model_dump")
                            else str(classification)
                        ),
                        action=action,
                    )
                    raise ValueError(
                        "EDIT decision requires edited_params. "
                        "Classification should be AMBIGUOUS if params cannot be extracted."
                    )
                # Build edit decision (uses EditDecisionBuilder)
                decision_dict = self.edit_builder.build(
                    action=action,
                    edited_params=edited_params,
                    classification=classification,
                    clarification_question=clarification_question,
                    validator=validator,
                )
                decisions.append(decision_dict)

        return ToolApprovalDecision(
            decisions=decisions,
            action_indices=action_indices,
            rejection_messages=None,  # Rejection messages handled in decisions
        )


__all__ = [
    "ApprovalDecisionBuilder",
]
