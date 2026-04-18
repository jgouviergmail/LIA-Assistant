"""Tests for _sync_tcm_after_draft_execution dispatcher.

Validates the post-execution TCM maintenance:
    - create → set current
    - update → set current + propagate to list in place
    - delete → remove from list + clear current if match
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.draft_executor import _sync_tcm_after_draft_execution

# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


@pytest.fixture
def mock_manager() -> MagicMock:
    """ToolContextManager with every mutation method stubbed as AsyncMock."""
    mock = MagicMock()
    mock.set_current_item = AsyncMock()
    mock.update_item_in_list = AsyncMock(return_value=True)
    mock.remove_item_from_list = AsyncMock(return_value=True)
    mock.clear_current_item = AsyncMock()
    mock.get_current_item = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def runnable_config() -> dict[str, Any]:
    """RunnableConfig with valid user_id and thread_id."""
    return {"configurable": {"user_id": str(uuid4()), "thread_id": "t1"}}


async def _run(
    manager: MagicMock,
    *,
    draft_type: str,
    draft_content: dict[str, Any],
    result_data: dict[str, Any] | None,
    runnable_config: dict[str, Any],
) -> None:
    """Run _sync_tcm_after_draft_execution with manager + store patched to mocks."""
    from src.domains.agents.context.access import TcmSession

    fake_session = TcmSession(
        manager=manager,
        store=AsyncMock(),
        user_id=runnable_config["configurable"]["user_id"],
        session_id=runnable_config["configurable"]["thread_id"],
    )
    with patch(
        "src.domains.agents.services.draft_executor.get_tcm_session",
        new=AsyncMock(return_value=fake_session),
    ):
        await _sync_tcm_after_draft_execution(
            draft_type=draft_type,
            draft_content=draft_content,
            result_data=result_data,
            config=runnable_config,
            run_id="r1",
        )


# ----------------------------------------------------------------------------
# CREATE family — set current only, LIST untouched
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_create_sets_current_only(
    mock_manager: MagicMock, runnable_config: dict[str, Any]
) -> None:
    await _run(
        mock_manager,
        draft_type="event",
        draft_content={"summary": "new rdv"},
        result_data={"success": True, "event_id": "evt_new", "summary": "new rdv"},
        runnable_config=runnable_config,
    )
    mock_manager.set_current_item.assert_awaited_once()
    assert mock_manager.set_current_item.await_args.kwargs["domain"] == "events"
    assert mock_manager.set_current_item.await_args.kwargs["item"]["event_id"] == "evt_new"
    mock_manager.update_item_in_list.assert_not_awaited()
    mock_manager.remove_item_from_list.assert_not_awaited()


# ----------------------------------------------------------------------------
# UPDATE family — set current + propagate in place
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_update_sets_current_and_propagates_to_list(
    mock_manager: MagicMock, runnable_config: dict[str, Any]
) -> None:
    await _run(
        mock_manager,
        draft_type="event_update",
        draft_content={"event_id": "evt_42", "summary": "old"},
        result_data={"success": True, "event_id": "evt_42", "summary": "new"},
        runnable_config=runnable_config,
    )
    mock_manager.set_current_item.assert_awaited_once()
    mock_manager.update_item_in_list.assert_awaited_once()
    kwargs = mock_manager.update_item_in_list.await_args.kwargs
    assert kwargs["domain"] == "events"
    assert kwargs["item_id"] == "evt_42"
    assert kwargs["updated_item"]["summary"] == "new"
    mock_manager.remove_item_from_list.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_update_uses_task_id_key(
    mock_manager: MagicMock, runnable_config: dict[str, Any]
) -> None:
    await _run(
        mock_manager,
        draft_type="task_update",
        draft_content={"task_id": "tsk_1", "title": "old"},
        result_data={"success": True, "task_id": "tsk_1", "title": "new"},
        runnable_config=runnable_config,
    )
    kwargs = mock_manager.update_item_in_list.await_args.kwargs
    assert kwargs["domain"] == "tasks"
    assert kwargs["item_id"] == "tsk_1"


# ----------------------------------------------------------------------------
# DELETE family — remove from list; safety-net clear if current matches
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_delete_removes_from_list(
    mock_manager: MagicMock, runnable_config: dict[str, Any]
) -> None:
    await _run(
        mock_manager,
        draft_type="event_delete",
        draft_content={"event_id": "evt_doomed"},
        result_data={"success": True, "event_id": "evt_doomed"},
        runnable_config=runnable_config,
    )
    mock_manager.remove_item_from_list.assert_awaited_once()
    kwargs = mock_manager.remove_item_from_list.await_args.kwargs
    assert kwargs["domain"] == "events"
    assert kwargs["item_id"] == "evt_doomed"
    mock_manager.set_current_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_when_not_in_list_clears_matching_current(
    mock_manager: MagicMock, runnable_config: dict[str, Any]
) -> None:
    """Direct-fetch item (not in list) but current points to it → clear current."""
    mock_manager.remove_item_from_list.return_value = False
    mock_manager.get_current_item.return_value = {"event_id": "evt_x", "id": "evt_x"}

    await _run(
        mock_manager,
        draft_type="event_delete",
        draft_content={"event_id": "evt_x"},
        result_data={"success": True, "event_id": "evt_x"},
        runnable_config=runnable_config,
    )
    mock_manager.remove_item_from_list.assert_awaited_once()
    mock_manager.clear_current_item.assert_awaited_once()


@pytest.mark.asyncio
async def test_contact_delete_uses_resource_name(
    mock_manager: MagicMock, runnable_config: dict[str, Any]
) -> None:
    await _run(
        mock_manager,
        draft_type="contact_delete",
        draft_content={"resource_name": "people/c_42"},
        result_data={"success": True, "resource_name": "people/c_42"},
        runnable_config=runnable_config,
    )
    kwargs = mock_manager.remove_item_from_list.await_args.kwargs
    assert kwargs["domain"] == "contacts"
    assert kwargs["item_id"] == "people/c_42"


# ----------------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_draft_type_is_noop(
    mock_manager: MagicMock, runnable_config: dict[str, Any]
) -> None:
    await _run(
        mock_manager,
        draft_type="unknown",
        draft_content={},
        result_data={"ok": True},
        runnable_config=runnable_config,
    )
    mock_manager.set_current_item.assert_not_awaited()
    mock_manager.update_item_in_list.assert_not_awaited()
    mock_manager.remove_item_from_list.assert_not_awaited()
