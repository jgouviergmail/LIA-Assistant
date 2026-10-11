"""Every localized approval names the exact archive without exposing private comparison data."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.export_download_schemas import (
    ExportDownloadPatch,
    ExportDownloadRequest,
)
from src.domains.agents.application.export_download_spec import EXPORT_DOWNLOAD_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.infrastructure.account_export_downloads import ExportArchiveSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", list(DRAFT_PREVIEW_LABELS))
def test_archive_preview_discloses_metadata_and_never_offers_an_editable_path(
    language: str,
) -> None:
    snapshot = ExportArchiveSnapshot(
        job_id=uuid4(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=None,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        file_size_bytes=4096,
        archive_digest="d" * 64,
    )
    patch = ExportDownloadPatch(archive_to_download=snapshot)
    draft = build_action_content(
        uuid4(),
        EXPORT_DOWNLOAD_OPERATION,
        patch,
        {"archive_to_download": None},
        patch.model_dump(mode="json"),
    )
    lines = render_application_preview(
        draft.model_dump(mode="json"), DRAFT_PREVIEW_LABELS[language], lambda value: value or ""
    )
    assert len(lines) == 3
    assert str(snapshot.job_id) in str(lines) and "4096" in str(lines)
    assert "d" * 64 not in str(lines) and "archive_digest" not in str(lines)
    prompt = build_application_edit_prompt(
        draft.model_dump(mode="json"), "Refresh the archive selection"
    )
    assert "job_id" in str(prompt) and "archive_digest" not in str(prompt)
    assert "file_path" not in str(prompt) and "expires_at" not in str(prompt)


def test_request_does_not_accept_a_path_url_or_comparison_from_the_model() -> None:
    for field in ["file_path", "url", "archive_digest", "actor_id"]:
        with pytest.raises(ValidationError):
            ExportDownloadRequest.model_validate({"job_id": str(uuid4()), field: "injected"})
