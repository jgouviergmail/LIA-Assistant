"""Parse only after the native caller claimed consent; close files and classify framing errors."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.datastructures import FormData
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.requests import ClientDisconnect, Request
from starlette.types import Message

from src.core.config import settings


def _bounded_upload_request(request: Request, maximum: int | None = None) -> Request:
    """Bound bytes before multipart spooling, including a small framing allowance."""
    maximum = (
        maximum if maximum is not None else (settings.rag_spaces_max_file_size_mb + 1) * 1024 * 1024
    )
    declared = request.headers.get("content-length")
    if declared is not None and int(declared) > maximum:
        raise MultiPartException("Upload body too large")
    received = 0

    async def receive() -> Message:
        nonlocal received
        message = await request.receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > maximum:
                raise MultiPartException("Upload body too large")
        return message

    return Request(request.scope, receive)


@asynccontextmanager
async def parse_document_upload_form(
    request: Request, *, max_body_bytes: int | None = None
) -> AsyncIterator[FormData]:
    try:
        async with _bounded_upload_request(request, max_body_bytes).form(
            max_files=1, max_fields=0
        ) as data:
            yield data
    except HTTPException, MultiPartException:
        raise ValueError("Invalid upload body") from None
    except ClientDisconnect:
        raise OSError("Upload body interrupted") from None
