"""The files routes at the door (ADR-369, Task 8.1).

Each route reaches its service for the signed-in account under its window —
reads, downloads and acts apart, a selection of several charged as a bulk act.
A file leaves as a DOWNLOAD the browser never renders: sandboxed, kept by no
cache, its name and its type made safe — both are the Drive owner's. An id of
the wrong shape, a search inside a folder or a format nobody offers asks
nothing of anyone.
"""

from __future__ import annotations

import contextlib
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
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.attachments.preview import DocumentPreview
from src.domains.workbench import (
    files_organize,
    files_preview,
    files_router,
    files_service,
    files_sharing,
    files_text,
)
from src.domains.workbench import router as router_module
from src.domains.workbench.errors import TOO_LARGE
from src.domains.workbench.files_service import DriveDownload
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.files import (
    DownloadQuery,
    DriveItem,
    DriveQuota,
    FileCopied,
    FileDetail,
    FileSharing,
    FilesPage,
    FileText,
    SharedLink,
)

pytestmark = pytest.mark.unit

_KEY = str(uuid4())

_DETAIL = FileDetail(
    id="f1",
    name="Budget",
    kind="file",
    mime_type="application/pdf",
    modified_at=None,
    size=3,
    web_url=None,
    target_id=None,
    target_kind=None,
    formats=[],
    downloadable=True,
    owners=[],
    description=None,
    created_at=None,
    ancestors=[],
    in_my_drive=True,
    ancestors_truncated=False,
)
_SERVICES: dict[str, Any] = {
    "read_quota": DriveQuota(used=1, total=2),
    "list_files": FilesPage(items=[], next_page_token=None),
    "read_file": _DETAIL,
    "download_file": DriveDownload(
        data=b"%PDF", filename="Budget 2026 « final ».pdf", mime_type="application/pdf"
    ),
    "trash_files": ActOutcome(done=["f1"], failed=[]),
}
_ITEM = DriveItem(**_DETAIL.model_dump(include=set(DriveItem.model_fields)))
_ACTS: dict[str, Any] = {
    "save_mail_attachment": _ITEM,
    "restore_files": ActOutcome(done=["f1"], failed=[]),
    "delete_files": ActOutcome(done=["f1"], failed=[]),
    "empty_trash": None,
    "star_file": _ITEM,
    "upload_file": _ITEM,
    "create_folder": _ITEM,
    "rename_file": _ITEM,
    "move_files": ActOutcome(done=["f1"], failed=[]),
    "copy_file": FileCopied(item=None),
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
    acts = {name: AsyncMock(return_value=value) for name, value in _ACTS.items()}
    transfers: list[Any] = []

    @contextlib.asynccontextmanager
    async def one_transfer(user_id: Any) -> AsyncIterator[None]:
        transfers.append(user_id)
        yield

    with (
        patch.multiple(files_service, **services),
        patch.multiple(files_organize, **acts),
        patch.object(files_router, "one_transfer", one_transfer),
    ):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(
                limiter=limiter, user=user, transfers=transfers, **services, **acts
            )


_ROUTES = [
    ("GET", "/workbench/files?folder_id=d0", None, "list_files", 200, ["workbench_read"]),
    (
        "GET",
        "/workbench/files?q=budget&full_text=true",
        None,
        "list_files",
        200,
        ["workbench_read"],
    ),
    ("GET", "/workbench/files/file?id=f1", None, "read_file", 200, ["workbench_read"]),
    (
        "GET",
        "/workbench/files/download?id=f1",
        None,
        "download_file",
        200,
        ["workbench_download"],
    ),
    (
        "POST",
        "/workbench/files/trash",
        {"file_ids": ["f1"]},
        "trash_files",
        200,
        ["workbench_write"],
    ),
    (
        "POST",
        "/workbench/files/trash",
        {"file_ids": ["f1", "f2"]},
        "trash_files",
        200,
        ["workbench_bulk"],
    ),
    (
        "POST",
        "/workbench/files/folders",
        {"name": "Trips", "folder_id": "d1", "idempotency_key": _KEY},
        "create_folder",
        201,
        ["workbench_write"],
    ),
    ("GET", "/workbench/files?view=recent", None, "list_files", 200, ["workbench_read"]),
    ("GET", "/workbench/files?view=drives", None, "list_files", 200, ["workbench_read"]),
    ("GET", "/workbench/files/quota", None, "read_quota", 200, ["workbench_read"]),
    (
        "POST",
        "/workbench/files/from-mail",
        {"message_id": "m1", "filename": "a.pdf", "idempotency_key": _KEY},
        "save_mail_attachment",
        201,
        ["workbench_write"],
    ),
    ("GET", "/workbench/files?view=trash", None, "list_files", 200, ["workbench_read"]),
    (
        "POST",
        "/workbench/files/restore",
        {"file_ids": ["f1"]},
        "restore_files",
        200,
        ["workbench_write"],
    ),
    (
        "POST",
        "/workbench/files/restore",
        {"file_ids": ["f1", "f2"]},
        "restore_files",
        200,
        ["workbench_bulk"],
    ),
    (
        "POST",
        "/workbench/files/delete",
        {"file_ids": ["f1"]},
        "delete_files",
        200,
        ["workbench_write"],
    ),
    (
        "POST",
        "/workbench/files/delete",
        {"file_ids": ["f1", "f2"]},
        "delete_files",
        200,
        ["workbench_bulk"],
    ),
    ("POST", "/workbench/files/trash/empty", None, "empty_trash", 204, ["workbench_write"]),
    (
        "PATCH",
        "/workbench/files/star",
        {"file_id": "f1", "starred": True},
        "star_file",
        200,
        ["workbench_write"],
    ),
    (
        "PATCH",
        "/workbench/files/file",
        {"file_id": "f1", "name": "Report.pdf"},
        "rename_file",
        200,
        ["workbench_write"],
    ),
    (
        "POST",
        "/workbench/files/move",
        {"file_ids": ["f1"], "folder_id": "d1"},
        "move_files",
        200,
        ["workbench_write"],
    ),
    (
        "POST",
        "/workbench/files/move",
        {"file_ids": ["f1", "f2"]},
        "move_files",
        200,
        ["workbench_bulk"],
    ),
    (
        "POST",
        "/workbench/files/copy",
        {"file_id": "f1", "idempotency_key": _KEY},
        "copy_file",
        200,
        ["workbench_write"],
    ),
]


@pytest.mark.parametrize(("method", "url", "body", "service", "status", "windows"), _ROUTES)
async def test_each_route_reaches_its_service_under_its_window(
    http: Any,
    method: str,
    url: str,
    body: dict[str, Any] | None,
    service: str,
    status: int,
    windows: list[str],
) -> None:
    client, seams = http

    response = await client.request(method, url, json=body)

    assert response.status_code == status, response.text
    called = getattr(seams, service)
    called.assert_awaited_once()
    assert called.await_args.args[0] == seams.user.id
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == windows


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("POST", "/workbench/files/folders", {"name": "a/b", "idempotency_key": _KEY}),
        ("POST", "/workbench/files/folders", {"name": "Trips"}),
        ("PATCH", "/workbench/files/file", {"file_id": "f1", "name": "   "}),
        ("PATCH", "/workbench/files/file", {"file_id": "a b", "name": "x"}),
        ("POST", "/workbench/files/move", {"file_ids": []}),
        ("POST", "/workbench/files/copy", {"file_id": "f1"}),
        (
            "POST",
            "/workbench/files/copy",
            {"file_id": "f1", "name": "a\\b", "idempotency_key": _KEY},
        ),
    ],
)
async def test_a_request_that_cannot_be_acted_on_asks_nothing(
    http: Any, method: str, url: str, body: dict[str, Any]
) -> None:
    client, seams = http

    response = await client.request(method, url, json=body)

    assert response.status_code == 422, response.text
    for act in _ACTS:
        getattr(seams, act).assert_not_awaited()


