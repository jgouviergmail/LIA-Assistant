"""A stored document's exact path: one check, refused through a link, run off the loop (AC-035).

Three callers — the post-commit cleanup, the move staging and the bookmark
deletion — each carried their own copy of the same check: no link on the account,
the space or the file, and no filename leaving its space. It is written once now,
and the two callers that only observe a file run it, and their open, in a worker
thread.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.domains.agents.application import bookmark_delete_scope
from src.domains.rag_spaces.document_access import owned_document_path
from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.domains.rag_spaces.models import RAGDocument
from src.infrastructure.file_transfer import LocalFileRead

pytestmark = pytest.mark.unit


@pytest.fixture
def space(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[UUID, UUID, Path]:
    """An owner, one of their spaces, and the space's directory holding ``stored.txt``."""
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, space_id = uuid4(), uuid4()
    scope = tmp_path / str(owner) / str(space_id)
    scope.mkdir(parents=True)
    (scope / "stored.txt").write_bytes(b"data")
    return owner, space_id, scope


def _link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        pytest.skip("Host does not grant symlink creation; exercised on Linux CI")


def test_the_stored_file_is_its_exact_path(space: tuple[UUID, UUID, Path]) -> None:
    owner, space_id, scope = space

    assert owned_document_path(owner, space_id, "stored.txt") == scope / "stored.txt"


def test_a_file_already_gone_keeps_its_exact_path(space: tuple[UUID, UUID, Path]) -> None:
    owner, space_id, scope = space

    assert owned_document_path(owner, space_id, "gone.txt") == scope / "gone.txt"


@pytest.mark.parametrize("filename", ["../stored.txt", "../../escape.txt", "nested/../../x.txt"])
def test_a_filename_leaving_its_space_is_refused(
    space: tuple[UUID, UUID, Path], filename: str
) -> None:
    owner, space_id, _ = space

    assert owned_document_path(owner, space_id, filename) is None


@pytest.mark.parametrize("hidden", [False, True], ids=["symlink", "junction_like"])
@pytest.mark.parametrize("linked", ["account", "space", "file"])
def test_a_link_anywhere_on_the_path_is_refused(
    space: tuple[UUID, UUID, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    linked: str,
    hidden: bool,
) -> None:
    owner, space_id, scope = space
    elsewhere = tmp_path / "elsewhere"
    foreign_space = elsewhere / str(uuid4())
    foreign_space.mkdir(parents=True)
    (foreign_space / "stored.txt").write_bytes(b"another account's file")
    if linked == "file":
        _link(scope / "linked.txt", foreign_space / "stored.txt")
        located = (owner, space_id, "linked.txt")
    elif linked == "space":
        linked_space = uuid4()
        _link(scope.parent / str(linked_space), foreign_space)
        located = (owner, linked_space, "stored.txt")
    else:
        linked_owner = uuid4()
        _link(tmp_path / str(linked_owner), elsewhere)
        located = (linked_owner, UUID(foreign_space.name), "stored.txt")
    if hidden:
        # A Windows junction is no symlink to is_symlink: the resolved paths refuse it.
        monkeypatch.setattr(Path, "is_symlink", lambda path: False)

    assert owned_document_path(*located) is None


def test_a_link_to_a_file_of_the_same_space_is_refused(space: tuple[UUID, UUID, Path]) -> None:
    # Its resolved path stays inside the space: only the link check refuses it.
    owner, space_id, scope = space
    _link(scope / "linked.txt", scope / "stored.txt")

    assert owned_document_path(owner, space_id, "linked.txt") is None


@pytest.fixture
def calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """The thread of every path check and file open made under ``tmp_path``."""
    seen: list[tuple[str, int]] = []
    for name in ("is_symlink", "resolve"):
        real = getattr(Path, name)

        def recording(
            path: Path, *args: Any, _real: Any = real, _name: str = name, **kw: Any
        ) -> Any:
            if path.is_relative_to(tmp_path):
                seen.append((_name, threading.get_ident()))
            return _real(path, *args, **kw)

        monkeypatch.setattr(Path, name, recording)
    real_open = LocalFileRead.open

    def recording_open(cls: type[LocalFileRead], path: Path) -> LocalFileRead:
        seen.append(("open", threading.get_ident()))
        return real_open(path)

    monkeypatch.setattr(LocalFileRead, "open", classmethod(recording_open))
    return seen


async def test_a_cleanup_checks_and_opens_the_file_off_the_loop(
    space: tuple[UUID, UUID, Path], calls: list[tuple[str, int]]
) -> None:
    owner, space_id, scope = space
    reader = await LocalFileRead.async_open(scope / "stored.txt")
    digest = reader.identity_digest
    await reader.close()
    calls.clear()

    assert await cleanup_deleted_document_file(owner, space_id, "stored.txt", digest)

    seen = list(calls)
    assert {"is_symlink", "resolve", "open"} <= {name for name, _ in seen}
    assert threading.get_ident() not in {thread for _, thread in seen}
    assert not (scope / "stored.txt").exists()


async def test_a_bookmark_deletion_observes_the_file_off_the_loop(
    space: tuple[UUID, UUID, Path], calls: list[tuple[str, int]]
) -> None:
    owner, space_id, _ = space
    document = RAGDocument(id=uuid4(), user_id=owner, space_id=space_id, filename="stored.txt")

    observed = await bookmark_delete_scope._file(owner, document)

    seen = list(calls)
    assert {"is_symlink", "resolve", "open"} <= {name for name, _ in seen}
    assert threading.get_ident() not in {thread for _, thread in seen}
    assert observed.stored_filename == "stored.txt" and observed.file_digest is not None
