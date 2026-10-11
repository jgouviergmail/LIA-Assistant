"""Download doors preserve finite refusals, dependency failures and non-cacheable responses."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from src.core.exceptions import BaseAPIException
from src.domains.agents.application import command_router
from src.domains.agents.application.command_service import CommandRejected
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "door,handler",
    [
        ("download_application_export", "serve_export_download_command"),
        ("download_management_export", "serve_management_export_command"),
        ("download_knowledge_document", "serve_document_download_command"),
        ("download_knowledge_archive", "serve_document_archive_command"),
    ],
)
@pytest.mark.parametrize(
    "error,status,code",
    [
        (CommandRejected("EXPIRED"), 409, "EXPIRED"),
        (OSError("private storage diagnostic"), 503, "DEPENDENCY_ERROR"),
        (ValueError("private validation diagnostic"), 422, "INVALID_INPUT"),
    ],
)
async def test_download_http_refusal_is_classified_without_leaking_source_diagnostics(
    monkeypatch, door, handler, error, status, code
):
    monkeypatch.setattr(command_router, handler, AsyncMock(side_effect=error))
    request = Request({"type": "http", "headers": []})
    with pytest.raises(BaseAPIException) as refusal:
        await getattr(command_router, door)(uuid4(), request, User(id=uuid4()), object())
    assert refusal.value.status_code == status and refusal.value.detail == {"error_code": code}
    assert refusal.value.headers["Cache-Control"] == "no-store"