def _upload_form(**fields: str) -> dict[str, Any]:
    return {
        "data": {"name": "Notes.txt", "idempotency_key": _KEY, **fields},
        "files": {"file": ("whatever.bin", b"data", "text/plain")},
    }


async def test_a_file_reaches_its_act_under_the_write_window(http: Any) -> None:
    client, seams = http

    response = await client.post("/workbench/files/upload", **_upload_form(folder_id="d1"))

    assert response.status_code == 201, response.text
    user_id, upload = seams.upload_file.await_args.args
    assert user_id == seams.user.id
    assert (upload.name, upload.data, upload.mime_type, upload.folder_id) == (
        "Notes.txt",
        b"data",
        "text/plain",
        "d1",
    )
    assert str(upload.key) == _KEY
    assert seams.transfers == [seams.user.id]
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == ["workbench_write"]


async def test_a_file_past_the_ceiling_sends_nothing_and_quotes_it(
    http: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, seams = http
    monkeypatch.setattr(settings, "workbench_upload_max_bytes", 3)

    response = await client.post("/workbench/files/upload", **_upload_form())

    assert response.status_code == 413, response.text
    assert response.json()["detail"]["code"] == TOO_LARGE
    assert response.json()["detail"]["max_bytes"] == 3
    seams.upload_file.assert_not_awaited()


async def test_a_file_at_the_ceiling_goes(http: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, seams = http
    monkeypatch.setattr(settings, "workbench_upload_max_bytes", 4)

    response = await client.post("/workbench/files/upload", **_upload_form())

    assert response.status_code == 201, response.text


async def test_a_type_nobody_can_serve_is_sent_opaque(http: Any) -> None:
    client, seams = http
    form = _upload_form()
    form["files"] = {"file": ("x", b"data", "text/html; evil")}

    await client.post("/workbench/files/upload", **form)

    assert seams.upload_file.await_args.args[1].mime_type == "application/octet-stream"


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "a/b"},
        {"name": "   "},
        {"idempotency_key": "not-a-uuid"},
        {"folder_id": "a b"},
    ],
)
async def test_an_upload_that_cannot_be_acted_on_asks_nothing(
    http: Any, fields: dict[str, str]
) -> None:
    client, seams = http

    response = await client.post("/workbench/files/upload", **_upload_form(**fields))

    assert response.status_code == 422, response.text
    seams.upload_file.assert_not_awaited()


