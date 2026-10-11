"""Native download transport binds the actual cookie and never leaks dependency details."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import AuthorizationError
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.export_download_response import ExportDownloadResponse
from src.domains.users.models import User
from src.infrastructure.account_export_downloads import (
    ExportArchiveSnapshot,
    ExportDownloadCompletionUnknown,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("case", ["valid", "forbidden", "sql", "redis", "unknown"])
@pytest.mark.parametrize(
    "endpoint", ["download", "management-export", "document-download", "document-archive"]
)
async def test_download_http_binds_cookie_streams_archive_and_redacts_failures(
    monkeypatch: pytest.MonkeyPatch, case: str, endpoint: str
) -> None:
    module = import_module("src.domains.agents.application.command_router")
    monkeypatch.setattr(settings, "session_cookie_name", "custom-session")
    actor, command_id = User(id=uuid4(), is_active=True), uuid4()
    now = datetime.now(UTC)
    reader = Mock()
    reader.snapshot = ExportArchiveSnapshot(
        job_id=uuid4(),
        created_at=now,
        completed_at=now,
        expires_at=now + timedelta(minutes=5),
        file_size_bytes=4,
        archive_digest="d" * 64,
    )
    reader.read_chunk = AsyncMock(side_effect=[b"data", b""])
    reader.close = AsyncMock()
    runner = AsyncMock(return_value=ExportDownloadResponse(reader))
    failures = {
        "forbidden": AuthorizationError(detail={"error_code": "FORBIDDEN"}),
        "sql": SQLAlchemyError("private-cookie private-archive-path"),
        "redis": RedisError("private-cookie private-archive-path"),
        "unknown": ExportDownloadCompletionUnknown("private-cookie private-archive-path"),
    }
    if case in failures:
        runner.side_effect = failures[case]
    origin = object()
    binding = Mock(return_value=origin)
    monkeypatch.setattr(
        module,
        {
            "download": "serve_export_download_command",
            "management-export": "serve_management_export_command",
            "document-download": "serve_document_download_command",
            "document-archive": "serve_document_archive_command",
        }[endpoint],
        runner,
        raising=False,
    )
    monkeypatch.setattr(module, "bind_browser_session", binding)
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: "request-db"
    app.dependency_overrides[get_current_active_session] = lambda: actor
    app.dependency_overrides[module.rate_limit_command_resume] = lambda: None
    # Generating the contract must work for this custom streaming response too.
    assert app.openapi()["paths"][f"/application-commands/{{command_id}}/{endpoint}"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"custom-session": "private-cookie"},
    ) as client:
        response = await client.get(f"/application-commands/{command_id}/{endpoint}")
    binding.assert_called_once_with(actor.id, "private-cookie")
    runner.assert_awaited_once_with("request-db", actor.id, command_id, origin)
    assert response.headers["cache-control"] == "no-store"
    assert "private-cookie" not in response.text and "private-archive-path" not in response.text
    if case == "valid":
        assert response.status_code == 200 and response.content == b"data"
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["content-length"] == "4"
        assert response.headers["content-disposition"].startswith("attachment;")
        reader.close.assert_awaited_once()
    else:
        assert response.status_code == (403 if case == "forbidden" else 503)
        assert response.json()["detail"]["error_code"] == (
            "FORBIDDEN"
            if case == "forbidden"
            else "COMPLETION_UNKNOWN" if case == "unknown" else "DEPENDENCY_ERROR"
        )
        reader.read_chunk.assert_not_awaited()
