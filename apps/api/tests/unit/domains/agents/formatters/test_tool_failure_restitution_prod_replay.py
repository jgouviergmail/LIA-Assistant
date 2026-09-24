"""Replay of the production turns that prove a tool failure never reaches the model.

Three measured turns, replayed against the real shapes the executor and the
ReAct loop write:

* 2026-09-09 09:06 UTC — three ``fetch_web_page_tool`` calls answered 403 and
  the response prompt received ``❓ plan_executor: Statut inconnu (failed)``.
* 2026-09-17 12:35 UTC — ``send_peer_message_tool`` failed with a precise,
  actionable message and the person was told « aucun service de messagerie
  n'est connecté », a diagnosis the tool never produced.
* 2026-09-10 … 2026-09-21, every other morning — a scheduled ReAct briefing
  whose calendar/tasks/mail tools failed announced that those connectors were
  not configured, while all three were ``ACTIVE``.

Every assertion here is about what the MODEL receives, never about wording it
chooses afterwards. Red before ADR-303.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import ToolMessage

from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt
from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult
from src.domains.diagnostics.failure_context import (
    extract_failures_from_steps,
    extract_failures_from_tool_messages,
)

pytestmark = [pytest.mark.unit]

_LISTING_IDS = ("66103994839", "87103543658", "69119842856")

#: What ``send_peer_message_tool`` really returns when the name matches nobody.
_PEER_ERROR = "No connected user matches that exact name. Connected users: Alice, Bob."


def _fetch_error(listing_id: str) -> str:
    return (
        "HTTP error 403 fetching "
        f"https://www.lacentrale.fr/auto-occasion-annonce-{listing_id}.html"
    )


def _failed_step_entry(error: str, code: str = "EXTERNAL_API_ERROR") -> dict[str, object]:
    """EXACTLY the shape ``parallel_executor`` writes for a failed TOOL step."""
    return {"success": False, "error": error, "error_code": code}


def _step(index: int, tool: str, *, error: str | None = None) -> StepResult:
    if error is None:
        return StepResult(
            step_index=index,
            tool_name=tool,
            args={},
            result={"success": True, "data": {"result": "🔔 Reminder created"}},
            success=True,
        )
    return StepResult(
        step_index=index,
        tool_name=tool,
        args={},
        result=_failed_step_entry(error),
        success=False,
        error=error,
    )


def _prompt_for(steps: list[StepResult], *, plan_succeeded: bool) -> str:
    failed = [s for s in steps if not s.success]
    execution_result = ExecutionResult(
        success=plan_succeeded,
        step_results=steps,
        total_steps=len(steps),
        completed_steps=len(steps),
        failed_step_index=failed[0].step_index if failed else None,
        error=failed[0].error if (failed and not plan_succeeded) else None,
        total_execution_time_ms=0,
    )
    agent_results = map_execution_result_to_agent_result(
        execution_result=execution_result, plan_id="p", turn_id=9
    )
    return format_agent_results_for_prompt(agent_results, current_turn_id=9, user_language="fr")


class TestPipelineTurn:
    """The 2026-09-09 turn: three fetches, all refused by an anti-bot."""

    def test_the_prompt_never_says_unknown_status(self) -> None:
        prompt = _prompt_for(
            [
                _step(i, "fetch_web_page_tool", error=_fetch_error(lid))
                for i, lid in enumerate(_LISTING_IDS)
            ],
            plan_succeeded=False,
        )
        assert "inconnu" not in prompt.lower()
        assert "unknown" not in prompt.lower()

    def test_a_partial_plan_still_confirms_what_succeeded(self) -> None:
        """2026-09-09 shape, one step short: the reminder was really created."""
        prompt = _prompt_for(
            [
                _step(0, "create_reminder_tool"),
                _step(1, "fetch_web_page_tool", error=_fetch_error(_LISTING_IDS[0])),
            ],
            plan_succeeded=True,
        )
        assert "🔔 Reminder created" in prompt


class TestWhatTheToolsSAIDSurvives:
    """A tool's own words reach the model in the shape the executor really writes.

    ``parallel_executor`` writes ``{"success", "data": <structured_data>,
    "message"}``; the extractor looked for a FLAT ``{"result": …}`` that only
    its own fixtures ever produced. Measured: a plan that created a reminder
    reached the response prompt EMPTY, and a sub-agent's full analysis was
    dropped instead of being wrapped for verbatim restitution.
    """

    @staticmethod
    def _executor_payload(**structured: object) -> dict[str, object]:
        """The shape ``parallel_executor._execute_tool`` really writes."""
        return {
            "success": True,
            "data": dict(structured),
            "message": str(structured.get("result", "")),
            "_tcm_saved": False,
            "context_save_mode": "auto",
        }

    def test_an_action_confirmation_reaches_the_prompt(self) -> None:
        step = StepResult(
            step_index=0,
            tool_name="create_reminder_tool",
            args={},
            result=self._executor_payload(result="🔔 Rappel créé pour demain 9h"),
            success=True,
        )
        assert "🔔 Rappel créé pour demain 9h" in _prompt_for([step], plan_succeeded=True)

    def test_a_sub_agent_analysis_is_wrapped_for_verbatim_restitution(self) -> None:
        step = StepResult(
            step_index=0,
            tool_name="delegate_to_sub_agent_tool",
            args={},
            result=self._executor_payload(
                type="sub_agent_analysis",
                analysis="# Rapport\n\nTexte complet de l'expert.",
                expertise="analyste senior",
            ),
            success=True,
        )
        prompt = _prompt_for([step], plan_succeeded=True)
        assert "<SubAgentAnalysis" in prompt
        assert "Texte complet de l'expert." in prompt

    def test_a_failed_step_message_is_not_read_as_a_confirmation(self) -> None:
        """A failed step speaks through the failures directive, never here."""
        step = StepResult(
            step_index=0,
            tool_name="fetch_web_page_tool",
            args={},
            result={
                "success": False,
                "data": {"result": "HTTP error 403 fetching https://x"},
                "message": "HTTP error 403 fetching https://x",
                "error": "HTTP error 403 fetching https://x",
            },
            success=False,
            error="HTTP error 403 fetching https://x",
        )
        ok = StepResult(
            step_index=1,
            tool_name="create_reminder_tool",
            args={},
            result=self._executor_payload(result="🔔 Rappel créé"),
            success=True,
        )
        prompt = _prompt_for([step, ok], plan_succeeded=True)
        assert "🔔 Rappel créé" in prompt
        assert "HTTP error 403" not in prompt


class TestHonestyDirectivePipeline:
    """The directive is the one channel meant to say what failed."""

    def test_every_failed_fetch_is_extracted_with_its_code(self) -> None:
        completed_steps = {
            f"step_{i + 1}": _failed_step_entry(_fetch_error(lid))
            for i, lid in enumerate(_LISTING_IDS)
        }
        failures = extract_failures_from_steps(completed_steps)
        assert len(failures) == 3
        assert {f["error_code"] for f in failures} == {"EXTERNAL_API_ERROR"}
        assert all(f["message"].startswith("HTTP error 403") for f in failures)

    def test_the_peer_message_failure_keeps_its_actionable_text(self) -> None:
        """2026-09-17: the tool said exactly what to do; the person never read it."""
        failures = extract_failures_from_steps(
            {"step_1": _failed_step_entry(_PEER_ERROR, code="NOT_FOUND")}
        )
        assert len(failures) == 1
        assert failures[0]["error_code"] == "NOT_FOUND"
        assert "No connected user matches that exact name" in failures[0]["message"]


class TestHonestyDirectiveReact:
    """The morning briefing runs in ReAct — the same channel must see it."""

    @staticmethod
    def _tool_message(name: str, body: str, *, failed: bool = False) -> ToolMessage:
        """A ToolMessage as the ReAct executor writes it: PROSE plus a marker."""
        return ToolMessage(
            content=body,
            tool_call_id=f"call_{name}",
            name=name,
            status="error" if failed else "success",
        )

    def test_a_prose_tool_message_failure_is_extracted(self) -> None:
        """``compose_tool_message`` emits PROSE — the verdict must be structural."""
        messages = [
            self._tool_message(
                "get_events_tool", "Calendar unavailable: token expired.", failed=True
            ),
            self._tool_message("get_tasks_tool", "Tasks unavailable: token expired.", failed=True),
            self._tool_message("get_weather_forecast_tool", "Forecast for Paris: 10-22 °C."),
        ]
        failures = extract_failures_from_tool_messages(messages)
        names = {f.get("tool") for f in failures}
        assert names == {"get_events_tool", "get_tasks_tool"}
        assert all("token expired" in f["message"] for f in failures)

    def test_a_json_tool_message_failure_is_still_extracted(self) -> None:
        """Backwards compatibility: an explicit JSON payload keeps working."""
        body = json.dumps(
            {"success": False, "error_code": "AUTHENTICATION_ERROR", "message": "token expired"}
        )
        failures = extract_failures_from_tool_messages(
            [self._tool_message("get_emails_tool", body)]
        )
        assert len(failures) == 1
        assert failures[0]["error_code"] == "AUTHENTICATION_ERROR"

    def test_a_successful_tool_message_is_not_a_failure(self) -> None:
        messages = [
            self._tool_message("get_events_tool", "3 events today: stand-up, lunch, review.")
        ]
        assert extract_failures_from_tool_messages(messages) == []
