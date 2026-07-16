"""RAGDocument / RAGDriveSource carry the durable-job columns (audit F001, T1).

Model-level guard (no DB needed): asserts the lease/heartbeat/attempts/worker_id
columns and the reaper scan index are declared on both entities, so a later edit
cannot silently drop the durability substrate. The from-scratch Alembic replay +
``alembic check`` prove the DB side; this pins the ORM side.
"""

from __future__ import annotations

import pytest

from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource

_DURABILITY_COLUMNS = {"lease_expires_at", "heartbeat_at", "attempts", "worker_id"}


@pytest.mark.parametrize("model", [RAGDocument, RAGDriveSource])
def test_durability_columns_declared(model) -> None:
    cols = set(model.__table__.columns.keys())
    assert _DURABILITY_COLUMNS <= cols, f"{model.__name__} missing {_DURABILITY_COLUMNS - cols}"


@pytest.mark.parametrize("model", [RAGDocument, RAGDriveSource])
def test_attempts_is_non_nullable_with_default(model) -> None:
    col = model.__table__.columns["attempts"]
    assert col.nullable is False
    assert col.server_default is not None  # server_default="0" → safe backfill


def test_reaper_scan_indexes_declared() -> None:
    doc_indexes = {ix.name for ix in RAGDocument.__table__.indexes}
    src_indexes = {ix.name for ix in RAGDriveSource.__table__.indexes}
    assert "ix_rag_documents_status_lease" in doc_indexes
    assert "ix_rag_drive_sources_status_lease" in src_indexes
