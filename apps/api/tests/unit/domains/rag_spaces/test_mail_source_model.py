"""The mail source's shape (ADR-262): table, provenance columns, one lifecycle.

The mail source mirrors the Drive source — same durable-job columns, same
sync lifecycle — and a document knows which thread it renders. The schema
the API publishes carries the same fields as the row.
"""

from __future__ import annotations

import pytest

from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentSourceType,
    RAGDriveSource,
    RAGDriveSyncStatus,
    RAGMailSource,
    RAGSourceSyncStatus,
    RAGSpace,
)
from src.domains.rag_spaces.schemas import (
    RAGDocumentResponse,
    RAGMailSourceResponse,
    RAGSpaceDetailResponse,
)

pytestmark = pytest.mark.unit

DURABLE_JOB_COLUMNS = {"lease_expires_at", "heartbeat_at", "attempts", "worker_id"}


def test_mail_source_table_and_columns() -> None:
    columns = set(RAGMailSource.__table__.columns.keys())
    assert RAGMailSource.__tablename__ == "rag_mail_sources"
    assert {
        "space_id",
        "user_id",
        "label_id",
        "label_name",
        "sync_status",
        "last_sync_at",
        "thread_count",
        "synced_thread_count",
        "last_history_id",
        "error_message",
    } <= columns
    # The reaper reasons about every synced source the same way (audit F001).
    assert DURABLE_JOB_COLUMNS <= columns
    assert DURABLE_JOB_COLUMNS <= set(RAGDriveSource.__table__.columns.keys())


def test_one_label_per_space_and_a_lease_scan_index() -> None:
    indexes = {index.name: index for index in RAGMailSource.__table__.indexes}
    unique = indexes["uq_rag_mail_sources_space_label"]
    assert unique.unique is True
    assert [column.name for column in unique.columns] == ["space_id", "label_id"]
    assert "ix_rag_mail_sources_status_lease" in indexes


def test_a_document_knows_the_thread_it_renders() -> None:
    columns = set(RAGDocument.__table__.columns.keys())
    assert {"mail_source_id", "mail_thread_id", "mail_last_message_at"} <= columns
    fk = next(fk for fk in RAGDocument.__table__.foreign_keys if fk.parent.name == "mail_source_id")
    # Unlinking a label keeps the documents (SET NULL), like a Drive folder.
    assert fk.ondelete == "SET NULL"
    assert RAGDocumentSourceType.MAIL == "mail"


def test_one_sync_lifecycle_for_every_synced_source() -> None:
    assert RAGSourceSyncStatus is RAGDriveSyncStatus
    assert RAGMailSource.sync_status.default.arg == RAGSourceSyncStatus.IDLE  # type: ignore[union-attr]


def test_the_space_owns_its_mail_sources() -> None:
    relationship = RAGSpace.__mapper__.relationships["mail_sources"]
    assert relationship.cascade.delete_orphan is True


def test_the_api_shape_mirrors_the_row() -> None:
    assert set(RAGMailSourceResponse.model_fields) == {
        "id",
        "label_id",
        "label_name",
        "sync_status",
        "last_sync_at",
        "thread_count",
        "synced_thread_count",
        "error_message",
        "created_at",
    }
    assert RAGSpaceDetailResponse.model_fields["mail_sources"].default_factory is list
    assert RAGDocumentResponse.model_fields["mail_thread_id"].default is None
