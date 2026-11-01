"""What the response reads once the turn's drafts were decided (spec 2026-10-29 D7).

Two cases, never both:

- the decision came back to the PLAN (``plan_resume``): steps waited for it,
  work ran beside the acts (``told``), or a step of the plan asked it — every
  tool call, and every question a resumed step asked. The orchestrator
  executed the decided drafts (``executed_drafts``) and ran what waited. Those
  drafts are never executed again — the resume cleared the decision, and the
  ledger would only serve a record anyway (probe Hb, 2026-10-29). The answer is
  then WRITTEN: the
  model reads each executed act's plain account (it must never author card
  markup; the performed-actions directive of ADR-263 §23 states the same acts as
  its own) COMPOSED with the results the resume reported — replacing the summary,
  as below, would drop the very step the person waited for, or the archiving they
  asked for beside a refused deletion (« OK, c'est annulé », measured
  2026-10-30). A confirmed tool call's step is reported too (``acted``, owner
  rule 2026-10-31): its account says it ran, its step says what it returned — a
  dedicated agent's task, a read asked under « always ask ». A decision no step
  of the plan asked (a draft without a step) is executed here and joins the
  accounts;
- otherwise the turn did nothing but the decided acts and what they read: the
  drafts are executed now and their card REPLACES the summary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from src.domains.agents.drafts.card_html import card_surface
from src.domains.agents.drafts.executed import executed_entries
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.drafts.result_renderer import render_execution_result
from src.domains.agents.nodes.draft_sequence import (
    STATE_KEY_DRAFT_ACTION_RESULT,
    STATE_KEY_EXECUTED_DRAFTS,
    STATE_KEY_HELD_PLAN,
)


def decision_answered_by_its_card(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """The decision the response answers with its card alone — None when it WRITES.

    After a resume the answer is written: the resumed steps' results need words,
    and a later round's decision joins the accounts the model reads.
    """
    if state.get(STATE_KEY_EXECUTED_DRAFTS):
        return None
    decision: dict[str, Any] | None = state.get(STATE_KEY_DRAFT_ACTION_RESULT)
    return decision


async def summary_with_drafts(
    state: Mapping[str, Any],
    summary: str,
    execute: Callable[[], Awaitable[dict[str, Any] | None]],
) -> tuple[str, dict[str, Any] | None]:
    """The results summary after the drafts, and the record the turn is judged on.

    Args:
        state: The graph state.
        summary: The results summary built so far.
        execute: Executes the decision still pending, if any (None when none is).

    Returns:
        The summary to answer from, and the record the turn is judged on (None
        when no draft was decided).
    """
    executed = list((state.get(STATE_KEY_EXECUTED_DRAFTS) or {}).values())
    record = await execute()
    if not executed:
        if record:
            card = render_execution_result(record, surface=card_surface())
            if card:
                summary = card.strip()
        return summary, record
    records = [*executed, *([record] if record else [])]
    accounts = [render_execution_result(entry) for entry in records]
    # The summary holds the steps the resume reported — those it ran, the work
    # done beside the acts (``told``) and what the confirmed tool calls returned
    # (``acted``); with none of them, only stale results.
    held_plan = state.get(STATE_KEY_HELD_PLAN) or {}
    reported = bool(held_plan.get("resumed") or held_plan.get("told") or held_plan.get("acted"))
    parts = [account for account in accounts if account] + (
        [summary] if reported and summary else []
    )
    return "\n\n".join(parts), _judged(records)


def _judged(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The record the turn is judged on: one decision, or every round's acts as one batch.

    A round whose approved act FAILED must weigh on the turn like the last one.
    """
    if len(records) == 1:
        return records[0]
    entries = [entry for record in records for entry in executed_entries(record)]
    return {"action": DraftAction.CONFIRM_BATCH.value, "data": {"batch_results": entries}}
