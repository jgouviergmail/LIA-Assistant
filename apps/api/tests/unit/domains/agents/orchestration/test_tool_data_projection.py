"""A read tool's data reaches its pipeline step as a bounded data block (ADR-347).

The pipeline's response model read a step's message and the registry items,
nothing else; a read tool whose facts lived in ``structured_data`` handed the
answer a sentence about them. The executor now projects what that data carries
beyond the registry items — through the ReAct functions themselves — into the
step's data, where the response's tool data section reads it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.core.field_names import FIELD_TOOL_DATA
from src.domains.agents.orchestration import parallel_executor as pe
from src.domains.agents.orchestration import tool_data_projection as projection
from src.domains.agents.orchestration.for_each_aggregation import aggregate_for_each_results
from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult
from src.domains.agents.orchestration.tool_data_projection import (
    ToolDataRecord,
    beyond_the_registry,
    previous_turns_without_tool_data,
    tool_data_fields,
    without_tool_data,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    MutationPolicy,
    PermissionProfile,
    PipelineDataChannel,
    ToolManifest,
)
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = pytest.mark.unit

BUDGET = 2_000


def _manifest(
    *,
    mutation_policy: MutationPolicy | None = "read",
    mutation_policy_reason: str | None = None,
    pipeline_data_channel: PipelineDataChannel = "data_block",
    pipeline_data_channel_reason: str | None = None,
) -> ToolManifest:
    return ToolManifest(
        name="probe_tool",
        agent="probe_agent",
        description="test",
        parameters=[],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mutation_policy=mutation_policy,
        mutation_policy_reason=mutation_policy_reason,
        pipeline_data_channel=pipeline_data_channel,
        pipeline_data_channel_reason=pipeline_data_channel_reason,
    )


_CONNECTIONS = UnifiedToolOutput.data_success(
    message="2 accepted connection(s).",
    structured_data={
        "connections": [
            {"name": "Ada", "i_share": ["calendar:availability"]},
            {"name": "Linus", "i_share": []},
        ]
    },
)


class _Builder(ToolOutputMixin):
    tool_name = "get_emails_tool"


def _emails_output() -> UnifiedToolOutput:
    emails = [
        {"id": "m1", "subject": "Quarterly figures", "from": "a@example.com", "snippet": "x"},
        {"id": "m2", "subject": "Lunch", "from": "b@example.com", "snippet": "y"},
    ]
    return _Builder().build_emails_output(
        emails=emails, user_timezone="UTC", result_size_estimate=42, next_page_token="tok_9"
    )


def _fields(
    output: object, manifest: ToolManifest | None = None, share: int = 1
) -> dict[str, list[ToolDataRecord]]:
    with patch.object(projection, "slot_tool_result_budget", return_value=BUDGET):
        return tool_data_fields(
            output,
            manifest=_manifest() if manifest is None else manifest,
            tool_name="probe_tool",
            share=share,
        )


class TestWhatIsProjected:
    def test_a_registry_less_read_reaches_the_step_as_external_data(self) -> None:
        (record,) = _fields(_CONNECTIONS)[FIELD_TOOL_DATA]

        assert record["tool"] == "probe_tool"
        assert "Linus" in record["text"]
        assert "calendar:availability" in record["text"]
        assert "<external_content" in record["text"]
        assert record["truncated"] is False

    def test_a_mixed_output_keeps_its_extras_and_drops_what_the_registry_shows(self) -> None:
        (record,) = _fields(_emails_output())[FIELD_TOOL_DATA]

        assert "tok_9" in record["text"]
        assert "42" in record["text"]
        assert "Quarterly figures" not in record["text"]

    def test_the_registry_items_are_recognised_by_content_whatever_their_key(self) -> None:
        output = _emails_output()
        renamed = {"forecasts": output.structured_data["emails"], "window": "today"}

        assert beyond_the_registry(renamed, output.registry_updates) == {"window": "today"}

    def test_a_list_only_partly_in_the_registry_keeps_the_rest(self) -> None:
        output = _emails_output()
        extra = {"id": "m3", "subject": "Not filed"}
        data = {"emails": [*output.structured_data["emails"], extra]}

        assert beyond_the_registry(data, output.registry_updates) == {"emails": [extra]}

    def test_a_registry_only_output_projects_nothing(self) -> None:
        output = _emails_output()
        registry_only = UnifiedToolOutput.data_success(
            message="[search] 2 email(s)", registry_updates=output.registry_updates
        )

        assert _fields(registry_only) == {}

    @pytest.mark.parametrize(
        "manifest",
        [
            pytest.param(
                _manifest(mutation_policy="reversible", mutation_policy_reason="Undone."),
                id="acting_tool",
            ),
            pytest.param(
                _manifest(
                    pipeline_data_channel="message",
                    pipeline_data_channel_reason="Rendered in the message.",
                ),
                id="message_channel",
            ),
        ],
    )
    def test_a_tool_whose_data_goes_elsewhere_projects_nothing(
        self, manifest: ToolManifest
    ) -> None:
        assert _fields(_CONNECTIONS, manifest) == {}

    def test_a_failure_projects_nothing(self) -> None:
        failure = UnifiedToolOutput.failure(message="refused", error_code="FORBIDDEN")

        assert _fields(failure) == {}

    def test_a_step_without_a_manifest_projects_nothing(self) -> None:
        with patch.object(projection, "slot_tool_result_budget", return_value=BUDGET):
            assert tool_data_fields(_CONNECTIONS, manifest=None, tool_name="probe_tool") == {}


class TestTheBudget:
    def test_items_of_one_loop_share_the_budget(self) -> None:
        (record,) = _fields(_CONNECTIONS, share=4)[FIELD_TOOL_DATA]

        assert record["budget_tokens"] == BUDGET // 4

    def test_a_long_list_is_paged_whole_items_and_says_so(self) -> None:
        rows = [{"name": f"row {i}", "notes": "word " * 120} for i in range(40)]
        output = UnifiedToolOutput.data_success(message="40 rows", structured_data={"rows": rows})

        (record,) = _fields(output)[FIELD_TOOL_DATA]

        assert record["truncated"] is True
        assert record["key"] == "rows"
        assert 1 <= record["shown"] < record["total"] == 40


class TestItNeverFailsTheStep:
    def test_a_projection_that_raises_costs_the_block_never_the_step(self) -> None:
        with (
            patch.object(projection, "extract_data_block", side_effect=RuntimeError("boom")),
            patch.object(projection.logger, "error") as logged,
        ):
            assert _fields(_CONNECTIONS) == {}

        logged.assert_called_once_with(
            "pipeline_tool_data_projection_failed",
            tool_name="probe_tool",
            error_type="RuntimeError",
        )


async def _execute(output: UnifiedToolOutput, manifest: ToolManifest) -> dict[str, Any]:
    async def _coroutine(**kwargs: Any) -> UnifiedToolOutput:
        return output

    tool = SimpleNamespace(coroutine=_coroutine, args_schema=None, name="probe_tool")
    registry = SimpleNamespace(get_tool=lambda name: tool)
    with (
        patch.object(pe.ToolRegistry, "get_instance", return_value=registry),
        patch.object(pe, "_build_tool_runtime", side_effect=lambda t, a, c, s: a),
        patch.object(projection, "slot_tool_result_budget", return_value=BUDGET),
    ):
        executed = await pe._execute_tool(
            tool_name="probe_tool",
            args={},
            config={"configurable": {}},
            store=None,
            manifest=manifest,
        )
    data: dict[str, Any] = executed.result["data"]
    return data


class TestTheExecutorCarriesIt:
    async def test_a_read_step_carries_its_record_in_its_data(self) -> None:
        data = await _execute(_CONNECTIONS, _manifest())

        (record,) = data[FIELD_TOOL_DATA]
        assert "Linus" in record["text"]
        # The step's own data is unchanged beside it: references still resolve.
        assert data["connections"][1]["name"] == "Linus"

    async def test_an_acting_step_carries_none(self) -> None:
        data = await _execute(
            _CONNECTIONS, _manifest(mutation_policy="reversible", mutation_policy_reason="Undone.")
        )

        assert FIELD_TOOL_DATA not in data

    def test_a_loop_keeps_every_item_s_record(self) -> None:
        steps: dict[str, dict[str, object]] = {
            "step_2_item_0": {FIELD_TOOL_DATA: [{"tool": "t", "text": "a"}]},
            "step_2_item_1": {FIELD_TOOL_DATA: [{"tool": "t", "text": "b"}]},
        }

        aggregate_for_each_results(steps, "step_2", ["step_2_item_0", "step_2_item_1"])

        records = steps["step_2"][FIELD_TOOL_DATA]
        assert isinstance(records, list)
        assert [record["text"] for record in records] == ["a", "b"]

    def test_the_record_survives_the_state_round_trip(self) -> None:
        (record,) = _fields(_CONNECTIONS)[FIELD_TOOL_DATA]

        assert json.loads(json.dumps(record)) == record


_RECORD = {"tool": "probe_tool", "text": "{}"}


class TestOnlyTheTurnKeepsItsRecords:
    """A record serves its own turn's response; the checkpoint carries no other."""

    def test_the_persisted_steps_carry_no_record(self) -> None:
        read_step: dict[str, object] = {"connections": [], FIELD_TOOL_DATA: [_RECORD]}
        steps: dict[str, object] = {
            "step_1": read_step,
            "step_2": {"success": False, "error": "x"},
            "step_3": "legacy text",
        }

        persisted = without_tool_data(steps)

        assert persisted == {
            "step_1": {"connections": []},
            "step_2": {"success": False, "error": "x"},
            "step_3": "legacy text",
        }
        assert FIELD_TOOL_DATA in read_step, "the turn's own entries are never mutated"

    def test_the_other_turns_lose_their_records_and_this_one_keeps_its_own(self) -> None:
        def entry() -> dict[str, object]:
            payload = {"result": "ok", FIELD_TOOL_DATA: [_RECORD]}
            return {"data": {"step_results": [payload], "aggregated_results": [payload]}}

        results = {"6:plan_executor": entry(), "7:plan_executor": entry(), "6:react": {}}

        kept = previous_turns_without_tool_data(results, 7)

        assert kept["7:plan_executor"] == entry()
        assert kept["6:plan_executor"] == {
            "data": {"step_results": [{"result": "ok"}], "aggregated_results": [{"result": "ok"}]}
        }
        assert kept["6:react"] == {}

    def test_a_record_inside_an_envelope_is_stripped_too(self) -> None:
        """The section reads a record in either shape; the strippers remove both."""
        inner: dict[str, object] = {"rows": [], FIELD_TOOL_DATA: [_RECORD]}
        enveloped: dict[str, object] = {"success": True, "data": inner}

        persisted = without_tool_data({"step_1": enveloped})

        assert persisted == {"step_1": {"success": True, "data": {"rows": []}}}
        assert FIELD_TOOL_DATA in inner, "the turn's own entry is never mutated"

    def test_the_multi_domain_copy_of_the_steps_carries_no_record(self) -> None:
        """``MultiDomainResultData.completed_steps`` copies every step payload, read by nobody.

        The section reads ``step_results``; a second copy of each block in the
        same entry would only double what the checkpoint stores.
        """

        def step(index: int, tool: str, result: dict[str, object]) -> StepResult:
            return StepResult(
                step_index=index, tool_name=tool, args={}, result=result, success=True
            )

        overview: dict[str, object] = {"person": "Alice", FIELD_TOOL_DATA: [_RECORD]}
        execution = ExecutionResult(
            success=True,
            step_results=[
                step(0, "get_person_overview_tool", overview),
                step(1, "get_contacts_tool", {"contacts": [{"resource_name": "c1"}], "total": 1}),
                step(2, "get_emails_tool", {"emails": [{"id": "m1"}], "total": 1}),
            ],
            total_steps=3,
            completed_steps=3,
            total_execution_time_ms=0,
        )

        mapped = map_execution_result_to_agent_result(
            execution_result=execution, plan_id="p", turn_id=1
        )
        data = mapped["1:plan_executor"]["data"]

        assert data["result_type"] == "multi_domain"
        assert data["step_results"][0][FIELD_TOOL_DATA] == [_RECORD]
        assert all(FIELD_TOOL_DATA not in payload for payload in data["completed_steps"].values())
