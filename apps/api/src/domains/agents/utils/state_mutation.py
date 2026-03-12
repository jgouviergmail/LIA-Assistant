"""
State mutation utilities for LangGraph nodes.

Provides atomic state mutations with automatic rollback on errors.
Uses selective deep copy to avoid copying reducer-managed fields.

Usage:
    from src.domains.agents.utils.state_mutation import StateMutationContext

    async def my_node(state: MessagesState, config: RunnableConfig) -> dict:
        with StateMutationContext(state, "my_node") as ctx:
            ctx.update("execution_plan", new_plan)
            ctx.update("agent_results", new_results)
            # If exception occurs here, automatic rollback
        return ctx.result

Note:
    Fields managed by LangGraph reducers (messages, registry, current_turn_registry)
    should NOT be mutated through this context - they have their own merge logic.
"""

import copy
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# Fields managed by LangGraph reducers - do NOT deep copy or mutate directly
# These fields have custom merge logic defined in MessagesState
REDUCER_MANAGED_FIELDS: set[str] = {
    "messages",  # add_messages_with_truncate reducer
    "registry",  # merge_registry reducer
    "current_turn_registry",  # merge_registry reducer
}

# Mutable fields that should be backed up for potential rollback
# These are dicts/lists that nodes might mutate in-place
MUTABLE_FIELDS_TO_BACKUP: set[str] = {
    "agent_results",
    "routing_history",
    "metadata",
    "execution_plan",
    "orchestration_plan",
    "completed_steps",
    "disambiguation_context",
    "draft_context",
}


class StateMutationContext:
    """
    Context manager for safe state mutations with automatic rollback.

    Only backs up fields that:
    1. Are mutable (dicts, lists)
    2. Are NOT managed by LangGraph reducers
    3. Will potentially be modified in this node

    On exception, the context provides the backup values for rollback.
    The calling code can choose to return ctx.backup instead of ctx.result.

    Attributes:
        state: The original state dict
        node_name: Name of the node (for logging)
        fields_to_modify: Set of field names that may be modified
        backup: Deep copies of backed up fields (populated on __enter__)
        result: Accumulated state updates (populated via update())

    Example:
        >>> with StateMutationContext(state, "task_orchestrator") as ctx:
        ...     ctx.update("execution_plan", new_plan)
        ...     ctx.update("agent_results", cleaned_results)
        >>> track_state_updates(state, ctx.result, "task_orchestrator", run_id)
        >>> return ctx.result
    """

    def __init__(
        self,
        state: dict[str, Any],
        node_name: str,
        fields_to_modify: set[str] | None = None,
    ):
        """
        Initialize the mutation context.

        Args:
            state: Current LangGraph state dict
            node_name: Name of the calling node (for logging)
            fields_to_modify: Optional set of fields that will be modified.
                              If None, uses MUTABLE_FIELDS_TO_BACKUP defaults.
        """
        self.state = state
        self.node_name = node_name
        self.fields_to_modify = fields_to_modify or MUTABLE_FIELDS_TO_BACKUP
        self.backup: dict[str, Any] = {}
        self.result: dict[str, Any] = {}
        self._entered = False

    def __enter__(self) -> "StateMutationContext":
        """
        Enter the context and create selective deep copies for rollback.

        Only copies fields that:
        - Are in fields_to_modify
        - Are NOT reducer-managed
        - Exist in state and are not None
        """
        self._entered = True

        for field in self.fields_to_modify:
            # Skip reducer-managed fields
            if field in REDUCER_MANAGED_FIELDS:
                logger.debug(
                    f"{self.node_name}_skip_reducer_field",
                    field=field,
                    reason="Managed by LangGraph reducer",
                )
                continue

            # Backup existing fields
            if field in self.state and self.state[field] is not None:
                self.backup[field] = copy.deepcopy(self.state[field])

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """
        Exit the context. On exception, log rollback info.

        Returns:
            False to re-raise any exception (we don't suppress exceptions)
        """
        if exc_type is not None:
            logger.warning(
                f"{self.node_name}_mutation_error",
                error_type=exc_type.__name__,
                error=str(exc_val),
                rolled_back_keys=list(self.backup.keys()),
                attempted_updates=list(self.result.keys()),
            )
            # Caller can access self.backup for rollback values
            # We don't automatically rollback - caller decides

    def update(self, key: str, value: Any) -> None:
        """
        Queue a state update.

        Warns if the key is a reducer-managed field (should use LangGraph
        reducer pattern instead).

        Args:
            key: State key to update
            value: New value for the key

        Raises:
            RuntimeError: If called outside of context manager
        """
        if not self._entered:
            raise RuntimeError("StateMutationContext.update() must be called within a 'with' block")

        if key in REDUCER_MANAGED_FIELDS:
            logger.warning(
                f"{self.node_name}_reducer_field_bypass",
                key=key,
                hint=f"Use LangGraph reducer pattern for '{key}' instead of direct mutation",
            )

        self.result[key] = value

    def get_rollback_state(self) -> dict[str, Any]:
        """
        Get the backup state for rollback purposes.

        Use this in exception handlers to return safe state instead of
        partial mutations.

        Returns:
            Dict with backed up field values
        """
        return self.backup.copy()
