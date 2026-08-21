"""Planner HUMAN-message builder (extracted from smart_planner_service).

Pure functions — no dependency on ``SmartPlannerService``. They live in their
own module (file-size ratchet) and are imported by the service's two planning
methods and by the single/multi-domain strategies (the runtime path).

The human message is where the planner's load-bearing facts belong: models
weight the human turn far more than the system context (prod 2026-07-17 — the
enriched query, buried in the system context, was ignored and defaults were
substituted). Both resolved facts and, on a replan, the previous plan ride
here.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan


def format_existing_plan_for_replan(existing_plan: ExecutionPlan) -> str:
    """One line per step (id + tool + JSON params) of a plan being replanned.

    Tolerates the dict-serialized plan form defensively (getattr/dict fallback),
    though on the validation-replan path the plan is the live in-memory object.
    Returns "" when the plan carries no steps.
    """
    steps = getattr(existing_plan, "steps", None)
    if steps is None and isinstance(existing_plan, dict):
        steps = existing_plan.get("steps")
    if not steps:
        return ""
    lines: list[str] = []
    for step in steps:
        tool = getattr(step, "tool_name", None) or (
            step.get("tool_name") if isinstance(step, dict) else ""
        )
        params = getattr(step, "parameters", None)
        if params is None and isinstance(step, dict):
            params = step.get("parameters")
        step_id = getattr(step, "step_id", None) or (
            step.get("step_id") if isinstance(step, dict) else ""
        )
        try:
            params_str = json.dumps(params or {}, ensure_ascii=False, sort_keys=True)
        except TypeError, ValueError:
            params_str = str(params)
        lines.append(f"- {step_id} {tool} {params_str}")
    return "PREVIOUS PLAN:\n" + "\n".join(lines)


def build_planner_human_message(
    intelligence: QueryIntelligence,
    *,
    existing_plan: ExecutionPlan | None = None,
    validation_feedback: str | None = None,
) -> str:
    """Human message for the planner LLM: original query + resolved facts.

    The enriched query used to live only in the middle of the system context,
    where the planner (observed twice in prod on deepseek-v4-flash, with and
    without an added FACT RULE) ignored it and substituted defaults — a
    next-hour slot and a generic title — for facts it had been given. Facts
    belong in the human message, the position models weight most. The language
    constraint stays attached (FIX 2026-03-23: free-text content such as
    titles/bodies is written in the user's language, never translated).

    On a validation replan (``existing_plan`` + ``validation_feedback`` present,
    passed ONLY when there is no user clarification), the previous plan is
    appended with a fix-don't-rebuild directive — also in the high-attention
    human message — so the planner converges instead of oscillating.
    """
    content = f"Query: {intelligence.original_query}"
    if intelligence.english_enriched_query:
        content += (
            "\nResolved facts (authoritative for tool parameters — dates, times, "
            "people, places; NEVER substitute a default like the current time or a "
            "generic title for a value stated here; write free-text values such as "
            "titles/bodies in the user's language): "
            f"{intelligence.english_enriched_query}"
        )
    if existing_plan is not None and validation_feedback:
        previous = format_existing_plan_for_replan(existing_plan)
        if previous:
            content += (
                "\n\nThis is a REPLAN of your PREVIOUS plan (below). Apply ONLY the "
                "corrections named in the validation feedback — add or remove a step if "
                "it asks — and keep every other parameter value byte-for-byte identical. "
                f"Do NOT rebuild from scratch.\n{previous}"
            )
    return content
