"""Intermediaries must forward a live event before the response ever ends."""

import asyncio

import pytest
from starlette.datastructures import Headers
from starlette.types import Message, Receive, Scope, Send

from src.core.middleware import SecurityHeadersMiddleware


@pytest.mark.parametrize(
    ("content_type", "cache_control"),
    [
        ("text/event-stream; charset=utf-8", None),
        ("text/event-stream", "no-store, private"),
        ("Text/Event-Stream; charset=UTF-8", "no-cache, No-Transform"),
        ("application/json", "private, max-age=60"),
    ],
)
async def test_event_stream_is_not_transformed_and_does_not_wait_for_completion(
    content_type: str, cache_control: str | None
) -> None:
    started, finish = asyncio.Event(), asyncio.Event()
    messages: list[Message] = []

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        headers = [(b"content-type", content_type.encode())]
        if cache_control is not None:
            headers.append((b"cache-control", cache_control.encode()))
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
        started.set()
        await finish.wait()
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        messages.append(message)

    task = asyncio.create_task(
        SecurityHeadersMiddleware(application)({"type": "http"}, receive, send)
    )
    try:
        await asyncio.wait_for(started.wait(), 1)
        assert not task.done(), "the response remains open"
        assert messages[1]["body"] == b"data: first\n\n"
        assert messages[1]["more_body"] is True
        headers = Headers(raw=messages[0]["headers"])
        if content_type.lower().startswith("text/event-stream"):
            directives = [part.strip() for part in headers["cache-control"].split(",")]
            # Next.js's pinned compression package recognizes this canonical token.
            assert directives.count("no-transform") == 1
            assert {part.lower() for part in directives} >= {
                part.strip().lower() for part in (cache_control or "no-cache").split(",")
            }
        else:
            assert headers["cache-control"] == cache_control
    finally:
        finish.set()
        await task
