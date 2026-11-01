"""The person's decision on a draft, executed once (Data Registry LOT 5.4, spec 2026-10-29 D7).

Two readers, one door. The response node executes the decision when nothing
waited on it; the plan's resume (``plan_resume``) executes it before the steps
that waited run. Both degrade the same way: a failure becomes an error record the
answer states — never a crashed turn, never the exception's text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.core.i18n import _, resolve_language
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.draft_sequence import STATE_KEY_DRAFT_ACTION_RESULT

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

logger = structlog.get_logger(__name__)


async def execute_decided_draft(
    state: MessagesState,
    config: RunnableConfig,
    run_id: str,
) -> dict[str, Any] | None:
    """Execute the person's decision on the turn's drafts, once.

    Data Registry LOT 5.4: after the confirmation sequence settled, this
    delegates to the draft_executor service.

    Args:
        state: Current graph state with draft_action_result
        config: Runnable config (thread plumbing) and metadata; dependencies come from the run context
        run_id: Run ID for logging

    Returns:
        Agent result dict for draft execution (or None if no draft to execute)

    Note:
        - Uses lazy imports to avoid circular dependencies
        - Graceful degradation: an execution failure is an error record the
          answer states, never a crashed node
        - Uses central draft_executor service with registry pattern
    """
    draft_action_result = state.get(STATE_KEY_DRAFT_ACTION_RESULT)

    if not draft_action_result:
        return None

    # Extract user_language from state for localized messages
    user_language = resolve_language(state.get("user_language"))

    try:
        # Lazy import to avoid circular dependencies
        from src.domains.agents.services.draft_executor import (
            execute_draft_if_confirmed,
        )

        # Delegate to central executor service
        # Handles confirm/edit/cancel routing and metrics
        result = await execute_draft_if_confirmed(
            draft_action_result, config, run_id, user_language
        )

        if result:
            logger.info(
                "draft_execution_completed",
                run_id=run_id,
                draft_id=result.draft_id,
                success=result.success,
                action=result.action,
            )
            return result.to_agent_result()

        return None

    except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
        logger.error(
            "draft_execution_failed",
            run_id=run_id,
            draft_id=draft_action_result.get("draft_id"),
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        # Return error result for response synthesis (graceful degradation)
        # Never expose raw exception details — they could leak to the user via LLM synthesis
        return {
            "status": "error",
            "message": _("The action could not be completed. Please try again."),
            "draft_id": draft_action_result.get("draft_id"),
            "draft_type": draft_action_result.get("draft_type"),
            "action": DraftAction.CONFIRM.value,
        }
