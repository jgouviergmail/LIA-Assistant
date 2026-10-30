"""Discovery follows the server's pages, in canonical order, with guards (M1, E7).

The pool listed the FIRST page only, so a server paginating its tools lost
every tool past it in silence — MCP: « clients MUST NOT assume a fixed page
size » (spec 2026-10-21 §0quater). Like the OpenAI Agents SDK and
langchain-mcp-adapters, discovery follows ``nextCursor``, stops on a repeated
cursor and at a page cap, and stops at ``mcp_max_tools_per_server`` — each
with its own outcome. It also keeps what the 2026-07-28 revision lets a server
say about its list (``ttlMs``, ``cacheScope``) and its handshake instructions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.core.config import settings
from src.core.constants import MCP_DISCOVERY_MAX_PAGES
from src.infrastructure.mcp.user_pool import UserMCPClientPool

pytestmark = pytest.mark.unit


def _tool(name: str) -> Any:
    return SimpleNamespace(
        name=name,
        description=f"{name} tool",
        input_schema={"type": "object"},
        output_schema=None,
        annotations=None,
        title=None,
        meta=None,
    )


class PagedClient:
    def __init__(self, pages: dict[str | None, tuple[list[str], str | None]], **extra: Any) -> None:
        self.pages = pages
        self.cursors: list[str | None] = []
        self.instructions = extra.get("instructions")
        self.ttl_ms = extra.get("ttl_ms")
        self.cache_scope = extra.get("cache_scope")

    async def list_tools(self, *, cursor: str | None = None, **_: Any) -> Any:
        self.cursors.append(cursor)
        names, next_cursor = self.pages[cursor]
        return SimpleNamespace(
            tools=[_tool(n) for n in names],
            next_cursor=next_cursor,
            ttl_ms=self.ttl_ms,
            cache_scope=self.cache_scope,
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return SimpleNamespace(content=[SimpleNamespace(text="# reference")])


async def _discover(client: PagedClient) -> Any:
    @asynccontextmanager
    async def ephemeral(*_: Any, **__: Any) -> AsyncIterator[PagedClient]:
        yield client

    with patch("src.infrastructure.mcp.user_pool._ephemeral_client", ephemeral):
        return await UserMCPClientPool._discover_tools("https://srv.example/mcp", None, 30)


async def test_discovery_follows_cursor_across_pages_in_canonical_order() -> None:
    client = PagedClient(
        {None: (["zeta", "alpha"], "p2"), "p2": (["mid"], "p3"), "p3": (["beta"], None)},
        instructions="Call search first.",
        ttl_ms=120_000,
        cache_scope="private",
    )

    found = await _discover(client)

    assert client.cursors == [None, "p2", "p3"]
    assert [t["name"] for t in found.tools] == ["alpha", "beta", "mid", "zeta"]
    assert found.outcome == "complete"
    assert (found.server_ttl_ms, found.cache_scope) == (120_000, "private")
    assert found.server_instructions == "Call search first."


async def test_a_repeated_cursor_stops_the_listing() -> None:
    client = PagedClient({None: (["a"], "loop"), "loop": (["b"], "loop")})

    found = await _discover(client)

    assert client.cursors == [None, "loop"]
    assert [t["name"] for t in found.tools] == ["a", "b"]
    assert found.outcome == "repeated_cursor"


async def test_the_page_cap_stops_the_listing() -> None:
    pages = {
        (None if i == 0 else f"p{i}"): ([f"t{i}"], f"p{i + 1}")
        for i in range(MCP_DISCOVERY_MAX_PAGES + 5)
    }
    client = PagedClient(pages)

    found = await _discover(client)

    assert len(client.cursors) == MCP_DISCOVERY_MAX_PAGES
    assert found.outcome == "page_cap"


async def test_the_per_server_cap_stops_the_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mcp_max_tools_per_server", 3)
    client = PagedClient({None: (["a", "b"], "p2"), "p2": (["c", "d"], "p3"), "p3": (["e"], None)})

    found = await _discover(client)

    assert len(found.tools) == 3
    assert client.cursors == [None, "p2"]
    assert found.outcome == "tool_cap"


async def test_the_reference_tool_is_detected() -> None:
    found = await _discover(PagedClient({None: (["read_me", "search"], None)}))
    assert found.has_reference_tool is True


@pytest.mark.parametrize(
    ("declared", "read"),
    [("public", "public"), ("private", "private"), ("shared", None), (None, None)],
)
def test_only_the_two_specified_cache_scopes_are_read(declared: object, read: object) -> None:
    from src.infrastructure.mcp.pool_catalogue import cache_scope

    assert cache_scope(SimpleNamespace(cache_scope=declared)) == read
