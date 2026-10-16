"""Cleanup after commit refuses changed or escaping files and keeps neighboring bytes."""

from pathlib import Path
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.infrastructure.file_transfer import LocalFileRead
from tests.support.file_clock import rewrite_later

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "obstacle", ["none", "missing", "changed", "unobserved", "escape", "unlink_failed"]
)
async def test_cleanup_removes_only_the_observed_owned_file(monkeypatch, tmp_path, obstacle):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, space = uuid4(), uuid4()
    scope = tmp_path / str(owner) / str(space)
    scope.mkdir(parents=True)
    path, neighbor = scope / "selected.txt", scope.parent / "kept.txt"
    path.write_bytes(b"data")
    neighbor.write_bytes(b"keep")
    reader = LocalFileRead.open(path)
    digest = reader.identity_digest
    await reader.close()
    filename = "selected.txt"
    if obstacle == "missing":
        path.unlink()
    elif obstacle == "changed":
        rewrite_later(path, b"new!")
    elif obstacle == "unobserved":
        digest = None
    elif obstacle == "escape":
        filename = "../kept.txt"
    elif obstacle == "unlink_failed":
        original = Path.unlink

        def refuse(self, *args, **kwargs):
            if self == path:
                raise OSError("Controlled cleanup failure")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", refuse)
    cleaned = await cleanup_deleted_document_file(owner, space, filename, digest)
    assert cleaned is (obstacle in {"none", "missing"})
    assert path.exists() is (obstacle not in {"none", "missing"})
    assert neighbor.read_bytes() == b"keep"
