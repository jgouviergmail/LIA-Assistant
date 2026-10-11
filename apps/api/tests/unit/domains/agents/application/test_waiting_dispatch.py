"""The actual confirmed dispatcher must preserve an explicit secure-interaction wait."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.agents.services import draft_executor
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit


async def test_waiting_draft_is_neither_failure_nor_completed_context_write() -> None:
    pending: dict[str, object] = {
        "success": False,
        "phase": "waiting",
        "committed": False,
        "interaction": {
            "interaction_id": str(uuid4()),
            "kind": "secure",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
    }

    async def wait(content: dict[str, object], actor_id: UUID, deps: object) -> dict[str, object]:
        return pending

    metrics = MagicMock()
    sync = AsyncMock()
    with (
        installed_runtime_context(deps=object()),
        patch.dict(draft_executor.EXECUTOR_REGISTRY, {"test_wait": wait}),
        patch.object(draft_executor, "registry_drafts_executed_total", metrics),
        patch.object(draft_executor, "_sync_tcm_after_draft_execution", sync),
    ):
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": "draft-await", "draft_type": "test_wait", "draft_content": {}},
            {"configurable": {"thread_id": "waiting-contract"}},
            "waiting-run",
            "fr",
        )
    assert result.success is False and result.error is None
    assert result.to_agent_result()["status"] == "waiting"
    assert result.result_data == pending
    metrics.labels.assert_called_once_with(draft_type="test_wait", outcome="waiting")
    sync.assert_not_awaited()


def test_waiting_result_has_an_explicit_hourglass_on_the_actual_chat_renderer() -> None:
    from src.domains.agents.drafts.result_renderer import render_execution_result

    result = {
        "status": "waiting",
        "draft_type": "application_action",
        "action": "confirm",
        "message": "Réauthentification attendue",
        "data": {},
    }
    rendered = render_execution_result(result)
    assert "⏳" in rendered and "Réauthentification attendue" in rendered
    assert "✅" not in rendered and "❌" not in rendered


async def test_batch_waiting_member_is_counted_as_pending_and_rendered_without_failure() -> None:
    from src.domains.agents.drafts.result_renderer import render_execution_result
    from src.domains.agents.services.draft_execution_result import DraftExecutionResult

    payload = {
        "success": False,
        "phase": "waiting",
        "committed": False,
        "interaction": {
            "interaction_id": str(uuid4()),
            "kind": "secure",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
    }
    waiting = DraftExecutionResult(
        False, "await", "application_action", "confirm", result_data=payload, user_language="fr"
    )
    completed = DraftExecutionResult(
        True,
        "done",
        "application_action",
        "confirm",
        result_data={"success": True},
        user_language="fr",
    )
    with patch.object(
        draft_executor, "_execute_confirmed_draft", AsyncMock(side_effect=[waiting, completed])
    ):
        result = await draft_executor._execute_confirmed_batch(
            {
                "action": "confirm_batch",
                "batch": [
                    {"draft_id": "await", "draft_type": "application_action"},
                    {"draft_id": "done", "draft_type": "application_action"},
                ],
            },
            {"configurable": {"thread_id": "await-batch"}},
            "batch-run",
            "fr",
        )
    assert not result.success and result.result_data["waiting_count"] == 1
    assert result.result_data["success_count"] == 1 and result.result_data["error_count"] == 0
    public = result.to_agent_result()
    assert public["status"] == "waiting"
    rendered = render_execution_result(public)
    assert "⏳" in rendered and "❌" not in rendered
    assert "1 interaction(s) en attente" in rendered


def test_waiting_confirmation_turn_is_not_classified_as_no_execution_or_failed() -> None:
    from src.domains.agents.services.business_metrics import infer_conversation_outcome

    assert infer_conversation_outcome({}, {"action": "confirm", "status": "waiting"}) == "waiting"
