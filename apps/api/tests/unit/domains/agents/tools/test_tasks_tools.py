"""Unit tests for tasks_tools.py.

Regression coverage for the 2026-07 codebase audit (wave 1):
- ListTaskListsTool must resolve its default ``max_results`` from settings via
  ``get_settings()`` (calling the factory), not via attribute access on the
  factory function itself (AttributeError swallowed as INTERNAL_ERROR).

The lists reach the answer as lists (owner rule, 2026-11-10): each one's id and name in
``structured_data``, and which is the default one when that is known.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import get_settings
from src.domains.agents.tools import task_organize_tools
from src.domains.agents.tools.task_organize_tools import ListTaskListsTool

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def user_id():
    """Generate test user ID."""
    return uuid4()


@pytest.fixture
def mock_tasks_client():
    """Mock GoogleTasksClient."""
    client = AsyncMock()
    client.list_task_lists = AsyncMock(
        return_value={"items": [{"id": "list-1", "title": "My Tasks", "updated": "2026-07-03"}]}
    )
    return client


@pytest.fixture
def list_task_lists_tool():
    """Create ListTaskListsTool instance."""
    return ListTaskListsTool()


@pytest.fixture(autouse=True)
def default_list():
    """The list a new task goes in when nobody names one: the account's only list."""
    with patch.object(
        task_organize_tools,
        "new_task_list",
        AsyncMock(return_value={"id": "list-1", "title": "My Tasks"}),
    ) as resolved:
        yield resolved


# ============================================================================
# REGRESSION: default max_results must come from get_settings() (audit item 1)
# ============================================================================


@pytest.mark.asyncio
async def test_list_task_lists_default_max_results_from_settings(
    list_task_lists_tool, user_id, mock_tasks_client
):
    """Without an explicit max_results, the settings default is used (no AttributeError)."""
    result = await list_task_lists_tool.execute_api_call(mock_tasks_client, user_id)

    expected_default = get_settings().tasks_tool_default_max_results
    mock_tasks_client.list_task_lists.assert_awaited_once_with(max_results=expected_default)
    assert result == {
        "task_lists": [{"id": "list-1", "title": "My Tasks", "updated": "2026-07-03"}],
        "default_list_id": "list-1",
    }


@pytest.mark.asyncio
async def test_list_task_lists_explicit_max_results_passthrough(
    list_task_lists_tool, user_id, mock_tasks_client
):
    """An explicit max_results is forwarded to the client untouched."""
    await list_task_lists_tool.execute_api_call(mock_tasks_client, user_id, max_results=5)

    mock_tasks_client.list_task_lists.assert_awaited_once_with(max_results=5)


# ============================================================================
# The lists reach the answer as lists, the default one named (2026-11-10)
# ============================================================================

_TWO_LISTS = [{"id": "list-1", "title": "My Tasks"}, {"id": "list-2", "title": "Home"}]


@pytest.mark.asyncio
async def test_the_default_list_is_asked_with_no_list_named(
    list_task_lists_tool, user_id, mock_tasks_client, default_list
):
    await list_task_lists_tool.execute_api_call(mock_tasks_client, user_id)

    default_list.assert_awaited_once_with(mock_tasks_client, user_id, None)


def test_each_list_reaches_the_answer_with_its_id_its_name_and_the_default_one(
    list_task_lists_tool,
):
    output = list_task_lists_tool.format_registry_response(
        {"task_lists": _TWO_LISTS, "default_list_id": "list-2"}
    )

    assert output.structured_data == {
        "task_lists": [
            {"id": "list-1", "title": "My Tasks", "is_default": False},
            {"id": "list-2", "title": "Home", "is_default": True},
        ],
        "count": 2,
    }


def test_a_default_list_that_is_not_among_those_listed_marks_none(list_task_lists_tool):
    """« No list is the default » is never told: the fact is left out when unknown."""
    output = list_task_lists_tool.format_registry_response(
        {"task_lists": _TWO_LISTS, "default_list_id": "@default"}
    )

    assert output.structured_data["task_lists"] == [
        {"id": "list-1", "title": "My Tasks"},
        {"id": "list-2", "title": "Home"},
    ]


def test_a_list_without_an_id_is_no_list(list_task_lists_tool):
    output = list_task_lists_tool.format_registry_response(
        {"task_lists": [{"title": "Ghost"}, *_TWO_LISTS], "default_list_id": "list-1"}
    )

    assert [entry["id"] for entry in output.structured_data["task_lists"]] == [
        "list-1",
        "list-2",
    ]
    assert len(output.registry_updates) == 2
