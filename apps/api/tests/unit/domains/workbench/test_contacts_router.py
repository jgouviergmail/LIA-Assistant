"""The contacts routes at the door (ADR-369, Task 7.1).

Each route reaches its service for the signed-in account under its window —
reads apart from writes. An id of the wrong shape, a search inside a group, or
a list past the published bound asks nothing of anyone.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.core.constants import (
    WORKBENCH_CONTACT_PHOTO_MAX_BYTES,
    WORKBENCH_CONTACT_VALUES_MAX,
    WORKBENCH_CONTACTS_IMPORT_MAX_BYTES,
)
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.connectors.clients.contact_photos import ContactPhoto
from src.domains.workbench import (
    contacts_groups,
    contacts_history,
    contacts_photos,
    contacts_service,
    contacts_transfer,
)
from src.domains.workbench import router as router_module
from src.domains.workbench.contacts_transfer import ContactsFile
from src.domains.workbench.schemas.contacts import (
    Contact,
    ContactGroup,
    ContactGroups,
    ContactHistory,
    ContactsImported,
    ContactsPage,
)

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


@contextlib.asynccontextmanager
async def _held(user_id: Any) -> AsyncIterator[None]:
    yield


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


_HISTORY = ContactHistory(
    mail="used",
    received=[],
    sent=[],
    calendar="disabled",
    organized_by_them=[],
    organized_by_you=[],
    shared=[],
    meetings_window_days=720,
    meetings_cut=False,
    telephony="not_requested",
    calls=[],
    calls_window=500,
    calls_cut=False,
    sms="not_requested",
    texts=[],
    texts_window=2000,
    texts_cut=False,
)


class TestAHistory:
    async def test_it_is_read_by_each_address_on_the_person_s_clock(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, seams = http
        read = AsyncMock(return_value=_HISTORY)

        with patch.object(contacts_history, "contact_history", read):
            answer = await client.get(
                "/workbench/contacts/history?address=ana@example.org&address=ana@work.example"
            )

        assert answer.status_code == 200
        assert answer.json()["calendar"] == "disabled"
        user_id, zone, query, now = read.await_args.args
        assert user_id == seams.user.id
        assert str(zone) == "Europe/Paris"
        assert [str(address) for address in query.address] == [
            "ana@example.org",
            "ana@work.example",
        ]
        assert now.tzinfo is UTC
        keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
        assert [key.split(":")[1] for key in keys] == ["workbench_read"]

    async def test_numbers_alone_are_read(self, http: tuple[AsyncClient, Any]) -> None:
        client, _ = http
        read = AsyncMock(return_value=_HISTORY)

        with patch.object(contacts_history, "contact_history", read):
            answer = await client.get(
                "/workbench/contacts/history",
                params=[("phone", "06 12 34 56 78"), ("phone", "+33 1 40 00 00 00")],
            )

        assert answer.status_code == 200
        query = read.await_args.args[2]
        assert (query.address, query.phone) == ([], ["06 12 34 56 78", "+33 1 40 00 00 00"])

    async def test_what_it_answers_is_never_kept_by_a_cache(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http

        with patch.object(contacts_history, "contact_history", AsyncMock(return_value=_HISTORY)):
            answer = await client.get("/workbench/contacts/history?phone=0612345678")

        assert answer.headers["cache-control"] == "no-store"

    @pytest.mark.parametrize(
        "url",
        ["", "?address=not-an-address", "?address=a@b.org&other=1", "?phone=%20%20"],
    )
    async def test_an_odd_request_asks_nothing(
        self, http: tuple[AsyncClient, Any], url: str
    ) -> None:
        client, _ = http
        read = AsyncMock()

        with patch.object(contacts_history, "contact_history", read):
            answer = await client.get(f"/workbench/contacts/history{url}")

        assert answer.status_code == 422
        read.assert_not_awaited()


class TestAPhoto:
    async def test_it_is_served_as_an_image_nothing_can_run(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        read = AsyncMock(return_value=ContactPhoto(b"\xff\xd8\xff", "image/jpeg"))

        with patch.object(contacts_photos, "read_photo", read):
            answer = await client.get("/workbench/contacts/photo?id=people/c1")

        assert answer.status_code == 200
        assert answer.headers["content-type"] == "image/jpeg"
        assert answer.headers["x-content-type-options"] == "nosniff"
        assert answer.headers["cache-control"] == "no-store"
        assert "sandbox" in answer.headers["content-security-policy"]

    async def test_a_new_one_reaches_the_service_with_its_contact(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        written = AsyncMock()

        with (
            patch.object(contacts_photos, "write_photo", written),
            patch("src.domains.workbench.contacts_router.one_transfer", _held),
        ):
            answer = await client.put(
                "/workbench/contacts/photo",
                data={"id": "people/c1"},
                files={"file": ("me.jpg", b"picture", "image/jpeg")},
            )

        assert answer.status_code == 204
        assert written.await_args.args[1:] == ("people/c1", b"picture")

    async def test_one_past_its_ceiling_is_refused_unread(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        written = AsyncMock()

        with patch.object(contacts_photos, "write_photo", written):
            answer = await client.put(
                "/workbench/contacts/photo",
                data={"id": "people/c1"},
                files={"file": ("me.jpg", b"x" * (WORKBENCH_CONTACT_PHOTO_MAX_BYTES + 1))},
            )

        assert answer.status_code == 413
        written.assert_not_awaited()

    async def test_it_is_taken_off(self, http: tuple[AsyncClient, Any]) -> None:
        client, _ = http
        removed = AsyncMock()

        with patch.object(contacts_photos, "remove_photo", removed):
            answer = await client.delete("/workbench/contacts/photo?id=people/c1")

        assert answer.status_code == 204
        assert removed.await_args.args[1] == "people/c1"


class TestAGroup:
    @pytest.mark.parametrize(
        ("method", "url", "body", "service", "code"),
        [
            ("GET", "/workbench/contacts/member-of?id=people/c1", None, "groups_of", 200),
            (
                "POST",
                "/workbench/contacts/groups/join",
                {"contact_id": "people/c1", "name": "Family"},
                "join_group",
                200,
            ),
            (
                "POST",
                "/workbench/contacts/groups/leave",
                {"contact_id": "people/c1", "group_id": "contactGroups/f"},
                "leave_group",
                204,
            ),
            (
                "PATCH",
                "/workbench/contacts/groups",
                {"id": "contactGroups/f", "name": "Kin"},
                "rename_group",
                204,
            ),
            ("DELETE", "/workbench/contacts/groups?id=contactGroups/f", None, "delete_group", 204),
        ],
    )
    async def test_each_route_reaches_its_act(
        self,
        http: tuple[AsyncClient, Any],
        method: str,
        url: str,
        body: dict[str, Any] | None,
        service: str,
        code: int,
    ) -> None:
        client, _ = http
        answers = {
            "groups_of": ContactGroups(groups=[]),
            "join_group": ContactGroup(id="contactGroups/f", name="Family", count=None),
        }
        act = AsyncMock(return_value=answers.get(service))

        with patch.object(contacts_groups, service, act):
            answer = await client.request(method, url, json=body)

        assert answer.status_code == code
        act.assert_awaited_once()

    async def test_a_name_past_its_bound_asks_nothing_of_anyone(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        act = AsyncMock()

        with patch.object(contacts_groups, "join_group", act):
            answer = await client.post(
                "/workbench/contacts/groups/join",
                json={"contact_id": "people/c1", "name": "x" * 600},
            )

        assert answer.status_code == 422
        act.assert_not_awaited()


class TestAFile:
    async def test_an_export_leaves_as_a_download_the_browser_never_renders(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        exported = AsyncMock(return_value=ContactsFile(b"BEGIN:VCARD", "Ana Lima.vcf"))

        with patch.object(contacts_transfer, "export_contacts", exported):
            answer = await client.get("/workbench/contacts/export?id=people/c1")

        assert answer.status_code == 200
        assert answer.content == b"BEGIN:VCARD"
        assert answer.headers["content-type"].startswith("text/vcard")
        assert "attachment" in answer.headers["content-disposition"]
        assert "sandbox" in answer.headers["content-security-policy"]
        assert exported.await_args.args[1] == "people/c1"

    async def test_an_export_of_the_whole_book_names_no_contact(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        exported = AsyncMock(return_value=ContactsFile(b"", "contacts.vcf"))

        with patch.object(contacts_transfer, "export_contacts", exported):
            await client.get("/workbench/contacts/export")

        assert exported.await_args.args[1] is None

    async def test_an_id_of_the_wrong_shape_asks_nothing_of_anyone(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        exported = AsyncMock()

        with patch.object(contacts_transfer, "export_contacts", exported):
            answer = await client.get("/workbench/contacts/export", params={"id": "a\nb"})

        assert answer.status_code == 422
        exported.assert_not_awaited()

    async def test_an_import_runs_under_its_submission_s_key(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        imported = AsyncMock(return_value=ContactsImported(done=1, failed=[]))

        with (
            patch.object(contacts_transfer, "import_contacts", imported),
            patch("src.domains.workbench.contacts_router.one_transfer", _held),
        ):
            answer = await client.post(
                "/workbench/contacts/import",
                data={"idempotency_key": _KEY},
                files={"file": ("book.vcf", b"BEGIN:VCARD", "text/vcard")},
            )

        assert answer.status_code == 200
        assert answer.json() == {"done": 1, "failed": []}
        assert imported.await_args.args[1] == b"BEGIN:VCARD"
        assert str(imported.await_args.args[2]) == _KEY

    async def test_a_file_past_its_ceiling_is_refused_with_it_unread(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        imported = AsyncMock()

        with patch.object(contacts_transfer, "import_contacts", imported):
            answer = await client.post(
                "/workbench/contacts/import",
                data={"idempotency_key": _KEY},
                files={"file": ("book.vcf", b"x" * (WORKBENCH_CONTACTS_IMPORT_MAX_BYTES + 1))},
            )

        assert answer.status_code == 413
        assert answer.json()["detail"]["max_bytes"] == WORKBENCH_CONTACTS_IMPORT_MAX_BYTES
        imported.assert_not_awaited()

    async def test_an_other_contact_is_saved_under_its_key(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _ = http
        saved = AsyncMock(return_value=_CONTACT)

        with patch.object(contacts_service, "save_other_contact", saved):
            answer = await client.post(
                "/workbench/contacts/other/save",
                json={"id": "otherContacts/c9", "idempotency_key": _KEY},
            )

        assert answer.status_code == 201
        assert saved.await_args.args[1].id == "otherContacts/c9"


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
