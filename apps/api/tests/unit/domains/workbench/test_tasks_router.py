"""The tasks routes at the door (ADR-369, Task 6.1).

Each route reaches its service for the signed-in account and in its zone,
under its window (reads apart from writes); an id or a cursor of the wrong
shape is refused before any provider is asked; a refusal leaves with its code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.workbench import router as router_module
from src.domains.workbench import tasks_organize, tasks_service
from src.domains.workbench.errors import ITEM_GONE, refuse
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.tasks import (
    DueTasks,
    Task,
    TaskList,
    TaskListsPage,
    TaskMoveOutcome,
    TasksCleared,
    TasksPage,
    TaskStep,
)

pytestmark = pytest.mark.unit

_TASK = Task(
    id="t1",
    title="Pay",
    notes=None,
    completed=False,
    due=date(2026, 11, 3),
    parent=None,
    position=None,
)
_SERVICES: dict[str, Any] = {
    "list_task_lists": TaskListsPage(items=[TaskList(id="l1", title="Home")], next_page_token=None),
    "create_task_list": TaskList(id="l2", title="Trip"),
    "delete_task_list": None,
    "list_tasks": TasksPage(items=[_TASK], next_page_token="p2"),
    "read_due_tasks": DueTasks(tasks=[], truncated=False, failed=[]),
    "read_task_view": DueTasks(tasks=[], truncated=False, failed=[]),
    "create_task": _TASK,
    "update_task": _TASK,
    "delete_task": None,
}


_STEP = TaskStep(id="s1", title="Pack", checked=False)
_ORGANIZE: dict[str, Any] = {
    "rename_task_list": TaskList(id="l1", title="New"),
    "set_completed": ActOutcome(done=["t1"], failed=[]),
    "delete_tasks": ActOutcome(done=["t1"], failed=[]),
    "move_tasks": TaskMoveOutcome(done=["t1"], failed=[], moved=[]),
    "clear_completed": TasksCleared(deleted=1, remaining=False),
    "place_task": _TASK,
    "add_step": _STEP,
    "change_step": _STEP,
    "remove_step": None,
}


async def _handler(_: Any, exc: BaseAPIException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


@pytest.fixture
async def http(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, Any]]:
    monkeypatch.setattr(
        "src.domains.feature_switches.guard.is_capability_enabled", AsyncMock(return_value=True)
    )
    limiter = MagicMock(acquire=AsyncMock(return_value=True))
    monkeypatch.setattr(
        "src.domains.auth.dependencies.get_rate_limiter", AsyncMock(return_value=limiter)
    )
    app = FastAPI()
    app.include_router(router_module.router)
    app.add_exception_handler(BaseAPIException, _handler)  # type: ignore[arg-type]
    user = SimpleNamespace(id=uuid4(), timezone="America/New_York")
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: user
    services = {name: AsyncMock(return_value=value) for name, value in _SERVICES.items()}
    organize = {name: AsyncMock(return_value=value) for name, value in _ORGANIZE.items()}
    with patch.multiple(tasks_service, **services), patch.multiple(tasks_organize, **organize):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(limiter=limiter, user=user, **services, **organize)


def _key() -> str:
    return str(uuid4())


_ROUTES: list[tuple[str, str, dict[str, Any] | None, str, int, str]] = [
    ("GET", "/workbench/tasks/lists", None, "list_task_lists", 200, "workbench_read"),
    (
        "PATCH",
        "/workbench/tasks/lists",
        {"list_id": "l1", "title": "New"},
        "rename_task_list",
        200,
        "workbench_write",
    ),
    ("GET", "/workbench/tasks/view?view=today", None, "read_task_view", 200, "workbench_read"),
    (
        "POST",
        "/workbench/tasks/selection/completed",
        {"list_id": "l1", "task_ids": ["t1"], "completed": True},
        "set_completed",
        200,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/tasks/selection/delete",
        {"list_id": "l1", "task_ids": ["t1", "t2"]},
        "delete_tasks",
        200,
        "workbench_bulk",
    ),
    (
        "POST",
        "/workbench/tasks/selection/move",
        {"list_id": "l1", "task_ids": ["t1"], "destination_list_id": "l2"},
        "move_tasks",
        200,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/tasks/clear-completed",
        {"list_id": "l1"},
        "clear_completed",
        200,
        "workbench_bulk",
    ),
    (
        "POST",
        "/workbench/tasks/place",
        {"list_id": "l1", "task_id": "t1", "after": None},
        "place_task",
        200,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/tasks/steps",
        {"list_id": "l1", "task_id": "t1", "title": "Pack", "idempotency_key": "K"},
        "add_step",
        201,
        "workbench_write",
    ),
    (
        "PATCH",
        "/workbench/tasks/steps",
        {"list_id": "l1", "task_id": "t1", "step_id": "s1", "checked": True},
        "change_step",
        200,
        "workbench_write",
    ),
    (
        "DELETE",
        "/workbench/tasks/steps?list_id=l1&task_id=t1&step_id=s1",
        None,
        "remove_step",
        204,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/tasks/lists",
        {"title": "Trip", "idempotency_key": "K"},
        "create_task_list",
        201,
        "workbench_write",
    ),
    (
        "DELETE",
        "/workbench/tasks/lists?list_id=l1",
        None,
        "delete_task_list",
        204,
        "workbench_write",
    ),
    ("GET", "/workbench/tasks?list_id=l1", None, "list_tasks", 200, "workbench_read"),
    (
        "GET",
        "/workbench/tasks/due?start=2026-11-02&end=2026-11-08",
        None,
        "read_due_tasks",
        200,
        "workbench_read",
    ),
    (
        "POST",
        "/workbench/tasks",
        {"list_id": "l1", "title": "Pay", "due": "2026-11-03", "idempotency_key": "K"},
        "create_task",
        201,
        "workbench_write",
    ),
    (
        "PATCH",
        "/workbench/tasks",
        {"list_id": "l1", "task_id": "t1", "completed": True},
        "update_task",
        200,
        "workbench_write",
    ),
    (
        "DELETE",
        "/workbench/tasks?list_id=l1&task_id=t1",
        None,
        "delete_task",
        204,
        "workbench_write",
    ),
]


@pytest.mark.parametrize(("method", "url", "body", "service", "status", "window"), _ROUTES)
async def test_each_route_reaches_its_service_under_its_window(
    http: Any,
    method: str,
    url: str,
    body: dict[str, Any] | None,
    service: str,
    status: int,
    window: str,
) -> None:
    client, seams = http
    if body and body.get("idempotency_key") == "K":
        body = {**body, "idempotency_key": _key()}

    response = await client.request(method, url, json=body)

    assert response.status_code == status, response.text
    called = getattr(seams, service)
    called.assert_awaited_once()
    assert called.await_args.args[0] == seams.user.id
    assert f"auth:{window}:user:" in seams.limiter.acquire.await_args.kwargs["key"]


async def test_the_zone_is_the_account_s(http: Any) -> None:
    client, seams = http
    await client.get("/workbench/tasks?list_id=l1&show_completed=true&page_token=p2")

    args, kwargs = seams.list_tasks.await_args.args, seams.list_tasks.await_args.kwargs
    assert args[1] == ZoneInfo("America/New_York")
    assert kwargs == {"list_id": "l1", "show_completed": True, "page_token": "p2"}


async def test_a_page_says_more_exists(http: Any) -> None:
    client, _ = http
    body = (await client.get("/workbench/tasks?list_id=l1")).json()
    assert body["next_page_token"] == "p2"
    assert body["items"][0]["due"] == "2026-11-03"


@pytest.mark.parametrize(
    "url",
    [
        "/workbench/tasks?list_id=a%20b",
        "/workbench/tasks?list_id=" + "x" * 1025,
        "/workbench/tasks?list_id=l1&page_token=" + "x" * 4097,
        "/workbench/tasks/lists?list_id=%0A",
    ],
)
async def test_an_id_or_a_cursor_of_the_wrong_shape_asks_nothing(http: Any, url: str) -> None:
    client, seams = http
    method = "DELETE" if "/lists?" in url else "GET"
    response = await client.request(method, url)
    assert response.status_code == 422
    seams.list_tasks.assert_not_awaited()
    seams.delete_task_list.assert_not_awaited()


async def test_a_create_without_its_key_is_refused(http: Any) -> None:
    client, seams = http
    response = await client.post("/workbench/tasks", json={"list_id": "l1", "title": "Pay"})
    assert response.status_code == 422
    seams.create_task.assert_not_awaited()


async def test_a_refusal_leaves_with_its_code(http: Any) -> None:
    client, seams = http

    async def gone(*_: Any, **__: Any) -> None:
        refuse(ITEM_GONE)

    seams.update_task.side_effect = gone
    response = await client.patch(
        "/workbench/tasks", json={"list_id": "l1", "task_id": "t1", "title": "x"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "item_gone"}}
