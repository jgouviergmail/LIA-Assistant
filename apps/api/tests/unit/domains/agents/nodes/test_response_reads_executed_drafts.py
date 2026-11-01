"""After a resume, the response executes nothing again and COMPOSES (spec D7).

The orchestrator executed the confirmed drafts and ran the steps that waited
for them. The response then reads those records: it never executes a draft a
second time (the ledger would only serve a record anyway — probe Hb), and the
model reads the executed acts' plain accounts WITH the results of the resumed
steps. Without a resume, the historical behaviour stands: the card REPLACES the
summary.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.agents.drafts.card_html import card_surface
from src.domains.agents.drafts.result_renderer import render_execution_result
from src.domains.agents.nodes.draft_results_summary import summary_with_drafts

pytestmark = [pytest.mark.unit]

_BLANK_LINE = "\n\n"


def _executed(draft_id: str, status: str = "success") -> dict[str, Any]:
    return {
        "status": status,
        "data": {"_draft_content": {"tool_name": "notes_delete", "tool_args": {}}},
        "message": f"Done: {draft_id}",
        "draft_id": draft_id,
        "draft_type": "tool_call",
        "action": "confirm",
    }


class TestAfterAResume:
    """The answer is WRITTEN after a resume: the model reads the acts as facts.

    The model never receives a result card — it must not author card markup —
    but each executed act's plain account; the performed-actions directive
    (ADR-263 §23) states the same acts as its own.
    """

    async def test_response_executes_nothing_twice(self) -> None:
        """The resume cleared the decision: nothing is left for the response to run."""
        execute = AsyncMock(return_value=None)
        state = {
            "executed_drafts": {"d1": _executed("d1")},
            "held_plan": {"resumed": ["s2"], "held": {}, "not_run": {}},
        }

        summary, judged = await summary_with_drafts(state, "Sent the e-mail.", execute)

        assert summary == _BLANK_LINE.join(
            [render_execution_result(_executed("d1")), "Sent the e-mail."]
        )
        assert judged == _executed("d1"), "the business metrics judge the executed draft"

    async def test_response_composes_executed_drafts_with_resumed_results(self) -> None:
        state = {
            "executed_drafts": {"d1": _executed("d1"), "d2": _executed("d2")},
            "held_plan": {"resumed": ["s2"], "held": {}, "not_run": {}},
        }

        summary, _judged = await summary_with_drafts(
            state, "[s2] e-mail sent with link https://x", AsyncMock(return_value=None)
        )

        accounts = [render_execution_result(_executed(d)) for d in ("d1", "d2")]
        assert summary == _BLANK_LINE.join([*accounts, "[s2] e-mail sent with link https://x"])
        assert "lia-card" not in summary, "no card markup reaches the model"

    async def test_a_decision_after_a_resume_is_executed_and_composed(self) -> None:
        """A later round asked again with nothing waiting: the response runs THAT decision."""
        execute = AsyncMock(return_value=_executed("d2"))
        state = {
            "executed_drafts": {"d1": _executed("d1")},
            "held_plan": {"resumed": ["s2"], "held": {}, "not_run": {}},
        }

        summary, judged = await summary_with_drafts(state, "[s2] archived", execute)

        execute.assert_awaited_once()
        assert summary == _BLANK_LINE.join(
            [
                render_execution_result(_executed("d1")),
                render_execution_result(_executed("d2")),
                "[s2] archived",
            ]
        )
        assert judged == {
            "action": "confirm_batch",
            "data": {"batch_results": [_executed("d1"), _executed("d2")]},
        }, "the turn is judged on every round's acts"

    async def test_every_round_is_judged_not_only_the_last(self) -> None:
        """An act approved then FAILED in an earlier round still weighs on the turn."""
        from src.domains.agents.services.business_metrics import (
            OUTCOME_PARTIAL_SUCCESS,
            infer_conversation_outcome,
        )

        state = {
            "executed_drafts": {"d1": _executed("d1", "error")},
            "held_plan": {"resumed": [], "held": {}, "not_run": {"s2": "failed"}},
        }

        _summary, judged = await summary_with_drafts(
            state, "", AsyncMock(return_value=_executed("d2"))
        )

        assert infer_conversation_outcome({}, judged) == OUTCOME_PARTIAL_SUCCESS  # type: ignore[typeddict-item]

    async def test_nothing_resumed_keeps_the_accounts_alone(self) -> None:
        """Every waiting step was left unrun: the summary holds no stale result."""
        state = {
            "executed_drafts": {"d1": _executed("d1", "cancelled")},
            "held_plan": {"resumed": [], "held": {}, "not_run": {"s2": "refused"}},
        }

        summary, _judged = await summary_with_drafts(
            state, "[search] 3 notes", AsyncMock(return_value=None)
        )

        assert summary == render_execution_result(_executed("d1", "cancelled"))

    async def test_work_told_beside_the_act_joins_the_accounts(self) -> None:
        """Spec D5 (2026-10-30): what ran beside the decided act reaches the answer."""
        state = {
            "executed_drafts": {"d1": _executed("d1", "cancelled")},
            "held_plan": {"resumed": [], "told": ["s1"], "held": {}, "not_run": {}},
        }

        summary, _judged = await summary_with_drafts(
            state, "[s1] note n3 archived", AsyncMock(return_value=None)
        )

        assert summary == _BLANK_LINE.join(
            [render_execution_result(_executed("d1", "cancelled")), "[s1] note n3 archived"]
        )

    async def test_what_a_confirmed_tool_call_returned_joins_its_account(self) -> None:
        """Owner rule (2026-10-31): the act's account names it, its step says what it returned."""
        state = {
            "executed_drafts": {"d1": _executed("d1")},
            "held_plan": {"resumed": [], "told": [], "acted": ["s1"], "held": {}, "not_run": {}},
        }

        summary, _judged = await summary_with_drafts(
            state, "Your notes: n1 Groceries, n3 Holidays", AsyncMock(return_value=None)
        )

        assert summary == _BLANK_LINE.join(
            [render_execution_result(_executed("d1")), "Your notes: n1 Groceries, n3 Holidays"]
        )