async def test_a_preview_is_read_under_the_read_window_and_never_kept(http: Any) -> None:
    client, seams = http
    shown = DocumentPreview(b"text", "text/plain", True)

    with patch.object(files_preview, "preview_file", AsyncMock(return_value=shown)) as preview:
        response = await client.get("/workbench/files/preview", params={"id": "f1"})

    assert response.status_code == 200, response.text
    preview.assert_awaited_once_with(seams.user.id, "f1")
    assert response.content == b"text"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-preview-truncated"] == "true"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == ["workbench_read"]


async def test_a_text_is_read_with_its_version(http: Any) -> None:
    client, seams = http
    read = FileText(text="Hello", tag="tag-1")

    with patch.object(files_text, "read_text", AsyncMock(return_value=read)) as reading:
        response = await client.get("/workbench/files/text", params={"id": "f1"})

    assert response.status_code == 200
    reading.assert_awaited_once_with(seams.user.id, "f1")
    assert response.json() == {"text": "Hello", "tag": "tag-1"}


async def test_a_text_is_written_on_its_version(http: Any) -> None:
    client, seams = http
    body = {"id": "f1", "text": "Bye", "tag": "tag-1"}

    with patch.object(files_text, "write_text", AsyncMock(return_value=_ITEM)) as writing:
        response = await client.put("/workbench/files/text", json=body)

    assert response.status_code == 200
    assert writing.await_args.args[0] == seams.user.id
    assert writing.await_args.args[1].tag == "tag-1"
    assert response.json()["id"] == _ITEM.id


