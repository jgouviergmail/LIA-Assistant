"""The Drive tree under a linked folder, walked once and bounded.

Google Drive lists ONE level per call (``'{id}' in parents``): the files of a
sub-folder are invisible to a source that only reads its root. The walk is a
breadth-first traversal shared by the synchronisation and the preflight, so
the count a person is shown is computed by the code that indexes.
"""

from __future__ import annotations

import pytest

from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME, GOOGLE_DRIVE_SHORTCUT_MIME
from src.domains.rag_spaces.drive_walk import DriveWalkError, walk_drive_tree
from tests.unit.domains.rag_spaces.drive_fakes import FakeDriveClient, drive_file

pytestmark = pytest.mark.unit

FOLDER = GOOGLE_DRIVE_FOLDER_MIME
_file = drive_file


@pytest.mark.asyncio
async def test_walks_every_sub_folder_breadth_first() -> None:
    client = FakeDriveClient(
        {
            "root": [_file("a"), _file("sub1", FOLDER), _file("sub2", FOLDER)],
            "sub1": [_file("b"), _file("deep", FOLDER)],
            "sub2": [_file("c")],
            "deep": [_file("d")],
        }
    )
    tree = await walk_drive_tree(client, "root", max_files=500, max_folders=100)
    assert [f["id"] for f in tree.files] == ["a", "b", "c", "d"]
    assert tree.folder_ids == ["root", "sub1", "sub2", "deep"]
    assert tree.truncated is False
    assert tree.unreadable_folders == 0


@pytest.mark.asyncio
async def test_paginates_files_inside_one_folder() -> None:
    client = FakeDriveClient({"root": [_file(f"f{i}") for i in range(7)]}, page_size=3)
    tree = await walk_drive_tree(client, "root", max_files=500, max_folders=100)
    assert len(tree.files) == 7
    assert tree.truncated is False


@pytest.mark.asyncio
async def test_file_cap_stops_the_walk_and_says_so() -> None:
    client = FakeDriveClient(
        {"root": [_file(f"f{i}") for i in range(5)] + [_file("sub", FOLDER)], "sub": [_file("g")]}
    )
    tree = await walk_drive_tree(client, "root", max_files=3, max_folders=100)
    assert len(tree.files) == 3
    assert tree.truncated is True


@pytest.mark.asyncio
async def test_folder_cap_stops_descending_and_says_so() -> None:
    client = FakeDriveClient(
        {
            "root": [_file("s1", FOLDER), _file("s2", FOLDER), _file("s3", FOLDER)],
            "s1": [_file("a")],
            "s2": [_file("b")],
            "s3": [_file("c")],
        }
    )
    tree = await walk_drive_tree(client, "root", max_files=500, max_folders=2)
    assert tree.folder_ids == ["root", "s1"]
    assert [f["id"] for f in tree.files] == ["a"]
    assert tree.truncated is True


@pytest.mark.asyncio
async def test_shortcuts_are_never_followed_nor_listed() -> None:
    client = FakeDriveClient(
        {
            "root": [
                _file("a"),
                _file("short", GOOGLE_DRIVE_SHORTCUT_MIME),
                _file("sub", FOLDER),
            ],
            "sub": [_file("b"), _file("short2", GOOGLE_DRIVE_SHORTCUT_MIME)],
        }
    )
    tree = await walk_drive_tree(client, "root", max_files=500, max_folders=100)
    assert [f["id"] for f in tree.files] == ["a", "b"]
    assert "short" not in tree.folder_ids


@pytest.mark.asyncio
async def test_a_folder_seen_twice_is_walked_once() -> None:
    # Two parents pointing at one folder (legacy multi-parent files, or a loop).
    client = FakeDriveClient(
        {
            "root": [_file("s1", FOLDER), _file("s2", FOLDER)],
            "s1": [_file("shared", FOLDER)],
            "s2": [_file("shared", FOLDER)],
            "shared": [_file("x"), _file("root", FOLDER)],
        }
    )
    tree = await walk_drive_tree(client, "root", max_files=500, max_folders=100)
    assert tree.folder_ids == ["root", "s1", "s2", "shared"]
    assert [f["id"] for f in tree.files] == ["x"]
    assert tree.truncated is False


@pytest.mark.asyncio
async def test_unreadable_sub_folder_is_counted_never_fatal() -> None:
    client = FakeDriveClient(
        {"root": [_file("a"), _file("locked", FOLDER)], "locked": [_file("b")]},
        unreadable={"locked"},
    )
    tree = await walk_drive_tree(client, "root", max_files=500, max_folders=100)
    assert [f["id"] for f in tree.files] == ["a"]
    assert tree.unreadable_folders == 1
    assert "locked" in tree.folder_ids


@pytest.mark.asyncio
async def test_unreadable_root_is_an_error() -> None:
    client = FakeDriveClient({"root": []}, unreadable={"root"})
    with pytest.raises(DriveWalkError):
        await walk_drive_tree(client, "root", max_files=500, max_folders=100)


@pytest.mark.asyncio
async def test_a_cap_reached_exactly_is_not_a_cut_but_one_more_file_is() -> None:
    exact = FakeDriveClient({"root": [_file(f"f{i}") for i in range(5)]}, page_size=2)
    tree = await walk_drive_tree(exact, "root", max_files=5, max_folders=10)
    assert len(tree.files) == 5 and tree.truncated is False

    over = FakeDriveClient({"root": [_file(f"f{i}") for i in range(6)]}, page_size=2)
    tree = await walk_drive_tree(over, "root", max_files=5, max_folders=10)
    assert len(tree.files) == 5 and tree.truncated is True
