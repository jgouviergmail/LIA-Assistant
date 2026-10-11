"""An updated Drive file is not discarded while its replacement download is uncertain."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.rag_spaces import drive_ingest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("download", ["failed", "empty"])
async def test_replacement_download_does_not_remove_the_old_indexed_document(download):
    existing = MagicMock(drive_modified_time=datetime(2026, 9, 1, tzinfo=UTC))
    repository = MagicMock()
    repository.get_by_drive_file_id = AsyncMock(return_value=existing)
    repository.count_for_space = AsyncMock(return_value=0)
    fetch = (
        AsyncMock(side_effect=OSError("controlled provider failure"))
        if download == "failed"
        else AsyncMock(return_value=(b"", ".pdf", "application/pdf"))
    )
    with (
        patch.object(drive_ingest, "RAGDocumentRepository", return_value=repository),
        patch.object(drive_ingest, "_download", fetch),
        patch.object(drive_ingest, "discard_document", AsyncMock()) as discard,
        patch.object(drive_ingest, "create_pending_document", AsyncMock()) as create,
    ):
        result = await drive_ingest.ingest_drive_file(
            AsyncMock(),
            object(),
            space_id=uuid4(),
            source_id=uuid4(),
            user_id=uuid4(),
            drive_file={
                "id": "existing",
                "name": "Current.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-10-01T00:00:00Z",
            },
        )
    assert result.outcome == ("failed" if download == "failed" else "skipped")
    discard.assert_not_awaited()
    create.assert_not_awaited()
