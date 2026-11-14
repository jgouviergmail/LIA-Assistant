"""Declare event-stream transport for FastAPI metadata and dependency guards."""

from fastapi.responses import StreamingResponse


class EventStreamResponse(StreamingResponse):
    """SSE response; finite file downloads retain their own declared media type."""

    media_type = "text/event-stream"
