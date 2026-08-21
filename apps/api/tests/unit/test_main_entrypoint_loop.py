"""The __main__ launcher picks a psycopg-compatible event loop on Windows.

Measured on the pinned stack (ADR-241 follow-up, 2026-08-21):
- psycopg 3.3.4 raises ``InterfaceError`` under ProactorEventLoop (no
  ``add_reader``) and works under SelectorEventLoop;
- uvicorn 0.48's ``asyncio_loop_factory(use_subprocess=False)`` returns
  **Proactor** on win32, and its runner passes a ``loop_factory`` to
  ``asyncio.run`` — which makes any event-loop *policy* a no-op;
- under ``--reload`` the app lives in a subprocess where the same factory
  returns Selector, which is why the everyday dev path never broke.

So the non-reload Windows branch must drive ``Server.serve()`` itself with an
explicit ``loop_factory=asyncio.SelectorEventLoop``. These tests pin that
branch (and the reload delegation) by running ``src.main`` as ``__main__``
with the boundaries patched — no server, no sockets.
"""

from __future__ import annotations

import asyncio
import runpy
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import settings

pytestmark = pytest.mark.unit


def test_win32_without_reload_serves_under_a_selector_loop_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """win32 + debug=False → Server.serve() driven by asyncio.run(SelectorEventLoop)."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.delitem(sys.modules, "src.main", raising=False)

    # serve() returns a plain sentinel, NOT a coroutine: asyncio.run is mocked
    # and would never await it — a real coroutine here leaks and trips the
    # F028 unawaited-coroutine guard on the next test's teardown.
    serve_sentinel = object()
    server = MagicMock()
    server.serve = MagicMock(return_value=serve_sentinel)
    with (
        patch("uvicorn.Server", return_value=server) as server_cls,
        patch("uvicorn.run") as uv_run,
        patch("asyncio.run") as aio_run,
    ):
        runpy.run_module("src.main", run_name="__main__")

    uv_run.assert_not_called()
    config = server_cls.call_args.args[0]
    assert config.loop == "asyncio"
    assert aio_run.call_args.args[0] is serve_sentinel  # runs THAT server's serve()
    assert aio_run.call_args.kwargs["loop_factory"] is asyncio.SelectorEventLoop


def test_reload_path_delegates_to_uvicorn_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """debug=True (any platform) → plain uvicorn.run with reload — uvicorn's
    reload SUBPROCESS gets a SelectorEventLoop from its own factory on win32."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.delitem(sys.modules, "src.main", raising=False)

    with (
        patch("uvicorn.run") as uv_run,
        patch("asyncio.run") as aio_run,
    ):
        runpy.run_module("src.main", run_name="__main__")

    aio_run.assert_not_called()
    assert uv_run.call_args.kwargs["reload"] is True
    assert uv_run.call_args.kwargs["loop"] == "asyncio"
