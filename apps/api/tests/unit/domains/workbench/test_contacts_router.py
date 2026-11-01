"""The contacts routes at the door (ADR-369, Task 7.1).

Each route reaches its service for the signed-in account under its window —
reads apart from writes. An id of the wrong shape, a search inside a group, or
a list past the published bound asks nothing of anyone.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.core.constants import WORKBENCH_CONTACT_VALUES_MAX
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.workbench import contacts_service
from src.domains.workbench import router as router_module
from src.domains.workbench.schemas.contacts import Contact, ContactGroups, ContactsPage

pytestmark = pytest.mark.unit

_KEY = "11111111-1111-4111-8111-111111111111"
_CONTACT = Contact(
    id="people/c1",
    name="Ana",
    email=None,
    phone=None,
    organization=None,
    emails=[],
    phones=[],
    addresses=[],
    notes=None,
)
_PAGE = ContactsPage(items=[], next_page_token=None, truncated=False)
_SERVICES: dict[str, Any] = {
    "list_contacts": _PAGE,
    "search_other": _PAGE,
    "list_groups": ContactGroups(groups=[]),
    "read_contact": _CONTACT,
    "create_contact": _CONTACT,
    "update_contact": _CONTACT,
    "delete_contact": None,
}


async def _handler(_: Any, exc: BaseAPIException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


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
    user = SimpleNamespace(id=uuid4(), timezone="Europe/Paris")
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: user
    services = {name: AsyncMock(return_value=value) for name, value in _SERVICES.items()}
    with patch.multiple(contacts_service, **services):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(limiter=limiter, user=user, **services)


_ROUTES = [
    ("GET", "/workbench/contacts?q=ana", None, "list_contacts", 200, "workbench_read"),
    (
        "GET",
        "/workbench/contacts/contact?id=people/c1",
        None,
        "read_contact",
        200,
        "workbench_read",
    ),
    ("GET", "/workbench/contacts/groups", None, "list_groups", 200, "workbench_read"),
    ("GET", "/workbench/contacts/other?q=ana", None, "search_other", 200, "workbench_read"),
    (
        "POST",
        "/workbench/contacts",
        {
            "name": "Ana",
            "emails": [{"value": "ana@example.org", "type": "work"}],
            "idempotency_key": _KEY,
        },
        "create_contact",
        201,
        "workbench_write",
    ),
    (
        "PATCH",
        "/workbench/contacts",
        {"id": "people/c1", "phones": []},
        "update_contact",
        200,
        "workbench_write",
    ),
    ("DELETE", "/workbench/contacts?id=people/c1", None, "delete_contact", 204, "workbench_write"),
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

    response = await client.request(method, url, json=body)

    assert response.status_code == status, response.text
    called = getattr(seams, service)
    called.assert_awaited_once()
    assert called.await_args.args[0] == seams.user.id
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == [window]


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("GET", "/workbench/contacts/contact?id=a%20b", None),
        ("GET", "/workbench/contacts?q=ana&group=contactGroups/x", None),
        ("GET", "/workbench/contacts/other", None),
        (
            "PATCH",
            "/workbench/contacts",
            {
                "id": "c1",
                "emails": [
                    {"value": f"a{i}@example.org"} for i in range(WORKBENCH_CONTACT_VALUES_MAX + 1)
                ],
            },
        ),
    ],
)
async def test_an_odd_request_asks_nothing(
    http: Any, method: str, url: str, body: dict[str, Any] | None
) -> None:
    client, seams = http

    response = await client.request(method, url, json=body)

    assert response.status_code == 422
    for name in _SERVICES:
        getattr(seams, name).assert_not_awaited()
