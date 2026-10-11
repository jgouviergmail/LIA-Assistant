"""An attachment owns and closes its transient export on every ASGI exit."""

from collections.abc import AsyncIterator
from typing import Literal

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from src.core.management_export_file import ManagementExportFile


class ManagementExportResponse(StreamingResponse):
    def __init__(
        self,
        reader: ManagementExportFile,
        *,
        collection: Literal["interests", "memories", "journals"],
        format: Literal["csv", "json"],
    ) -> None:
        self._reader = reader
        super().__init__(
            self._chunks(),
            media_type="text/csv; charset=utf-8" if format == "csv" else "application/json",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="lia-{collection}.{format}"',
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
