"""Post-commit cleanup preserves sibling scopes and refuses linked directories."""

from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.rag_spaces.space_deletion import cleanup_space_files

pytestmark = pytest.mark.unit


async def test_cleanup_removes_only_selected_directory_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    actor, selected, sibling = uuid4(), uuid4(), uuid4()
    target, other = tmp_path / str(actor) / str(selected), tmp_path / str(actor) / str(sibling)
    target.mkdir(parents=True)
    other.mkdir()
    (other / "keep.txt").write_text("Unselected source", encoding="utf-8")
    assert await cleanup_space_files(actor, selected)
    assert (
        not target.exists()
        and (other / "keep.txt").read_text(encoding="utf-8") == "Unselected source"
    )
    assert await cleanup_space_files(actor, selected)


@pytest.mark.parametrize("link_kind", ["symlink", "junction_like"])
async def test_symlinked_scope_cannot_delete_another_space(tmp_path, monkeypatch, link_kind):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    actor, selected = uuid4(), uuid4()
    target, other = tmp_path / str(actor) / str(selected), tmp_path / "other-account"
    target.parent.mkdir()
    other.mkdir()
    marker = other / "keep.txt"
    marker.write_text("Must survive", encoding="utf-8")
    try:
        target.symlink_to(other, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not grant directory symlink creation; exercised on Linux CI")
    if link_kind == "junction_like":
        # Windows junctions resolve to the linked path while is_symlink is false.
        # Exercise that behavior on the same real linked directory on every OS.
        monkeypatch.setattr(type(target), "is_symlink", lambda self: False)
    assert not await cleanup_space_files(actor, selected)
    assert marker.read_text(encoding="utf-8") == "Must survive"
