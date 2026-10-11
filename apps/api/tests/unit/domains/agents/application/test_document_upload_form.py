"""Multipart failures remain finite native errors after authority, with no leaking detail."""

import pytest
from starlette.requests import Request

from src.core.config import settings
from src.domains.agents.application.document_upload_form import parse_document_upload_form

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("count", [1, 2])
async def test_native_multipart_accepts_one_file_and_classifies_extra_files(count):
    boundary = b"native-test-boundary"
    parts = b"".join(
        b"--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="file"; filename="controlled.txt"\r\nContent-Type: text/plain\r\n\r\ndata\r\n'
        for _ in range(count)
    )
    body = parts + b"--" + boundary + b"--\r\n"

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"content-type", b"multipart/form-data; boundary=" + boundary),
            ],
        },
        receive,
    )
    if count == 2:
        with pytest.raises(ValueError, match="Invalid upload body"):
            async with parse_document_upload_form(request):
                pytest.fail("An extra file cannot reach upload execution")
    else:
        async with parse_document_upload_form(request) as data:
            selected = data["file"]
            assert await selected.read() == b"data"
        assert selected.file.closed


@pytest.mark.parametrize("declared", [False, True])
@pytest.mark.parametrize("skill_limit", [False, True])
async def test_native_multipart_bounds_declared_and_streamed_body_before_spooling(
    monkeypatch, declared, skill_limit
):
    monkeypatch.setattr(settings, "rag_spaces_max_file_size_mb", 1)
    maximum = (
        164 * 1024 if skill_limit else (settings.rag_spaces_max_file_size_mb + 1) * 1024 * 1024
    )
    received = 0
    body = (
        b'--bounded\r\nContent-Disposition: form-data; name="file"; filename="large.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n" + b"x" * maximum + b"\r\n--bounded--\r\n"
    )

    async def receive():
        nonlocal received
        received += 1
        return {"type": "http.request", "body": body, "more_body": False}

    headers = [(b"content-type", b"multipart/form-data; boundary=bounded")]
    if declared:
        headers.append((b"content-length", str(len(body)).encode()))
    request = Request({"type": "http", "method": "POST", "headers": headers}, receive)
    with pytest.raises(ValueError, match="Invalid upload body"):
        async with parse_document_upload_form(
            request, max_body_bytes=maximum if skill_limit else None
        ):
            pytest.fail("Oversized multipart data cannot reach upload execution")
    assert received == (0 if declared else 1)
