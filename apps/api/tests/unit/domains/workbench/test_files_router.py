"""The files routes at the door (ADR-369, Task 8.1).

Each route reaches its service for the signed-in account under its window —
reads, downloads and acts apart, a selection of several charged as a bulk act.
A file leaves as a DOWNLOAD the browser never renders: sandboxed, kept by no
cache, its name and its type made safe — both are the Drive owner's. An id of
the wrong shape, a search inside a folder or a format nobody offers asks
nothing of anyone.
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

from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.workbench import files_service
from src.domains.workbench import router as router_module
from src.domains.workbench.files_service import DriveDownload
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.files import DownloadQuery, FileDetail, FilesPage

pytestmark = pytest.mark.unit

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
    "list_files": FilesPage(items=[], next_page_token=None),
    "read_file": _DETAIL,
    "download_file": DriveDownload(
        data=b"%PDF", filename="Budget 2026 « final ».pdf", mime_type="application/pdf"
    ),
    "trash_files": ActOutcome(done=["f1"], failed=[]),
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
    with patch.multiple(files_service, **services):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield client, SimpleNamespace(limiter=limiter, user=user, **services)


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
