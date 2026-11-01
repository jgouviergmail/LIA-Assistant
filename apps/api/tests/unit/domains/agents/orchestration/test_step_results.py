"""How a tool's output becomes a step's result — pinned before it moved (spec D5).

``_execute_tool`` used to project a registry-aware output inline: registry ids
re-identified per FOR_EACH parent, structured data exposed for Jinja, and at
most ONE draft read off the output. The projection moved to
``orchestration/step_results.py`` so a resumed plan can project a replayed
draft's result the same way (spec D7), and it now reads a LIST of drafts — an
iterative MCP task hands up every confirmation its sub-loop queued.

The golden file was captured from the inline block BEFORE the move, on three
outputs: a plain one, a FOR_EACH-correlated one and a draft. Both doors must
still produce it byte for byte.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.core.field_names import FIELD_CORRELATION_PARENT_ID
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.orchestration import parallel_executor as pe
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = [pytest.mark.unit]

GOLDEN = Path(__file__).parent / "golden" / "step_result_projection.json"
_AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def _item(item_id: str, kind: RegistryItemType, payload: dict[str, Any]) -> RegistryItem:
    return RegistryItem(
        id=item_id,
        type=kind,
        payload=payload,
        meta=RegistryItemMeta(source="fixture", domain=kind.value.lower() + "s", timestamp=_AT),
    )


def _plain() -> UnifiedToolOutput:
    return UnifiedToolOutput.data_success(
        message="2 events found",
        registry_updates={
            "event_a1": _item("event_a1", RegistryItemType.EVENT, {"title": "Standup"}),
            "event_b2": _item("event_b2", RegistryItemType.EVENT, {"title": "Review"}),
        },
        structured_data={"total": 2},
    )


def _correlated() -> UnifiedToolOutput:
    return UnifiedToolOutput.data_success(
        message="Sunny, 21°C",
        registry_updates={
            "weather_fee011": _item("weather_fee011", RegistryItemType.WEATHER, {"temp": 21})
        },
    )


def _draft(draft_id: str = "draft_fixed", tool: str = "mcp_user_abcd1234_delete_note") -> Any:
    return UnifiedToolOutput.data_success(
        message="Confirm the deletion of note n2",
        registry_updates={
            draft_id: _item(
                draft_id,
                RegistryItemType.DRAFT,
                {
                    "draft_type": "tool_call",
                    "content": {
                        "tool_name": tool,
                        "tool_label": "notes · delete note",
                        "tool_args": {"note_id": "n2"},
                    },
                },
            )
        },
        metadata={"draft_id": draft_id, "draft_type": "tool_call", "requires_confirmation": True},
    )


def _grouped() -> UnifiedToolOutput:
    """A LocalQueryEngine GROUP/AGGREGATE answer: members of every shape it may carry."""
    member = _item("contact_c1", RegistryItemType.CONTACT, {"resource_name": "people/c1"})
    return UnifiedToolOutput.data_success(
        message="2 groups",
        registry_updates={"contact_c1": member},
        metadata={
            "groups": [
                {"key": "Paris", "members": [member]},
                {
                    "key": "Lyon",
                    "members": [
                        {"id": "contact_c2", "payload": {"resource_name": "people/c2"}},
                        {"resource_name": "people/c3", "_registry_id": "contact_c3"},
                    ],
                },
            ],
            "distinct_values": ["Lyon", "Paris"],
        },
    )


def _failed() -> UnifiedToolOutput:
    return UnifiedToolOutput.failure(message="The mailbox refused", error_code="RATE_LIMITED")


def _saved() -> UnifiedToolOutput:
    from src.domains.agents.context.schemas import ContextSaveMode

    output = UnifiedToolOutput.data_success(
        message="1 contact", metadata={"_tcm_saved": True}, structured_data={"count": 1}
    )
    output.context_save_mode = ContextSaveMode.CURRENT
    return output


FIXTURES: dict[str, tuple[Any, dict[str, Any]]] = {
    "plain": (_plain, {}),
    "correlated": (_correlated, {FIELD_CORRELATION_PARENT_ID: "event_parent9"}),
    "draft": (_draft, {}),
    "grouped": (_grouped, {}),
    "failed": (_failed, {}),
    "saved": (_saved, {}),
}


async def _through_execute_tool(output: Any, args: dict[str, Any]) -> dict[str, Any]:
    async def _coroutine(**_: Any) -> Any:
        return output

    tool = SimpleNamespace(coroutine=_coroutine, args_schema=None, name="fake_tool")
    registry = MagicMock()
    registry.get_tool.return_value = tool
    with (
        patch.object(pe.ToolRegistry, "get_instance", return_value=registry),
        patch.object(pe, "_build_tool_runtime", side_effect=lambda t, a, c, s: dict(a)),
    ):
        projected = await pe._execute_tool(
            tool_name="fake_tool",
            args=dict(args),
            config={"configurable": {}, "metadata": {"run_id": "run-golden"}},
            store=None,
            turn_id=4,
            step_id="s1",
        )
    return projected.model_dump(mode="json")


def _golden() -> dict[str, Any]:
    golden: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return golden


def _as_listed(golden: dict[str, Any]) -> dict[str, Any]:
    """The golden in today's shape — exactly two intended changes, nothing else.

    1. The one draft the inline block read is a list of one (a task hands up several).
    2. The draft names its step: ``_execute_step`` used to add it after the call,
       the one reader now does.
    """
    listed = {key: value for key, value in golden.items() if key != "draft_info"}
    single = golden["draft_info"]
    listed["draft_infos"] = [{**single, "step_id": "s1"}] if single is not None else []
    return listed


class TestTheProjectionDidNotMove:
    @pytest.mark.parametrize("fixture", sorted(FIXTURES))
    async def test_execute_tool_still_projects_like_the_inline_block(self, fixture: str) -> None:
        build, args = FIXTURES[fixture]

        assert await _through_execute_tool(build(), args) == _as_listed(_golden()[fixture])

    @pytest.mark.parametrize("fixture", sorted(FIXTURES))
    def test_the_extracted_projection_is_the_same_projection(self, fixture: str) -> None:
        from src.domains.agents.orchestration.step_results import project_tool_result

        build, args = FIXTURES[fixture]
        projected = project_tool_result(
            build(),
            tool_name="fake_tool",
            step_id="s1",
            turn_id=4,
            correlation_parent_id=args.get(FIELD_CORRELATION_PARENT_ID),
            manifest=None,
            data_share=1,
        )

        assert projected.model_dump(mode="json") == _as_listed(_golden()[fixture])


def _task_output(*draft_ids: str) -> UnifiedToolOutput:
    """What an iterative MCP task returns when its sub-loop queued confirmations."""
    drafts = [_draft(draft_id, f"mcp_user_abcd1234_delete_{draft_id}") for draft_id in draft_ids]
    registry = {key: item for draft in drafts for key, item in draft.registry_updates.items()}
    pending = [
        {
            "draft_id": draft_id,
            "draft_type": "tool_call",
            "draft_content": registry[draft_id].payload["content"],
            "draft_summary": "Confirm the deletion",
            "registry_ids": [draft_id],
            "tool_name": f"mcp_user_abcd1234_delete_{draft_id}",
            "step_id": None,
        }
        for draft_id in draft_ids
    ]
    return UnifiedToolOutput.data_success(
        message="Archived two notes.",
        registry_updates=registry,
        metadata={"requires_confirmation": True, "pending_drafts": pending},
    )


class TestEveryDraftOfAStepIsRead:
    def test_drafts_of_reads_the_list_a_task_hands_up(self) -> None:
        from src.domains.agents.orchestration.step_results import drafts_of

        drafts = drafts_of(_task_output("d1", "d2"), "mcp_user_abcd1234_task", "s3")

        assert [draft["draft_id"] for draft in drafts] == ["d1", "d2"]
        assert {draft["step_id"] for draft in drafts} == {"s3"}, "each draft names its step"
        assert drafts[1]["tool_name"] == "mcp_user_abcd1234_delete_d2", "the act, not the task"

    def test_drafts_of_reads_a_single_draft_as_before(self) -> None:
        from src.domains.agents.orchestration.step_results import drafts_of

        (draft,) = drafts_of(_draft(), "fake_tool", "s1")

        assert draft["draft_id"] == "draft_fixed" and draft["step_id"] == "s1"
        assert draft["draft_content"]["tool_args"] == {"note_id": "n2"}

    def test_an_output_asking_nothing_has_no_draft(self) -> None:
        from src.domains.agents.orchestration.step_results import drafts_of

        assert drafts_of(_plain(), "fake_tool", "s1") == []

    def test_a_question_without_an_identity_is_no_draft(self) -> None:
        """Nothing could answer it: an id-less draft would fail the queue's validation."""
        from src.domains.agents.orchestration.step_results import drafts_of

        broken = UnifiedToolOutput.data_success(
            message="?", metadata={"requires_confirmation": True}
        )
        assert drafts_of(broken, "fake_tool", "s1") == []

    async def test_one_step_with_two_drafts_queues_two(self) -> None:
        projected = await _through_execute_tool(_task_output("d1", "d2"), {})
        assert [draft["draft_id"] for draft in projected["draft_infos"]] == ["d1", "d2"]

        step = pe.StepResult(
            step_id="s1",
            step_type=pe.StepType.TOOL,
            tool_name="mcp_user_abcd1234_task",
            result=projected["result"],
            success=True,
            draft_infos=[{**draft, "step_id": "s1"} for draft in projected["draft_infos"]],
        )
        drafts: list[dict[str, Any]] = []
        pe._merge_single_step_result({}, step, accumulated_drafts=drafts)

        assert [(draft["draft_id"], draft["step_id"]) for draft in drafts] == [
            ("d1", "s1"),
            ("d2", "s1"),
        ]
