"""
HITL resumption helpers shared by the production resume path.

The production HITL resume flow lives in
``orchestration/service.py::_build_hitl_resume_command`` (Command construction)
and ``streaming/service.py::stream_sse_chunks`` (SSE emission, all four stream
modes, nested-interrupt handling). This module provides the helpers that flow
consumes:

- ``_build_plan_modifications_from_classifier``: classifier ``edited_params``
  → per-step modification dicts (Issue #60 bridge, used by approval_decision).
- ``build_edit_reformulated_intent``: localized reformulated intent injected
  into state on EDIT resumes.
- ``resolve_user_language``: reads the user's language from the checkpointed
  graph state so reformulations match the original turn's language.

History (ADR-222): this module previously also shipped a
``ConversationalHitlResumption`` strategy class (own ``graph.astream`` loop
limited to ``["values", "messages"]``, own tracker/archival flow) behind a
``HitlResumptionStrategy`` Protocol. That parallel implementation was never
wired to any production caller — the API layer streams resumes through
``StreamingService`` (which was purpose-built for it, including
``is_hitl_resumption`` labelling) — and its reduced stream-mode subscription
would have dropped compaction/update events had it ever been wired. Deleted
2026-08-16 with its Protocol and tests; the three helpers above are the only
production consumers' surface.
"""

from typing import Any

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from src.core.i18n import DEFAULT_LANGUAGE
from src.core.i18n_hitl import HitlMessages, ReformulationKind
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _build_plan_modifications_from_classifier(
    edited_params: dict[str, Any],
    pending_action_requests: list[dict],
    run_id: str,
) -> list[dict[str, Any]]:
    """
    Convert classifier's edited_params to per-step modification dicts.

    Issue #60 Fix: Bridge the gap between classifier output (edited_params)
    and the modification format consumed by the HITL resumption flow.

    The classifier produces:
        {"count": 4, "max_results": 10}

    The resumption flow expects:
        [{"modification_type": "edit_params", "step_id": "step_2", "new_parameters": {"count": 4}}]

    Strategy for step identification:
    1. Get plan_summary.steps from pending_action_requests
    2. For each edited param, find the step whose parameters contain that key
    3. Create a modification dict for each matched step

    Args:
        edited_params: Parameters extracted by classifier (e.g., {"max_results": 4})
        pending_action_requests: Contains plan_summary with steps
        run_id: Run ID for logging

    Returns:
        List of modification dicts consumed by the HITL resumption flow
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


def build_edit_reformulated_intent(
    modifications: list[dict[str, Any]], user_language: str = DEFAULT_LANGUAGE
) -> str | None:
    """
    Build a reformulated user intent from EDIT modifications, localized.

    When a user EDITs parameters via HITL (e.g., "recherche plutot jean" instead of "jean"),
    we need to update the HumanMessage to match the new parameters. Otherwise, the
    response_node sees the original message but agent_results from modified query,
    causing LLM confusion.

    The reformulated intent replaces the user's message in the conversation, so it
    is localized to ``user_language`` (via ``HitlMessages.get_reformulation``) — a
    hardcoded phrase would leak a foreign language into the transcript.

    This is a LangGraph v1.0.3+ best practice for HITL with Command(update={...}).

    Args:
        modifications: List of modification dicts from HITL classifier.
                      Format: [{"modification_type": "edit_params", "step_id": "...",
                               "new_parameters": {"query": "jean"}}]
        user_language: User language code (any spelling; normalized internally).

    Returns:
        Reformulated intent string in ``user_language``, or None if no
        reformulation needed. Examples (en): "search jean", "send to
        jean@example.com", "execute with: count=10, max_results=5".

    Example:
        >>> mods = [{"modification_type": "edit_params", "new_parameters": {"query": "jean"}}]
        >>> build_edit_reformulated_intent(mods, "en")
        'search jean'
    """
    for mod in modifications:
        if mod.get("modification_type") != "edit_params":
            continue

        new_params = mod.get("new_parameters", {})
        if not new_params:
            continue

        # Contacts domain: query parameter
        if "query" in new_params:
            return HitlMessages.get_reformulation(
                ReformulationKind.SEARCH_QUERY, user_language, value=new_params["query"]
            )

        # Emails domain: search_query parameter
        if "search_query" in new_params:
            return HitlMessages.get_reformulation(
                ReformulationKind.SEARCH_EMAILS, user_language, value=new_params["search_query"]
            )

        # Emails domain: recipient parameter (for send)
        if "to" in new_params or "recipient" in new_params:
            recipient = new_params.get("to") or new_params.get("recipient")
            return HitlMessages.get_reformulation(
                ReformulationKind.SEND_TO, user_language, value=recipient
            )

        # Calendar domain: event search
        if "event_query" in new_params:
            return HitlMessages.get_reformulation(
                ReformulationKind.SEARCH_EVENTS, user_language, value=new_params["event_query"]
            )

        # Generic fallback for other parameter types
        param_parts = []
        for k, v in new_params.items():
            if isinstance(v, str) and len(v) < 50:
                param_parts.append(f"{k}={v}")
            elif isinstance(v, int | float | bool):
                param_parts.append(f"{k}={v}")

        if param_parts:
            param_str = ", ".join(param_parts)
            return HitlMessages.get_reformulation(
                ReformulationKind.EXECUTE_PARAMS, user_language, value=param_str
            )

        return HitlMessages.get_reformulation(ReformulationKind.EXECUTE_MODIFIED, user_language)

    return None


async def resolve_user_language(
    graph: "CompiledStateGraph", runnable_config: "RunnableConfig"
) -> str:
    """Read the user's language from the checkpointed graph state.

    Reformulations injected on resume must match the user's language, which was
    written to the graph state during the original turn. Falls back to the
    configured default language if the state cannot be read.

    Args:
        graph: The compiled graph to read the checkpointed state from.
        runnable_config: RunnableConfig identifying the thread/checkpoint.

    Returns:
        The user's language code (raw; callers normalize as needed).
    """
    try:
        snapshot = await graph.aget_state(runnable_config, subgraphs=False)
        return snapshot.values.get("user_language") or DEFAULT_LANGUAGE
    except Exception as exc:
        logger.warning(
            "resolve_user_language_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            fallback=DEFAULT_LANGUAGE,
        )
        return DEFAULT_LANGUAGE
