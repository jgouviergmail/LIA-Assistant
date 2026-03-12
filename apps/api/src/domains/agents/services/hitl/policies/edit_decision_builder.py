"""
Edit Decision Builder Policy.

This policy builds edit decisions with parameter merging, validation, and metrics tracking.

Architecture:
- Builds structured edit decisions from classification results
- Merges edited parameters into tool arguments
- Infers edit type (params_modified, tool_changed, full_rewrite, minor_adjustment)
- Tracks parameter-level edit metrics
- Validates edited_params presence
"""

from typing import TYPE_CHECKING, Any

from structlog import get_logger

from src.core.field_names import FIELD_TOOL_NAME

if TYPE_CHECKING:
    from src.domains.agents.services.hitl.validator import HitlValidator

logger = get_logger(__name__)


class EditDecisionBuilder:
    """
    Policy class for building edit decisions.

    Handles edit decision construction with parameter merging,
    edit type inference, and metrics tracking.
    """

    def __init__(self, agent_type: str = "generic"):
        """
        Initialize edit builder.

        Args:
            agent_type: Agent type label for metrics (e.g., "contacts_agent")
        """
        self.agent_type = agent_type

    def build(
        self,
        action: dict[str, Any],
        edited_params: dict[str, Any],
        classification: Any,
        clarification_question: str | None,
        validator: "HitlValidator",
    ) -> dict[str, Any]:
        """
        Build edit decision with parameter merging, validation, and metrics tracking.

        Args:
            action: Tool action to edit
            edited_params: Parameters to merge into tool args
            classification: ClassificationResult or dict (for error logging)
            clarification_question: Clarification question if present
            validator: HitlValidator instance for tool extraction

        Returns:
            Decision dict with type="edit" and edited_action

        Raises:
            ValueError: If edited_params is None/empty

        Example:
            >>> builder = EditDecisionBuilder(agent_type="contacts_agent")
            >>> decision = builder.build(
            ...     action={"name": "search_contacts", "args": {"name": "John"}},
            ...     edited_params={"name": "Jane"},
            ...     classification=classification_result,
            ...     clarification_question=None,
            ...     validator=validator,
            ... )
            >>> decision["type"]  # "edit"
            >>> decision["edited_action"]["args"]["name"]  # "Jane"
        """
        from src.infrastructure.observability.metrics_agents import (
            hitl_edit_actions_total,
            hitl_edit_decisions_total,
        )

        # Extract tool name and args
        try:
            tool_name = validator.extract_tool_name(action)
        except ValueError:
            tool_name = "unknown"
        tool_args = action.get("args", action.get("tool_args", {}))

        # Validation: edited_params required for EDIT
        if not edited_params:
            logger.error(
                "hitl_edit_missing_params",
                classification=(
                    classification.model_dump()
                    if hasattr(classification, "model_dump")
                    else str(classification)
                ),
                action=action,
                has_clarification=bool(clarification_question),
            )
            raise ValueError(
                "EDIT decision requires edited_params. "
                "Classification should be AMBIGUOUS if params cannot be extracted."
            )

        # Merge edited params into tool args
        merged_args = {**tool_args, **edited_params}

        # Track metrics
        tool_name_str = str(tool_name) if tool_name else "unknown"
        edit_type = self.infer_edit_type(
            tool_args=tool_args,
            edited_params=edited_params,
            tool_name=tool_name_str,
        )

        hitl_edit_actions_total.labels(edit_type=edit_type, agent_type=self.agent_type).inc()

        logger.info(
            "hitl_edit_decision_built",
            tool_name=tool_name,
            edit_type=edit_type,
            original_args=tool_args,
            edited_params=edited_params,
            merged_args=merged_args,
        )

        # Track parameter-level edits
        for param_name in edited_params.keys():
            hitl_edit_decisions_total.labels(
                tool_name=tool_name or "unknown",
                param_modified=param_name,
            ).inc()

        return {
            "type": "edit",
            "edited_action": {"name": tool_name, "args": merged_args},
            # Issue #60 Fix: Include original edited_params for plan-level HITL
            # _build_plan_modifications_from_classifier needs the raw edited_params
            # because for plan_approval, tool_args is empty and merged_args = edited_params
            "edited_params": edited_params,
        }

    @staticmethod
    def infer_edit_type(tool_args: dict, edited_params: dict, tool_name: str) -> str:
        """
        Infer the type of EDIT action based on edited parameters.

        Categorizes edits into:
        - params_modified: User modified existing parameter values
        - tool_changed: Tool name was changed (rare)
        - full_rewrite: User rewrote all parameters
        - minor_adjustment: User tweaked 1-2 parameters

        Args:
            tool_args: Original tool arguments
            edited_params: Parameters edited by user
            tool_name: Tool name

        Returns:
            Edit type string for metrics labeling

        Example:
            >>> EditDecisionBuilder.infer_edit_type({"name": "John"}, {"name": "Jane"}, "search")
            'minor_adjustment'
            >>> EditDecisionBuilder.infer_edit_type({"name": "John"}, {"name": "Jane", "city": "Paris", "age": 30}, "search")
            'full_rewrite'
        """
        # Tool changed (rare case)
        if FIELD_TOOL_NAME in edited_params and edited_params[FIELD_TOOL_NAME] != tool_name:
            return "tool_changed"

        edited_count = len(edited_params)
        original_count = len(tool_args)

        # Full rewrite: More than 50% of params changed or 4+ params changed
        if edited_count > max(original_count * 0.5, 3):
            return "full_rewrite"

        # Minor adjustment: 1-2 params changed
        if edited_count <= 2:
            return "minor_adjustment"

        # Default: Multiple params modified (3-4 params)
        return "params_modified"


__all__ = [
    "EditDecisionBuilder",
]
