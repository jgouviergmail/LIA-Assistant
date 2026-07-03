"""Unit tests for tasks_tools.py.

Regression coverage for the 2026-07 codebase audit (wave 1):
- ListTaskListsTool must resolve its default ``max_results`` from settings via
  ``get_settings()`` (calling the factory), not via attribute access on the
  factory function itself (AttributeError swallowed as INTERNAL_ERROR).
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import get_settings
from src.domains.agents.tools.tasks_tools import ListTaskListsTool

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
        "task_lists": [{"id": "list-1", "title": "My Tasks", "updated": "2026-07-03"}]
    }


@pytest.mark.asyncio
async def test_list_task_lists_explicit_max_results_passthrough(
    list_task_lists_tool, user_id, mock_tasks_client
):
    """An explicit max_results is forwarded to the client untouched."""
    await list_task_lists_tool.execute_api_call(mock_tasks_client, user_id, max_results=5)

    mock_tasks_client.list_task_lists.assert_awaited_once_with(max_results=5)
