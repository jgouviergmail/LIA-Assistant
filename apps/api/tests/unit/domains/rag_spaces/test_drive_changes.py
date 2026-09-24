"""The Drive changes feed, drained under bounds and routed onto linked trees (ADR-304).

Measured in production on 2026-09-22: one account's feed was drained 25
changes at a time, with no page limit and no deadline, for 935 then 1 328
seconds — the wake sweep that serves every account sat blocked behind it. The
drain now reads pages of the size Google allows, stops at a page count or a
deadline, refuses a feed that stops moving, and says where it stopped.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME
from src.domains.rag_spaces.drive_changes import (
    ChangeRouter,
    ChangesPage,
    DrainBounds,
    DriveFeedError,
    SourceRoute,
    iter_change_pages,
    routed_folder_ids,
)

pytestmark = pytest.mark.unit


def _feed(pages: list[dict[str, Any]]) -> AsyncMock:
    client = AsyncMock()
    client.list_changes = AsyncMock(side_effect=pages)
    return client


def _page(n: int, *, last: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {"changes": [{"fileId": f"f{n}"}]}
    body["newStartPageToken" if last else "nextPageToken"] = f"t{n + 1}"
    return body


async def _drain(client: AsyncMock, bounds: DrainBounds, clock: Any = None) -> list[ChangesPage]:
    kwargs = {"clock": clock} if clock is not None else {}
    return [page async for page in iter_change_pages(client, "t0", bounds, **kwargs)]


async def test_a_feed_is_read_in_pages_of_the_configured_size() -> None:
    client = _feed([_page(0, last=True)])
    await _drain(client, DrainBounds(max_pages=5, deadline_seconds=60))
    client.list_changes.assert_awaited_once_with(
        "t0", page_size=settings.rag_drive_changes_page_size
    )


async def test_a_drained_feed_ends_on_the_new_baseline() -> None:
    client = _feed([_page(0), _page(1), _page(2, last=True)])
    pages = await _drain(client, DrainBounds(max_pages=10, deadline_seconds=60))
    assert [p.resume_token for p in pages] == ["t1", "t2", "t3"]
    assert [p.drained for p in pages] == [False, False, True]
    assert client.list_changes.await_args_list[1].args[0] == "t1"


async def test_the_page_bound_stops_the_drain_and_keeps_its_place() -> None:
    client = _feed([_page(n) for n in range(10)])
    pages = await _drain(client, DrainBounds(max_pages=3, deadline_seconds=60))
    assert len(pages) == 3
    assert pages[-1].drained is False
    assert pages[-1].resume_token == "t3"


async def test_the_deadline_stops_the_drain_after_the_page_in_flight() -> None:
    client = _feed([_page(n) for n in range(10)])
    ticks = iter([0.0, 10.0, 31.0, 99.0])
    pages = await _drain(
        client, DrainBounds(max_pages=10, deadline_seconds=30), clock=lambda: next(ticks)
    )
    assert len(pages) == 2, "the deadline is read after each page; the page read is kept"
    assert pages[-1].drained is False


async def test_a_feed_that_returns_the_token_it_was_given_is_refused() -> None:
    client = _feed([{"changes": [], "nextPageToken": "t0"}])
    with pytest.raises(DriveFeedError, match="did not move"):
        await _drain(client, DrainBounds(max_pages=10, deadline_seconds=60))


async def test_a_page_carrying_neither_token_is_refused() -> None:
    client = _feed([{"changes": []}])
    with pytest.raises(DriveFeedError, match="neither"):
        await _drain(client, DrainBounds(max_pages=10, deadline_seconds=60))


async def test_an_empty_page_that_still_moves_the_feed_is_kept() -> None:
    client = _feed([{"changes": [], "nextPageToken": "t1"}, _page(1, last=True)])
    pages = await _drain(client, DrainBounds(max_pages=10, deadline_seconds=60))
    assert [p.changes for p in pages] == [[], [{"fileId": "f1"}]]


def test_the_bounds_come_from_the_settings() -> None:
    bounds = DrainBounds.from_settings()
    assert bounds.max_pages == settings.rag_drive_push_max_pages
    assert bounds.deadline_seconds == settings.rag_drive_push_drain_deadline_seconds


# ============================================================================
# Routing across the pages of one drain
# ============================================================================


def _route(folder_id: str, folder_ids: tuple[str, ...] = ()) -> SourceRoute:
    return SourceRoute(
        id=uuid.uuid4(), space_id=uuid.uuid4(), folder_id=folder_id, folder_ids=folder_ids
    )


def _change(file_id: str, parent: str, *, folder: bool = False, gone: bool = False) -> dict:
    return {
        "fileId": file_id,
        "removed": False,
        "file": {
            "id": file_id,
            "mimeType": GOOGLE_DRIVE_FOLDER_MIME if folder else "text/plain",
            "parents": [parent],
            "trashed": gone,
        },
    }


def test_a_source_never_walked_routes_on_its_root_alone() -> None:
    assert routed_folder_ids(_route("root")) == ["root"]
    assert routed_folder_ids(_route("root", ("root", "sub"))) == ["root", "sub"]


def test_a_sub_folder_created_on_one_page_routes_the_files_of_the_next() -> None:
    route = _route("root", ("root",))
    router = ChangeRouter([route])
    router.route([_change("newsub", "root", folder=True)])
    router.route([_change("f9", "newsub"), _change("elsewhere", "other")])
    [touched] = router.touched()
    assert [c["fileId"] for c in touched.changes] == ["f9"]
    assert touched.folder_ids == ["root", "newsub"]


def test_a_trashed_sub_folder_leaves_the_routing_set_and_touches_the_source() -> None:
    router = ChangeRouter([_route("root", ("root", "sub"))])
    router.route([_change("sub", "root", folder=True, gone=True)])
    [touched] = router.touched()
    assert touched.folder_ids == ["root"]
    assert touched.changes == []


def test_a_feed_that_touches_no_linked_tree_touches_nothing() -> None:
    router = ChangeRouter([_route("root", ("root",))])
    router.route([_change("f1", "elsewhere")])
    assert router.touched() == []


def test_the_router_keeps_only_what_it_routes() -> None:
    """A drain holds the routed changes, never the whole feed (bounded memory)."""
    router = ChangeRouter([_route("root", ("root",))])
    router.route([_change(f"x{i}", "elsewhere") for i in range(1000)] + [_change("f1", "root")])
    [touched] = router.touched()
    assert len(touched.changes) == 1
