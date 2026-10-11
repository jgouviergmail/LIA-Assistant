"""A confirmed attachment owns a frozen reader and closes it on every ASGI exit."""

import re
from collections.abc import AsyncIterator
from urllib.parse import quote

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from src.infrastructure.file_transfer import LocalFileRead


class StoredFileResponse(StreamingResponse):
    def __init__(self, reader: LocalFileRead, *, filename: str, content_type: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", content_type):
            raise ValueError("Invalid stored MIME metadata")
        self._reader = reader
        super().__init__(
            self._chunks(),
            media_type=content_type,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f"attachment; filename=\"lia-document\"; filename*=UTF-8''{quote(filename, safe='')}",
                "Content-Length": str(reader.file_size_bytes),
            },
        )

    async def _chunks(self) -> AsyncIterator[bytes]:
        while chunk := await self._reader.read_chunk():
            yield chunk

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._reader.close()
