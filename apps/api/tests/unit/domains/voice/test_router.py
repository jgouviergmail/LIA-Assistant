"""Unit tests for the voice WebSocket router — disconnect handling and metric guard.

Targets two regressions:

1. ``websocket.receive()`` (the raw ASGI helper) returns ``{"type":
   "websocket.disconnect"}`` instead of raising ``WebSocketDisconnect`` (only
   the typed ``receive_text/bytes/json`` helpers raise via
   ``_raise_on_disconnect``). The previous implementation fell through both
   ``"text" in data`` and ``"bytes" in data`` branches and looped — Starlette
   then raised ``RuntimeError: Cannot call "receive" once a disconnect message
   has been received.`` on the next iteration.
2. ``websocket_connections_active`` was decremented in the ``finally`` block
   whenever ``user_id`` was set, even when ``websocket.accept()`` had not run.
   The fix introduces an ``accepted`` flag.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeWebSocket:
    """Minimal stand-in for a Starlette ``WebSocket`` instance.

    Drives the message loop by yielding the messages provided at
    construction time. Records calls to ``accept`` / ``close`` /
    ``send_json`` so assertions can inspect them.
    """

    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._iter: AsyncIterator[dict[str, Any]] = self._gen(messages)
        self.accepted = False
        self.close_calls: list[dict[str, Any]] = []
        self.sent_json: list[Any] = []

    @staticmethod
    async def _gen(messages: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        for msg in messages:
            yield msg

    async def accept(self) -> None:
        self.accepted = True

    async def receive(self) -> dict[str, Any]:
        return await anext(self._iter)

    async def send_json(self, payload: Any) -> None:
        self.sent_json.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append({"code": code, "reason": reason})


@pytest.fixture
def _ticket_store() -> MagicMock:
    store = MagicMock()
    store.validate_and_consume_ticket = AsyncMock(
        return_value={"user_id": "user-uuid", "language": "fr"}
    )
    return store


@pytest.fixture
def _rate_limiter_allow() -> MagicMock:
    limiter = MagicMock()
    limiter.acquire = AsyncMock(return_value=True)
    return limiter


@pytest.mark.asyncio
async def test_websocket_breaks_cleanly_on_disconnect_message(
    _ticket_store: MagicMock, _rate_limiter_allow: MagicMock
) -> None:
    """Regression: when the client disconnects, ``receive()`` returns the
    disconnect message dict and the loop must ``break`` instead of looping
    again (which would trigger Starlette's RuntimeError).
    """
    fake_ws = _FakeWebSocket(
        messages=[
            # Client opens, sends one chunk of audio, then disconnects.
            {"type": "websocket.receive", "bytes": b"\x00\x01" * 100},
            {"type": "websocket.disconnect", "code": 1000},
        ]
    )

    with (
        patch("src.domains.voice.router.get_redis_session", AsyncMock()),
        patch("src.domains.voice.router.get_redis_cache", AsyncMock()),
        patch("src.domains.voice.router.WebSocketTicketStore", return_value=_ticket_store),
        patch("src.domains.voice.router.RedisRateLimiter", return_value=_rate_limiter_allow),
        patch("src.domains.voice.router.get_stt_service", return_value=MagicMock()),
        patch("src.domains.voice.router.websocket_connections_active") as gauge,
        patch("src.domains.voice.router.websocket_connection_duration_seconds"),
        patch("src.domains.voice.router.websocket_connections_total"),
        patch("src.domains.voice.router.websocket_audio_bytes_received"),
        patch("src.domains.voice.router.logger") as logger,
    ):
        # Import inside the patch context so the patched logger is bound.
        from src.domains.voice.router import websocket_audio

        # Must not raise — the disconnect branch must break out cleanly.
        await websocket_audio(fake_ws, ticket="abcdef0123456789")  # type: ignore[arg-type]

    # Assertions on lifecycle.
    assert fake_ws.accepted is True, "accept() should have been called"
    # Active gauge: exactly one inc (on accept) and one dec (in finally).
    assert gauge.inc.call_count == 1
    assert gauge.dec.call_count == 1
    # The disconnect log must have been emitted.
    info_event_names = [c.args[0] for c in logger.info.call_args_list if c.args]
    assert "websocket_disconnected_by_client" in info_event_names


@pytest.mark.asyncio
async def test_websocket_accept_failure_does_not_phantom_decrement(
    _ticket_store: MagicMock, _rate_limiter_allow: MagicMock
) -> None:
    """Regression: when ``websocket.accept()`` raises (e.g. client closed
    before accept), the ``finally`` must NOT decrement the active-connections
    gauge because the corresponding ``inc()`` never ran.
    """
    fake_ws = _FakeWebSocket(messages=[])
    fake_ws.accept = AsyncMock(side_effect=RuntimeError("client gone"))  # type: ignore[method-assign]

    with (
        patch("src.domains.voice.router.get_redis_session", AsyncMock()),
        patch("src.domains.voice.router.get_redis_cache", AsyncMock()),
        patch("src.domains.voice.router.WebSocketTicketStore", return_value=_ticket_store),
        patch("src.domains.voice.router.RedisRateLimiter", return_value=_rate_limiter_allow),
        patch("src.domains.voice.router.get_stt_service", return_value=MagicMock()),
        patch("src.domains.voice.router.websocket_connections_active") as gauge,
        patch("src.domains.voice.router.websocket_connection_duration_seconds"),
        patch("src.domains.voice.router.websocket_connections_total"),
        patch("src.domains.voice.router.websocket_audio_bytes_received"),
    ):
        from src.domains.voice.router import websocket_audio

        # The handler swallows the exception via its outer ``try`` / log.
        await websocket_audio(fake_ws, ticket="abcdef0123456789")  # type: ignore[arg-type]

    # Critical: no inc, no dec — the gauge must stay balanced.
    assert gauge.inc.call_count == 0
    assert gauge.dec.call_count == 0
