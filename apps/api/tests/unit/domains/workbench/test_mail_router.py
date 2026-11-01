"""The mail routes at the door (ADR-369, Tasks 4.1-4.2).

Each route reaches its service for the signed-in account under its window —
reads apart from writes, and an act on a selection in the bulk window only
when it carries more than one message (filing messages one by one is not a
bulk act). An id of the wrong shape, or a selection above the published bound,
is refused before any provider is asked; a refusal leaves with its code.
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

from src.core.config import settings
from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.workbench import (
    mail_acts,
    mail_attachments,
    mail_compose,
    mail_drafts,
    mail_folders,
    mail_reading,
    mail_settings,
)
from src.domains.workbench import router as router_module
from src.domains.workbench.errors import NAME_TAKEN, refuse
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.mail import (
    AttachmentRequest,
    MailFolder,
    MailFolders,
    MailHtml,
    MailListing,
    MailMessage,
    MailPage,
)
from src.domains.workbench.schemas.mail_compose import (
    DraftsPage,
    MailDraft,
    SentMessage,
)
from src.domains.workbench.schemas.mail_settings import MailFilter, MailFilters, Vacation

pytestmark = pytest.mark.unit

_LABEL = MailFolder(id="Label_1", kind="user", role=None, name="Travel")
_SERVICES: dict[str, Any] = {
    "read_folders": MailFolders(folders=[_LABEL]),
    "create_label": _LABEL,
    "rename_label": _LABEL,
    "delete_label": None,
    "apply_labels": None,
}
_READS: dict[str, Any] = {
    "list_messages": MailPage(items=[], next_page_token=None, skipped=0),
    "read_message": MailMessage(
        id="m1",
        thread_id="t1",
        sender=None,
        reply_to=[],
        to=[],
        cc=[],
        subject="",
        received_at=None,
        is_read=True,
        is_starred=False,
        label_ids=[],
        body="",
        attachments=[],
    ),
    "read_message_html": MailHtml(html="<p>Hello</p>", truncated=False),
}
_ACTS: dict[str, Any] = {
    "set_read_state": ActOutcome(done=["m1"], failed=[]),
    "trash_messages": ActOutcome(done=["m1"], failed=[]),
}
_PDF = EmailAttachmentContent(filename="budget.pdf", mime_type="application/pdf", data=b"%PDF")
_SENT = SentMessage(id="s1", thread_id="t1")
_SENDS: dict[str, Any] = {"send_message": _SENT, "reply": _SENT, "forward": _SENT}
_DRAFT = MailDraft(
    id="d1",
    revision="r1",
    to=[],
    cc=[],
    bcc=[],
    subject="",
    body="",
    attachments=[],
    updated_at=None,
)
_VACATION = Vacation(enabled=False, subject="", body="", start_date=None, end_date=None)
_FILTER = MailFilter(
    id="f1",
    sender="a@example.org",
    recipient=None,
    subject=None,
    query=None,
    has_attachment=False,
    add_label_ids=[],
    archive=True,
    mark_read=False,
    forward=None,
)
_SETTINGS: dict[str, Any] = {
    "read_vacation": _VACATION,
    "set_vacation": _VACATION,
    "list_filters": MailFilters(filters=[_FILTER]),
    "create_filter": _FILTER,
}
_DRAFTS: dict[str, Any] = {
    "list_drafts": DraftsPage(items=[], next_page_token=None),
    "read_draft": _DRAFT,
    "save_draft": _DRAFT,
    "send_draft": _SENT,
    "trash_drafts": ActOutcome(done=["d1"], failed=[]),
}
_KEY = "11111111-1111-4111-8111-111111111111"


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
    user = SimpleNamespace(id=uuid4(), timezone="Europe/Paris")
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: user
    services = {name: AsyncMock(return_value=value) for name, value in _SERVICES.items()}
    reads = {name: AsyncMock(return_value=value) for name, value in _READS.items()}
    acts = {name: AsyncMock(return_value=value) for name, value in _ACTS.items()}
    sends = {name: AsyncMock(return_value=value) for name, value in _SENDS.items()}
    drafts = {name: AsyncMock(return_value=value) for name, value in _DRAFTS.items()}
    settings_ = {name: AsyncMock(return_value=value) for name, value in _SETTINGS.items()}
    download = AsyncMock(return_value=_PDF)
    with (
        patch.multiple(mail_folders, **services),
        patch.multiple(mail_reading, **reads),
        patch.multiple(mail_acts, **acts),
        patch.multiple(mail_compose, **sends),
        patch.multiple(mail_drafts, **drafts),
        patch.multiple(mail_settings, **settings_),
        patch.object(mail_attachments, "download_attachment", download),
    ):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(
                limiter=limiter,
                user=user,
                download_attachment=download,
                **services,
                **reads,
                **acts,
                **sends,
                **drafts,
                **settings_,
            )


_ROUTES: list[tuple[str, str, dict[str, Any] | None, str, int, str]] = [
    (
        "POST",
        "/workbench/mail/send",
        {"to": ["ana@example.org"], "subject": "s", "body": "b", "idempotency_key": _KEY},
        "send_message",
        200,
        "workbench_send",
    ),
    (
        "POST",
        "/workbench/mail/reply",
        {"message_id": "m1", "body": "b", "idempotency_key": _KEY},
        "reply",
        200,
        "workbench_send",
    ),
    (
        "POST",
        "/workbench/mail/forward",
        {"message_id": "m1", "to": ["dan@example.org"], "idempotency_key": _KEY},
        "forward",
        200,
        "workbench_send",
    ),
    ("GET", "/workbench/mail/drafts", None, "list_drafts", 200, "workbench_read"),
    ("GET", "/workbench/mail/draft?id=d1", None, "read_draft", 200, "workbench_read"),
    (
        "POST",
        "/workbench/mail/drafts",
        {"subject": "s", "idempotency_key": _KEY},
        "save_draft",
        200,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/mail/drafts/send",
        {"draft_id": "d1", "expected_revision": "r1", "idempotency_key": _KEY},
        "send_draft",
        200,
        "workbench_send",
    ),
    (
        "POST",
        "/workbench/mail/drafts/trash",
        {"draft_ids": ["d1", "d2"]},
        "trash_drafts",
        200,
        "workbench_bulk",
    ),
    ("GET", "/workbench/mail/vacation", None, "read_vacation", 200, "workbench_read"),
    ("PUT", "/workbench/mail/vacation", {"enabled": False}, "set_vacation", 200, "workbench_write"),
    ("GET", "/workbench/mail/filters", None, "list_filters", 200, "workbench_read"),
    (
        "POST",
        "/workbench/mail/filters",
        {"sender": "a@example.org", "archive": True, "idempotency_key": _KEY},
        "create_filter",
        201,
        "workbench_write",
    ),
    ("GET", "/workbench/mail/folders", None, "read_folders", 200, "workbench_read"),
    ("GET", "/workbench/mail/messages", None, "list_messages", 200, "workbench_read"),
    ("GET", "/workbench/mail/message?id=m1", None, "read_message", 200, "workbench_read"),
    (
        "GET",
        "/workbench/mail/message/html?id=m1",
        None,
        "read_message_html",
        200,
        "workbench_read",
    ),
    ("POST", "/workbench/mail/labels", {"name": "Travel"}, "create_label", 201, "workbench_write"),
    (
        "PATCH",
        "/workbench/mail/labels",
        {"label_id": "Label_1", "name": "Trips"},
        "rename_label",
        200,
        "workbench_write",
    ),
    (
        "DELETE",
        "/workbench/mail/labels?label_id=Label_1",
        None,
        "delete_label",
        204,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/mail/labels/apply",
        {"message_ids": ["m1"], "add": ["Label_1"]},
        "apply_labels",
        204,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/mail/labels/apply",
        {"message_ids": ["m1", "m2"], "remove": ["Label_1"]},
        "apply_labels",
        204,
        "workbench_bulk",
    ),
    (
        "POST",
        "/workbench/mail/read-state",
        {"message_ids": ["m1"], "read": True},
        "set_read_state",
        200,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/mail/read-state",
        {"message_ids": ["m1", "m2"], "read": False},
        "set_read_state",
        200,
        "workbench_bulk",
    ),
    (
        "POST",
        "/workbench/mail/trash",
        {"message_ids": ["m1"]},
        "trash_messages",
        200,
        "workbench_write",
    ),
    (
        "POST",
        "/workbench/mail/trash",
        {"message_ids": ["m1", "m2", "m3"]},
        "trash_messages",
        200,
        "workbench_bulk",
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

    response = await client.request(method, url, json=body)

    assert response.status_code == status, response.text
    called = getattr(seams, service)
    called.assert_awaited_once()
    assert called.await_args.args[0] == seams.user.id
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == [window]


async def test_the_pane_answers_its_folders(http: Any) -> None:
    client, _ = http
    body = (await client.get("/workbench/mail/folders")).json()
    assert body == {"folders": [{"id": "Label_1", "kind": "user", "role": None, "name": "Travel"}]}


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("DELETE", "/workbench/mail/labels?label_id=a%20b", None),
        ("PATCH", "/workbench/mail/labels", {"label_id": "x" * 1025, "name": "n"}),
        ("POST", "/workbench/mail/labels/apply", {"message_ids": ["m 1"], "add": ["Label_1"]}),
    ],
)
async def test_an_id_of_the_wrong_shape_asks_nothing(
    http: Any, method: str, url: str, body: dict[str, Any] | None
) -> None:
    client, seams = http

    response = await client.request(method, url, json=body)

    assert response.status_code == 422
    for service in _SERVICES:
        getattr(seams, service).assert_not_awaited()


async def test_a_selection_above_the_published_bound_asks_nothing(http: Any) -> None:
    client, seams = http
    ids = [f"m{index}" for index in range(settings.workbench_bulk_max_items + 1)]

    response = await client.post(
        "/workbench/mail/labels/apply", json={"message_ids": ids, "add": ["Label_1"]}
    )

    assert response.status_code == 422
    seams.apply_labels.assert_not_awaited()


async def test_a_refusal_leaves_with_its_code(http: Any) -> None:
    client, seams = http

    async def taken(*_: Any, **__: Any) -> None:
        refuse(NAME_TAKEN)

    seams.create_label.side_effect = taken
    response = await client.post("/workbench/mail/labels", json={"name": "Travel"})

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "name_taken"}}


async def test_a_listing_reads_its_folder_words_and_chips_in_the_account_s_zone(
    http: Any,
) -> None:
    from zoneinfo import ZoneInfo

    client, seams = http
    response = await client.get(
        "/workbench/mail/messages",
        params={
            "folder": "system:sent",
            "q": "from:ana",
            "unread": "true",
            "after": "2026-10-01",
            "page_token": "p2",
        },
    )

    assert response.status_code == 200, response.text
    user_id, zone, listing = seams.list_messages.await_args.args
    assert (user_id, zone) == (seams.user.id, ZoneInfo("Europe/Paris"))
    assert listing == MailListing(
        folder="system:sent", q="from:ana", unread=True, after="2026-10-01", page_token="p2"
    )


@pytest.mark.parametrize(
    "params",
    [
        {"q": "w" * (WORKBENCH_MAIL_QUERY_MAX_CHARS + 1)},
        {"after": "2026-10-08", "before": "2026-10-01"},
        {"folder": "a\nb"},
        {"unknown": "1"},
    ],
)
async def test_a_listing_of_the_wrong_shape_asks_nothing(http: Any, params: dict[str, str]) -> None:
    client, seams = http
    response = await client.get("/workbench/mail/messages", params=params)
    assert response.status_code == 422
    seams.list_messages.assert_not_awaited()


async def test_a_message_id_of_the_wrong_shape_asks_nothing(http: Any) -> None:
    client, seams = http
    response = await client.get("/workbench/mail/message", params={"id": "a b"})
    assert response.status_code == 422
    seams.read_message.assert_not_awaited()


async def test_a_message_s_html_is_answered_with_its_cut_and_an_odd_id_asks_nothing(
    http: Any,
) -> None:
    client, seams = http

    response = await client.get("/workbench/mail/message/html", params={"id": "m1"})
    refused = await client.get("/workbench/mail/message/html", params={"id": "a b"})

    assert response.json() == {"html": "<p>Hello</p>", "truncated": False}
    seams.read_message_html.assert_awaited_once_with(seams.user.id, "m1")
    assert refused.status_code == 422


async def test_an_attachment_is_downloaded_never_rendered(http: Any) -> None:
    """Served as a download, sandboxed, never kept by a cache, its name made safe."""
    client, seams = http
    asked = {"message_id": "m1", "attachment_id": "ANGj", "filename": "budget.pdf"}

    response = await client.get("/workbench/mail/attachment", params=asked)

    assert response.status_code == 200, response.text
    assert response.content == b"%PDF"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        "attachment; filename=\"budget.pdf\"; filename*=UTF-8''budget.pdf"
    )
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["cache-control"] == "no-store"
    assert seams.download_attachment.await_args.args == (
        seams.user.id,
        AttachmentRequest(**asked),
    )
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == ["workbench_download"]


async def test_a_declared_type_that_is_none_is_served_opaque(http: Any) -> None:
    client, seams = http
    seams.download_attachment.return_value = EmailAttachmentContent(
        filename="x", mime_type="text/html; evil", data=b"<b>"
    )
    response = await client.get(
        "/workbench/mail/attachment", params={"message_id": "m1", "filename": "x"}
    )
    assert response.headers["content-type"] == "application/octet-stream"


async def test_an_attachment_named_by_nothing_asks_nothing(http: Any) -> None:
    client, seams = http
    response = await client.get("/workbench/mail/attachment", params={"message_id": "m1"})
    assert response.status_code == 422
    seams.download_attachment.assert_not_awaited()


async def test_recipients_are_suggested_from_the_book_and_never_filed(http: Any) -> None:
    """The person typing in their own composer is not LIA reading (D5)."""
    from src.domains.email_share import recipients as share_recipients
    from src.domains.email_share.recipient_match import RecipientSuggestion
    from src.domains.email_share.recipients import RecipientSuggestions

    client, seams = http
    found = RecipientSuggestions(
        query="jea",
        suggestions=[RecipientSuggestion(name="Jean", email="jean@example.org")],
        truncated=False,
    )
    with patch.object(
        share_recipients, "suggest_recipients", AsyncMock(return_value=found)
    ) as asked:
        response = await client.get("/workbench/mail/recipients", params={"q": "jea"})

    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == [{"name": "Jean", "email": "jean@example.org"}]
    asked.assert_awaited_once_with(seams.user.id, "jea", recorded=False)
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == ["workbench_read"]


async def test_the_person_s_attachable_files_are_listed(http: Any) -> None:
    from src.domains.workbench import mail_files
    from src.domains.workbench.schemas.mail_compose import AttachablePage

    client, seams = http
    page = AttachablePage(items=[], total=0, next_offset=None)
    with patch.object(mail_files, "list_attachable", AsyncMock(return_value=page)) as listed:
        response = await client.get("/workbench/mail/attachable", params={"q": "rap", "offset": 25})
        refused = await client.get("/workbench/mail/attachable", params={"offset": -1})

    assert response.status_code == 200, response.text
    listed.assert_awaited_once_with(seams.user.id, query="rap", offset=25)
    assert refused.status_code == 422
