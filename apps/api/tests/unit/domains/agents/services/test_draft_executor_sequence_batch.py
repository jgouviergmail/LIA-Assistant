"""A batch decided draft by draft runs the confirmed ones and REPORTS the rest.

ADR-288: a sequence of independent drafts settles into one ``confirm_batch``
whose entries carry the decision taken on each. The executor must never run
a cancelled entry, and must never drop it in silence either — the person
cancelled it, the answer says so.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.services import draft_executor
from src.domains.agents.services.draft_executor import (
    DraftExecutionResult,
    execute_draft_if_confirmed,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _entry(action: str, draft_id: str, draft_type: str = "email") -> dict[str, Any]:
    entry = {
        "action": action,
        "draft_id": draft_id,
        "draft_type": draft_type,
        "draft_content": {"to": f"{draft_id}@x", "subject": f"S {draft_id}"},
    }
    if action == "cancel":
        entry["reason"] = "not this one"
    return entry


async def _run(batch: list[dict[str, Any]]) -> tuple[DraftExecutionResult, AsyncMock]:
    async def fake_execute(single: dict[str, Any], *_: Any, **__: Any) -> DraftExecutionResult:
        return DraftExecutionResult(
            success=True,
            draft_id=single["draft_id"],
            draft_type=single["draft_type"],
            action="confirm",
            result_data={"message_id": "m", "_draft_content": single["draft_content"]},
            user_language="fr",
        )

    spy = AsyncMock(side_effect=fake_execute)
    with (
        patch.object(draft_executor, "_execute_confirmed_draft", spy),
        patch.object(draft_executor, "ensure_executors_registered", lambda: None),
    ):
        result = await execute_draft_if_confirmed(
            {"action": DraftAction.CONFIRM_BATCH.value, "batch": batch}, {}, "run-1", "fr"
        )
    assert result is not None
    return result, spy


class TestCancelledEntriesAreSkippedAndReported:
    async def test_only_confirmed_entries_run(self) -> None:
        result, spy = await _run(
            [_entry("cancel", "d1"), _entry("confirm", "d2"), _entry("confirm", "d3", "event")]
        )
        assert [call.args[0]["draft_id"] for call in spy.await_args_list] == ["d2", "d3"]
        assert result.success is True

    async def test_the_counts_say_what_ran_and_what_did_not(self) -> None:
        result, _ = await _run([_entry("cancel", "d1"), _entry("confirm", "d2")])
        data = result.result_data
        assert (data["success_count"], data["error_count"], data["cancelled_count"]) == (1, 0, 1)
        assert data["total_count"] == 1, "the total is what was ATTEMPTED"

    async def test_a_cancelled_entry_keeps_its_row(self) -> None:
        result, _ = await _run([_entry("cancel", "d1"), _entry("confirm", "d2")])
        rows = result.result_data["batch_results"]
        assert [row["draft_id"] for row in rows] == ["d1", "d2"]
        assert rows[0]["status"] == "cancelled"
        assert rows[0]["data"]["_draft_content"]["subject"] == "S d1"
        assert rows[1]["status"] == "success"

    async def test_a_mixed_batch_declares_no_single_type(self) -> None:
        result, _ = await _run([_entry("confirm", "d1", "email"), _entry("confirm", "d2", "event")])
        assert result.draft_type == "batch"

    async def test_a_homogeneous_batch_keeps_its_type(self) -> None:
        result, _ = await _run([_entry("confirm", "d1"), _entry("confirm", "d2")])
        assert result.draft_type == "email"