class TestWithoutAResume:
    async def test_the_card_replaces_the_summary_as_before(self) -> None:
        execute = AsyncMock(return_value=_executed("d1"))

        summary, judged = await summary_with_drafts({}, "[search] 3 notes", execute)

        execute.assert_awaited_once()
        assert summary == render_execution_result(_executed("d1"), surface=card_surface())
        assert judged == _executed("d1")

    async def test_no_decision_leaves_the_summary_untouched(self) -> None:
        summary, judged = await summary_with_drafts(
            {}, "[search] 3 notes", AsyncMock(return_value=None)
        )

        assert (summary, judged) == ("[search] 3 notes", None)


class TestWhatWasNotRunIsSaid:
    async def test_a_step_left_unrun_reaches_the_honesty_block(self) -> None:
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )
        from src.domains.agents.services.runtime_failure_directive import held_not_run_block

        plan = ExecutionPlan(
            plan_id="p",
            user_id="u",
            session_id="s",
            steps=[
                ExecutionStep(
                    step_id="s2",
                    step_type=StepType.TOOL,
                    agent_name="a",
                    tool_name="send_email_tool",
                    parameters={},
                ),
                ExecutionStep(
                    step_id="s4",
                    step_type=StepType.TOOL,
                    agent_name="a",
                    tool_name="create_event_tool",
                    parameters={},
                ),
            ],
        )
        block = held_not_run_block(
            {"execution_plan": plan, "held_plan": {"not_run": {"s2": "refused", "s4": "failed"}}}
        )

        assert "send_email_tool" in block and "refused" in block
        assert "create_event_tool" in block and "failed" in block
        assert held_not_run_block({"held_plan": {"not_run": {}}}) == ""
        assert held_not_run_block({}) == ""


class TestTheMetricsImportFirst:
    def test_the_business_metrics_import_first_without_a_cycle(self) -> None:
        """Imported FIRST they reach the nodes package, which must not need them back.

        ``business_metrics`` imports ``nodes.react_recovery``, whose package loads
        the response node: the response reading anything from the metrics module
        closed an import cycle only an import ORDER reveals — a fresh interpreter
        importing the metrics first fails on it.
        """
        import subprocess
        import sys
        from pathlib import Path

        api_dir = Path(__file__).resolve().parents[5]
        probe = "import src.domains.agents.services.business_metrics"
        done = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=api_dir,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        assert done.returncode == 0, done.stderr[-1500:]