async def test_a_text_with_no_version_asks_nothing(http: Any) -> None:
    client, _ = http

    with patch.object(files_text, "write_text", AsyncMock()) as writing:
        response = await client.put("/workbench/files/text", json={"id": "f1", "text": "Bye"})

    assert response.status_code == 422
    writing.assert_not_awaited()


async def test_a_preview_of_a_malformed_id_asks_nothing(http: Any) -> None:
    client, _seams = http

    with patch.object(files_preview, "preview_file", AsyncMock()) as preview:
        response = await client.get("/workbench/files/preview", params={"id": "a b"})

    assert response.status_code == 422, response.text
    preview.assert_not_awaited()


@pytest.fixture
def sharing() -> Any:
    answers = {
        "read_sharing": AsyncMock(return_value=FileSharing(people=[], link=None)),
        "share_file": AsyncMock(return_value=None),
        "open_link": AsyncMock(return_value=SharedLink(id="l1", url="https://d.example/f1")),
        "remove_share": AsyncMock(return_value=None),
    }
    with patch.multiple(files_sharing, **answers):
        yield SimpleNamespace(**answers)


@pytest.mark.parametrize(
    ("method", "url", "body", "act", "status", "window"),
    [
        ("GET", "/workbench/files/sharing?id=f1", None, "read_sharing", 200, "workbench_read"),
        (
            "POST",
            "/workbench/files/sharing",
            {"file_id": "f1", "email": "a@x.org", "role": "reader", "idempotency_key": _KEY},
            "share_file",
            204,
            "workbench_write",
        ),
        (
            "POST",
            "/workbench/files/sharing/link",
            {"file_id": "f1"},
            "open_link",
            200,
            "workbench_write",
        ),
        (
            "POST",
            "/workbench/files/sharing/remove",
            {"file_id": "f1", "permission_id": "p1"},
            "remove_share",
            204,
            "workbench_write",
        ),
    ],
)
async def test_each_sharing_route_reaches_its_act_under_its_window(
    http: Any,
    sharing: Any,
    method: str,
    url: str,
    body: dict[str, Any] | None,
    act: str,
    status: int,
    window: str,
) -> None:
    client, seams = http

    response = await client.request(method, url, json=body)

    assert response.status_code == status, response.text
    called = getattr(sharing, act)
    called.assert_awaited_once()
    assert called.await_args.args[0] == seams.user.id
    keys = [call.kwargs["key"] for call in seams.limiter.acquire.await_args_list]
    assert [key.split(":")[1] for key in keys] == [window]


async def test_a_file_leaves_as_a_download_never_rendered(http: Any) -> None:
    client, seams = http

    response = await client.get("/workbench/files/download", params={"id": "f1", "format": "pdf"})

    assert response.status_code == 200, response.text
    assert response.content == b"%PDF"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="Budget 2026  final .pdf"; '
        "filename*=UTF-8''Budget%202026%20%C2%AB%20final%20%C2%BB.pdf"
    )
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["cache-control"] == "no-store"
    assert seams.download_file.await_args.args[1] == DownloadQuery(id="f1", format="pdf")


async def test_a_type_that_is_none_is_served_opaque(http: Any) -> None:
    client, seams = http
    seams.download_file.return_value = DriveDownload(
        data=b"<b>", filename="x", mime_type="text/html; evil"
    )

    response = await client.get("/workbench/files/download", params={"id": "f1"})

    assert response.headers["content-type"] == "application/octet-stream"


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("GET", "/workbench/files/file?id=a%20b", None),
        ("GET", "/workbench/files?q=budget&folder_id=d0", None),
        ("GET", "/workbench/files/download?id=f1&format=odt", None),
        ("GET", "/workbench/files/download", None),
        ("POST", "/workbench/files/trash", {"file_ids": []}),
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
