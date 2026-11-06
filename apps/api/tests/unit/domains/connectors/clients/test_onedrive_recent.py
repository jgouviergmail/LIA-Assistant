"""OneDrive's latest files, which no Graph call lists on a personal drive (ADR-369, lot 11).

Measured on a real drive of 30,960 items: a search takes no empty query, ignores ``$orderby`` and
stops at 200 items, a folder's date does not follow what changes under it, ``recent`` answers one
item, and enumerating the drive takes a minute. The feed alone is exact: the window starts from the
top of the drive and fills with what changes.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import (
    GOOGLE_DRIVE_FOLDER_MIME,
    ONEDRIVE_RECENT_FEED_PAGES,
    ONEDRIVE_RECENT_SEED_REQUESTS,
    ONEDRIVE_RECENT_TTL_SECONDS,
    ONEDRIVE_RECENT_WINDOW_MAX,
    REDIS_KEY_ONEDRIVE_RECENT_PREFIX,
)
from src.domains.connectors.clients.onedrive_changes import ChangesFeedLostError
from src.domains.connectors.clients.onedrive_recent import recent_window
from src.infrastructure.cache.key_families import KeyScope, scope_of

pytestmark = pytest.mark.unit

USER = uuid4()


def _file(file_id: str, day: int = 1) -> dict[str, Any]:
    return {
        "id": file_id,
        "name": f"{file_id}.pdf",
        "mimeType": "application/pdf",
        "modifiedTime": f"2026-11-{day:02d}T09:00:00Z",
        "webViewLink": f"https://onedrive.live.com/{file_id}",
        "parents": ["p"],
        "owners": [],
    }


def _folder(folder_id: str, day: int = 1) -> dict[str, Any]:
    return {
        "id": folder_id,
        "name": folder_id,
        "mimeType": GOOGLE_DRIVE_FOLDER_MIME,
        "modifiedTime": f"2026-11-{day:02d}T09:00:00Z",
    }


def _changed(item: dict[str, Any]) -> dict[str, Any]:
    return {"fileId": item["id"], "removed": False, "file": item}


def _removed(file_id: str) -> dict[str, Any]:
    return {"fileId": file_id, "removed": True, "file": {"id": file_id}}


class _Redis:
    def __init__(self, stored: dict[str, Any] | None = None) -> None:
        self.value = json.dumps(stored) if stored is not None else None
        self.set = AsyncMock(side_effect=self._set)

    async def get(self, _key: str) -> str | None:
        return self.value

    async def _set(self, _key: str, value: str, ex: int) -> None:
        self.value = value


def _drive(folders: dict[str, list[dict[str, Any]]] | None = None, **calls: Any) -> Any:
    tree = folders if folders is not None else {"root": []}

    async def listed(folder_id: str, **_options: Any) -> dict[str, Any]:
        return {"files": tree.get(folder_id, []), "nextPageToken": None}

    drive = MagicMock(user_id=USER)
    drive.list_files = AsyncMock(side_effect=listed)
    drive.get_changes_start_page_token = AsyncMock(return_value="baseline")
    drive.list_changes = AsyncMock(return_value={"changes": [], "newStartPageToken": "next"})
    for name, value in calls.items():
        setattr(drive, name, value)
    return drive


async def _read(drive: Any, redis: _Redis, limit: int = 5) -> list[dict[str, Any]]:
    with patch(
        "src.domains.connectors.clients.onedrive_recent.get_redis_cache",
        AsyncMock(return_value=redis),
    ):
        return await recent_window(drive, limit)


class TestTheFirstRead:
    async def test_it_starts_from_the_top_newest_first_never_a_folder(self) -> None:
        tree = {
            "root": [_file("old", 1), _folder("work", 3), _file("new", 5)],
            "work": [_file("inside", 4)],
        }
        files = await _read(_drive(tree), _Redis())

        assert [item["id"] for item in files] == ["new", "inside", "old"]

    async def test_it_asks_each_folder_newest_first(self) -> None:
        drive = _drive()

        await _read(drive, _Redis())

        assert drive.list_files.await_args.kwargs["order_by"] == "folder,modifiedTime desc"
        assert drive.list_files.await_args.kwargs["folder_id"] == "root"

    async def test_it_opens_the_folders_changed_last_first_within_its_budget(self) -> None:
        count = ONEDRIVE_RECENT_SEED_REQUESTS + 3
        tree: dict[str, list[dict[str, Any]]] = {
            "root": [_folder(f"f{day}", day) for day in range(1, count + 1)]
        }
        drive = _drive(tree)

        await _read(drive, _Redis())

        opened = [call.kwargs["folder_id"] for call in drive.list_files.await_args_list]
        assert len(opened) == ONEDRIVE_RECENT_SEED_REQUESTS
        assert opened[1] == f"f{count}"

    async def test_the_feed_is_taken_first_so_nothing_falls_between(self) -> None:
        order: list[str] = []
        drive = _drive(
            get_changes_start_page_token=AsyncMock(
                side_effect=lambda: order.append("token") or "t"
            ),
        )
        listing = drive.list_files.side_effect

        async def listed(**options: Any) -> dict[str, Any]:
            order.append("listing")
            return await listing(**options)

        drive.list_files = AsyncMock(side_effect=listed)

        await _read(drive, _Redis())

        assert order[:2] == ["token", "listing"]

    async def test_what_it_found_is_kept_with_the_token_for_a_month(self) -> None:
        redis = _Redis()

        await _read(_drive({"root": [_file("a")]}), redis)

        key, value = redis.set.await_args.args
        assert key == f"{REDIS_KEY_ONEDRIVE_RECENT_PREFIX}{USER}"
        assert redis.set.await_args.kwargs == {"ex": ONEDRIVE_RECENT_TTL_SECONDS}
        kept = json.loads(value)
        assert kept["token"] == "baseline"
        assert [item["id"] for item in kept["files"]] == ["a"]


class TestALaterRead:
    @staticmethod
    def _held(*files: dict[str, Any], token: str = "from") -> _Redis:
        return _Redis({"token": token, "files": list(files)})

    async def test_it_costs_one_call_from_where_it_stopped(self) -> None:
        drive = _drive()

        await _read(drive, self._held(_file("a")))

        drive.list_changes.assert_awaited_once()
        assert drive.list_changes.await_args.args[0] == "from"
        drive.list_files.assert_not_awaited()

    async def test_a_changed_file_comes_first_wherever_it_lives(self) -> None:
        feed = {"changes": [_changed(_file("deep", 9))], "newStartPageToken": "next"}
        drive = _drive(list_changes=AsyncMock(return_value=feed))

        files = await _read(drive, self._held(_file("a", 2)))

        assert [item["id"] for item in files] == ["deep", "a"]

    async def test_a_file_changed_again_is_listed_once_at_its_new_date(self) -> None:
        feed = {"changes": [_changed(_file("a", 9))], "newStartPageToken": "next"}
        drive = _drive(list_changes=AsyncMock(return_value=feed))

        files = await _read(drive, self._held(_file("a", 2), _file("b", 3)))

        assert [item["id"] for item in files] == ["a", "b"]

    async def test_a_deleted_file_leaves_it(self) -> None:
        feed = {"changes": [_removed("a")], "newStartPageToken": "next"}
        drive = _drive(list_changes=AsyncMock(return_value=feed))

        files = await _read(drive, self._held(_file("a"), _file("b")))

        assert [item["id"] for item in files] == ["b"]

    async def test_a_folder_takes_no_place(self) -> None:
        feed = {"changes": [_changed(_folder("d", 9))], "newStartPageToken": "next"}
        drive = _drive(list_changes=AsyncMock(return_value=feed))

        assert await _read(drive, self._held()) == []

    async def test_the_token_moves_past_what_was_read(self) -> None:
        redis = self._held(_file("a"))

        await _read(_drive(), redis)

        assert json.loads(redis.value)["token"] == "next"

    async def test_a_burst_is_read_a_few_pages_at_a_time_and_resumes(self) -> None:
        page = {"changes": [], "nextPageToken": "further"}
        drive = _drive(list_changes=AsyncMock(return_value=page))
        redis = self._held(_file("a"))

        await _read(drive, redis)

        assert drive.list_changes.await_count == ONEDRIVE_RECENT_FEED_PAGES
        assert json.loads(redis.value)["token"] == "further"

    async def test_it_stays_within_its_size(self) -> None:
        many = [
            _file(f"f{index}", 1 + index % 28) for index in range(ONEDRIVE_RECENT_WINDOW_MAX * 2)
        ]
        feed = {"changes": [_changed(item) for item in many], "newStartPageToken": "next"}
        redis = self._held()

        await _read(_drive(list_changes=AsyncMock(return_value=feed)), redis)

        assert len(json.loads(redis.value)["files"]) == ONEDRIVE_RECENT_WINDOW_MAX

    async def test_it_answers_no_more_than_asked(self) -> None:
        files = await _read(_drive(), self._held(_file("a"), _file("b")), limit=1)

        assert len(files) == 1

    async def test_a_token_graph_forgot_starts_it_again(self) -> None:
        drive = _drive(
            {"root": [_file("fresh", 8)]}, list_changes=AsyncMock(side_effect=ChangesFeedLostError)
        )
        redis = self._held(_file("stale"))

        files = await _read(drive, redis)

        assert [item["id"] for item in files] == ["fresh"]
        assert json.loads(redis.value)["token"] == "baseline"


class TestItsBookkeeping:
    async def test_a_redis_that_cannot_read_never_fails_the_card(self) -> None:
        redis = _Redis()
        redis.get = AsyncMock(side_effect=ConnectionError("redis down"))  # type: ignore[method-assign]

        files = await _read(_drive({"root": [_file("a")]}), redis)

        assert [item["id"] for item in files] == ["a"]

    async def test_a_redis_that_cannot_write_never_fails_the_card(self) -> None:
        redis = _Redis()
        redis.set = AsyncMock(side_effect=ConnectionError("redis down"))

        files = await _read(_drive({"root": [_file("a")]}), redis)

        assert [item["id"] for item in files] == ["a"]

    async def test_a_value_nobody_can_read_starts_it_again(self) -> None:
        redis = _Redis()
        redis.value = "not json"

        files = await _read(_drive({"root": [_file("a")]}), redis)

        assert [item["id"] for item in files] == ["a"]

    def test_it_is_a_cache_of_the_account_a_reset_may_drop(self) -> None:
        assert scope_of(f"{REDIS_KEY_ONEDRIVE_RECENT_PREFIX}{USER}") is KeyScope.USER_CACHE
