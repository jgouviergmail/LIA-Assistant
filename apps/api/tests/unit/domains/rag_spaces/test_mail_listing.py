"""Full Gmail listings honor their thread budget across provider pages."""

from dataclasses import dataclass
from typing import NotRequired, TypedDict

import pytest

from src.domains.rag_spaces.mail_sync import _list_label_threads

pytestmark = pytest.mark.unit


class _Thread(TypedDict):
    id: str


class _Page(TypedDict):
    threads: list[_Thread]
    nextPageToken: NotRequired[str]


@dataclass
class _PagedMailbox:
    """Provider fixture with opaque cursors and optionally sparse pages."""

    total: int
    page_size: int = 100
    calls: int = 0

    async def list_threads(
        self, *, label_ids: list[str], max_results: int, page_token: str | None
    ) -> _Page:
        """Return one label page, respecting the requested upper bound."""
        assert label_ids == ["chosen-label"]
        self.calls += 1
        offset = int(page_token) if page_token else 0
        end = min(self.total, offset + min(max_results, self.page_size))
        page: _Page = {"threads": [{"id": f"thread-{i}"} for i in range(offset, end)]}
        if end < self.total:
            page["nextPageToken"] = str(end)
        return page


@pytest.mark.parametrize(("total", "page_size"), [(2051, 100), (10_000, 100), (73, 1)])
async def test_a_full_listing_reaches_every_thread_within_its_budget(
    total: int, page_size: int
) -> None:
    """An unrelated fixed page cap must not truncate an admitted label."""
    mailbox = _PagedMailbox(total, page_size)

    listing = await _list_label_threads(mailbox, "chosen-label", max_threads=total)

    assert listing.complete
    assert listing.ids == tuple(f"thread-{i}" for i in range(total))


async def test_a_thread_budget_is_reported_as_incomplete() -> None:
    """Unseen documents must never be pruned after a bounded listing."""
    mailbox = _PagedMailbox(total=7, page_size=2)

    listing = await _list_label_threads(mailbox, "chosen-label", max_threads=3)

    assert listing.ids == ("thread-0", "thread-1", "thread-2")
    assert not listing.complete
    assert mailbox.calls == 2


async def test_an_empty_label_is_a_complete_listing() -> None:
    """Only a completed empty census can remove previously indexed threads."""
    listing = await _list_label_threads(_PagedMailbox(0), "chosen-label", max_threads=3)

    assert listing.ids == ()
    assert listing.complete


@dataclass
class _RepeatingMailbox:
    """An upstream that never reaches the end or adds a new thread."""

    calls: int = 0

    async def list_threads(
        self, *, label_ids: list[str], max_results: int, page_token: str | None
    ) -> _Page:
        """Keep returning the same id with a next-page cursor."""
        self.calls += 1
        return {"threads": [{"id": "repeated"}], "nextPageToken": str(self.calls)}


async def test_a_nonprogressing_provider_remains_bounded_and_incomplete() -> None:
    """Removing the fixed page cap must not introduce an endless provider loop."""
    mailbox = _RepeatingMailbox()
    budget = 3

    listing = await _list_label_threads(mailbox, "chosen-label", max_threads=budget)

    assert listing.ids == ("repeated",)
    assert not listing.complete
    assert mailbox.calls <= budget
