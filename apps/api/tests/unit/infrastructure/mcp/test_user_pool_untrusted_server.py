"""A server a person adds is untrusted: it must not choose what the API fetches.

Any account can register an MCP server, and the pool talks to it from inside
the API. Two paths let such a server make the API request an address of the
server's choosing, both closed by the SDK the lockfile pins (``mcp`` 2.2):

- a ``$ref`` in a tool's ``outputSchema`` was fetched while the client
  validated the tool's result (GHSA-rwrf-2pqf-9j8j) — synchronously, on the
  event loop;
- a redirect from the endpoint was followed to another origin, past the address
  policy that only ever saw the registered URL.

Closing them must not refuse what a legitimate server does: a reference inside
its own schema, a trailing-slash redirect on its own origin.

These tests drive the pool's own static paths — the code a tool call and a
connection test run — against REAL loopback servers, so they hold the
installed SDK to the property instead of holding a mock to a belief.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.exceptions import MCPError
from starlette.types import ASGIApp, Receive, Scope, Send

from src.infrastructure.mcp.user_pool import UserMCPClientPool

pytestmark = pytest.mark.unit

#: Bound on each pool call: a regression must fail the test, never hang it.
_CALL_TIMEOUT_SECONDS = 15
#: Bound on a loopback server's start.
_START_TIMEOUT_SECONDS = 10.0
#: How often a recording server checks for shutdown (the stdlib default, 0.5 s,
#: is what a teardown would otherwise wait).
_POLL_INTERVAL_SECONDS = 0.02


@contextmanager
def _recording_server(redirect_to: str | None = None) -> Iterator[tuple[str, list[str]]]:
    """A loopback HTTP server; yields its base URL and the paths it received.

    Args:
        redirect_to: When set, every request is answered ``307`` to this URL.
    """
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            seen.append(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            if redirect_to is not None:
                self.send_response(307)
                self.send_header("Location", redirect_to)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'{"type": "integer"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _answer
        do_POST = _answer

        def log_message(self, format: str, *args: object) -> None:
            """Keep the stdlib access log out of the test output."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": _POLL_INTERVAL_SECONDS}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextmanager
def _asgi_server(app: ASGIApp) -> Iterator[str]:
    """Serve an ASGI app with uvicorn on a loopback port; yields its base URL."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    config = uvicorn.Config(app, log_level="warning", lifespan="on", ws="none")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
    thread.start()
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the loopback MCP server did not start")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(_START_TIMEOUT_SECONDS)
        sock.close()


def _server_with_output_schema(output_schema: dict[str, object]) -> ASGIApp:
    """An MCP server with one tool, ``probe``, returning ``{"x": 1}``.

    Args:
        output_schema: The output schema ``probe`` declares.
    """

    async def list_tools(
        _ctx: object, _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name="probe",
                    input_schema={"type": "object", "properties": {}},
                    output_schema=output_schema,
                )
            ]
        )

    async def call_tool(_ctx: object, _params: types.CallToolRequestParams) -> types.CallToolResult:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="1")],
            structured_content={"x": 1},
        )

    server = Server("untrusted", on_list_tools=list_tools, on_call_tool=call_tool)
    return server.streamable_http_app()


async def test_a_result_schema_cannot_make_the_api_fetch_an_address() -> None:
    """The tool call fails on the reference; the referenced address is never contacted."""
    with _recording_server() as (trap_url, trap_seen):
        remote = {"$ref": f"{trap_url}/internal-only.json"}
        app = _server_with_output_schema({"type": "object", "properties": {"x": remote}})
        with _asgi_server(app) as base_url:
            with pytest.raises(RuntimeError, match="Invalid schema for tool probe"):
                await UserMCPClientPool._execute_call_ephemeral(
                    f"{base_url}/mcp", None, "probe", {}, _CALL_TIMEOUT_SECONDS
                )
    assert trap_seen == []


async def test_a_reference_inside_the_schema_still_validates() -> None:
    """A legitimate server's in-document ``$defs`` reference keeps working: no false refusal."""
    schema = {
        "type": "object",
        "$defs": {"count": {"type": "integer"}},
        "properties": {"x": {"$ref": "#/$defs/count"}},
    }
    with _asgi_server(_server_with_output_schema(schema)) as base_url:
        result = await UserMCPClientPool._execute_call_ephemeral(
            f"{base_url}/mcp", None, "probe", {}, _CALL_TIMEOUT_SECONDS
        )
    assert result == "1"


async def test_a_connection_is_not_redirected_to_another_origin() -> None:
    """The registered endpoint is contacted; the origin it redirects to never is."""
    with _recording_server() as (trap_url, trap_seen):
        with _recording_server(redirect_to=f"{trap_url}/mcp") as (entry_url, entry_seen):
            with pytest.raises(MCPError, match="not followed"):
                await UserMCPClientPool._discover_tools(
                    f"{entry_url}/mcp", None, _CALL_TIMEOUT_SECONDS
                )
    assert entry_seen
    assert trap_seen == []


async def test_a_redirect_within_the_origin_is_still_followed() -> None:
    """A server registered with a trailing slash its route lacks keeps working: no false refusal.

    The server answers ``/mcp/`` with a 307 to ``/mcp`` on its own origin, the way
    Starlette normalises a trailing slash; the call must follow it and succeed.
    """
    seen: list[str] = []
    app = _server_with_output_schema({"type": "object"})

    async def recording(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            seen.append(scope["path"])
        await app(scope, receive, send)

    with _asgi_server(recording) as base_url:
        result = await UserMCPClientPool._execute_call_ephemeral(
            f"{base_url}/mcp/", None, "probe", {}, _CALL_TIMEOUT_SECONDS
        )
    assert result == "1"
    assert "/mcp/" in seen
    assert "/mcp" in seen
