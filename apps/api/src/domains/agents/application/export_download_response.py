"""Stream to the authenticated browser; the response owns the opened archive lifetime."""

from collections.abc import AsyncIterator

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from src.infrastructure.account_export_downloads import ExportArchiveRead


class ExportDownloadResponse(StreamingResponse):
    def __init__(self, reader: ExportArchiveRead) -> None:
        self._reader = reader
        super().__init__(
            self._chunks(),
            media_type="application/zip",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'attachment; filename="lia-account-export.zip"',
                "Content-Length": str(reader.snapshot.file_size_bytes),
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
