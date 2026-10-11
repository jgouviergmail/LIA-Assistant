"""A confirmed draft's explicit refusal stays a refusal at every observer."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from langchain_core.runnables import RunnableConfig

from src.domains.agents.effects.runtime import ClaimTicket, gated_executor
from src.domains.agents.services import draft_executor
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "error": "Operation refused", "error_code": "FORBIDDEN"},
        {"success": False, "error_code": "CONFLICT"},
    ],
)
async def test_returned_failure_does_not_report_success_or_mutate_context(
    payload: dict[str, Any],
) -> None:
    """Exercise the real dispatcher, not a mock of its final result."""

    async def refuse(content: dict[str, Any], user_id: UUID, deps: object) -> dict[str, Any]:
        return dict(payload)

    metrics = MagicMock()
    sync = AsyncMock()
    config: RunnableConfig = {"configurable": {"thread_id": "test-conversation"}}
    with (
        installed_runtime_context(deps=object()),
        patch.dict(draft_executor.EXECUTOR_REGISTRY, {"test_outcome": refuse}),
        patch.object(draft_executor, "registry_drafts_executed_total", metrics),
        patch.object(draft_executor, "_sync_tcm_after_draft_execution", sync),
    ):
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": "draft-refusal",
                "draft_type": "test_outcome",
                "draft_content": {"target": "owned-resource"},
            },
            config,
            "run-outcome",
            "en",
        )

    assert result.success is False
    assert result.result_data == payload
    assert result.error
    sync.assert_not_awaited()
    metrics.labels.assert_called_once_with(draft_type="test_outcome", outcome="failed")


@pytest.mark.parametrize("payload", [{"success": True, "id": "saved"}, {"id": "legacy"}])
async def test_explicit_and_legacy_success_keep_the_existing_context_sync(
    payload: dict[str, Any],
) -> None:
    async def succeed(content: dict[str, Any], user_id: UUID, deps: object) -> dict[str, Any]:
        return dict(payload)

    sync = AsyncMock()
    with (
        installed_runtime_context(deps=object()),
        patch.dict(draft_executor.EXECUTOR_REGISTRY, {"test_outcome": succeed}),
        patch.object(draft_executor, "_sync_tcm_after_draft_execution", sync),
    ):
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": "draft-ok", "draft_type": "test_outcome", "draft_content": {}},
            {"configurable": {"thread_id": "test-conversation"}},
            "run-outcome",
            "en",
        )

    assert result.success is True
    sync.assert_awaited_once()


async def test_gate_ledger_and_dispatcher_agree_on_a_returned_failure() -> None:
    from uuid import uuid4

    async def refuse(content: dict[str, Any], user_id: UUID, deps: object) -> dict[str, Any]:
        return {"success": False, "error_code": "FORBIDDEN"}

    ledger = MagicMock()
    ledger.claim = AsyncMock(return_value=ClaimTicket(uuid4(), uuid4(), None))
    ledger.close = AsyncMock()
    sync = AsyncMock()
    with (
        installed_runtime_context(deps=object()),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(
            draft_executor.EXECUTOR_REGISTRY,
            {"test_outcome": gated_executor("test_outcome", refuse)},
        ),
        patch.object(draft_executor, "_sync_tcm_after_draft_execution", sync),
    ):
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": "draft-ledger", "draft_type": "test_outcome", "draft_content": {}},
            {"configurable": {"thread_id": "test-conversation"}},
            "run-outcome",
            "en",
        )

    assert result.success is False
    ledger.close.assert_awaited_once()
    assert ledger.close.await_args.kwargs["outcome"].succeeded is False
    sync.assert_not_awaited()
