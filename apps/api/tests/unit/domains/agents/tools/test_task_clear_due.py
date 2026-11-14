"""A task's due date can be REMOVED by the assistant too (ADR-369, D2).

The workbench's task editor can empty a due date, so the clients gained
``clear_due``; D2 brings the same gesture to ``update_task_tool`` in the same
lot. One wording is published to both readers (the planner's manifest and the
loop's tool schema), the draft carries the removal through the confirmation,
the card says the date goes, and the executor hands it to the client.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.drafts.models import TaskUpdateDraftInput
from src.domains.agents.tasks.catalogue_manifests import update_task_catalogue_manifest
from src.domains.agents.tasks.parameter_descriptions import TASK_CLEAR_DUE_DESCRIPTION
from src.domains.agents.tools import tasks_draft_executors, tasks_tools
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.tasks_tools import UpdateTaskDraftTool, update_task_tool

pytestmark = pytest.mark.unit

_DUE = "2026-11-03T00:00:00.000Z"


def test_manifest_and_schema_read_one_description() -> None:
    parameter = next(p for p in update_task_catalogue_manifest.parameters if p.name == "clear_due")
    assert parameter.description == TASK_CLEAR_DUE_DESCRIPTION
    assert parameter.type == "boolean"
    schema = update_task_tool.tool_call_schema.model_json_schema()
    assert schema["properties"]["clear_due"]["description"] == TASK_CLEAR_DUE_DESCRIPTION


def test_the_draft_round_trips_the_removal() -> None:
    draft = TaskUpdateDraftInput(task_id="t1", clear_due=True, user_language="en")
    assert draft.to_update_task_args()["clear_due"] is True
    assert TaskUpdateDraftInput.model_validate(draft.model_dump()) == draft
    assert TaskUpdateDraftInput(task_id="t1", user_language="en").clear_due is False


class TestTheDraftTool:
    async def _prepare(self, **kwargs: Any) -> dict[str, Any]:
        tool = UpdateTaskDraftTool()
        client = MagicMock(get_task=AsyncMock(return_value={"id": "t1", "due": _DUE}))
        with (
            patch.object(tasks_tools, "own_task_list_id", AsyncMock(return_value="l1")),
            patch.object(tool, "get_user_preferences_safe", AsyncMock(return_value=("UTC", "en"))),
        ):
            return await tool.execute_api_call(client, uuid4(), task_id="t1", **kwargs)

    async def test_a_removal_shows_no_date_and_says_so(self) -> None:
        prepared = await self._prepare(clear_due=True)
        assert prepared["clear_due"] is True
        assert prepared["due"] is None, "the current date is not carried into a removal"

    async def test_a_date_and_its_removal_together_are_refused(self) -> None:
        with pytest.raises(ToolValidationError) as refused:
            await self._prepare(due="2026-11-04T00:00:00Z", clear_due=True)
        assert refused.value.field == "clear_due"


def test_the_card_says_the_date_goes() -> None:
    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.drafts.card_spec import to_markdown_lines
    from src.domains.agents.drafts.dates import draft_datetime_formatter
    from src.domains.agents.drafts.preview_renderer import _render_task_update

    labels = get_draft_preview_labels("en")
    content = TaskUpdateDraftInput(
        task_id="t1",
        clear_due=True,
        current_task={"title": "Pay", "due": _DUE},
        user_language="en",
    ).model_dump()

    lines = _render_task_update(content, labels, draft_datetime_formatter("UTC", "en"))
    card = "\n".join(to_markdown_lines(lines, labels["separator"]))

    due_line = next(line for line in card.splitlines() if labels["due"] in line)
    assert due_line.endswith(f"{labels['due_removed']} ✏️"), due_line
    assert "2026" not in card, "the date that goes is not shown as the one that stays"


async def test_the_executor_hands_the_removal_to_the_client() -> None:
    client = MagicMock(update_task=AsyncMock(return_value={"id": "t1", "title": "Pay"}))
    content = TaskUpdateDraftInput(task_id="t1", clear_due=True, user_language="en").model_dump()

    with patch.object(
        tasks_draft_executors, "_resolve_tasks_client", AsyncMock(return_value=client)
    ):
        await tasks_draft_executors.execute_task_update_draft(content, uuid4(), MagicMock())

    assert client.update_task.await_args.kwargs["clear_due"] is True
    assert client.update_task.await_args.kwargs["due"] is None
