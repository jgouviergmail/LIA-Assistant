"""Every locale discloses the complete export scope without model-editable authority."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.management_export_schemas import (
    ManagementExportPatch,
    ManagementExportRequest,
    ManagementExportSnapshot,
)
from src.domains.agents.application.management_export_spec import (
    INTEREST_EXPORT_OPERATION,
    JOURNAL_EXPORT_OPERATION,
    MEMORY_EXPORT_OPERATION,
)
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.interests.management_export import InterestExportRecord
from src.domains.memories.management_export import MemoryCSVExportRecord
from src.domains.memories.schemas import MemoryResponse

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", list(DRAFT_PREVIEW_LABELS))
@pytest.mark.parametrize("collection", ["interests", "memories", "journals"])
def test_export_preview_and_editor_are_complete_bounded_and_do_not_disclose_comparison(
    language: str,
    collection: str,
) -> None:
    selected = ManagementExportSnapshot(
        format="csv",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        selected_count=603,
        selection_digest="d" * 64,
    )
    patch = ManagementExportPatch(management_export=selected)
    draft = build_action_content(
        uuid4(),
        {
            "interests": INTEREST_EXPORT_OPERATION,
            "memories": MEMORY_EXPORT_OPERATION,
            "journals": JOURNAL_EXPORT_OPERATION,
        }[collection],
        patch,
        {"management_export": None},
        patch.model_dump(mode="json"),
    )
    lines = render_application_preview(
        draft.model_dump(mode="json"), DRAFT_PREVIEW_LABELS[language], lambda value: value or ""
    )
    assert len(lines) == 3 and "603" in str(lines) and "CSV" in str(lines)
    assert "d" * 64 not in str(lines)
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Use JSON")
    assert "format" in str(prompt) and "selection_digest" not in str(prompt)
    assert "observed_at" not in str(prompt) and "603" not in str(prompt)


@pytest.mark.parametrize(
    "field", ["actor_id", "scope", "url", "selection_digest", "observed_at", "selected_count"]
)
def test_model_cannot_select_other_accounts_or_replace_comparison(field: str) -> None:
    with pytest.raises(ValidationError):
        ManagementExportRequest.model_validate({"format": "json", field: "injected"})


def test_source_export_vocabulary_requires_review_for_new_public_fields() -> None:
    assert set(InterestExportRecord.model_fields) == {
        "id",
        "topic",
        "category",
        "status",
        "positive_signals",
        "negative_signals",
        "weight",
        "last_mentioned_at",
        "last_notified_at",
        "created_at",
    }


def test_memory_export_privacy_and_columns_require_review_when_source_schemas_grow() -> None:
    assert set(MemoryCSVExportRecord.model_fields) == {
        "id",
        "content",
        "category",
        "emotional_weight",
        "trigger_topic",
        "usage_nuance",
        "importance",
        "pinned",
        "usage_count",
        "last_accessed_at",
        "created_at",
        "updated_at",
    }
    assert set(MemoryResponse.model_fields) == set(MemoryCSVExportRecord.model_fields) | {
        "context_biometric",
        "purge_risk",
        "retention_score",
    }


def test_journal_export_inherits_public_entry_fields_and_reviews_portrait_shape() -> None:
    from src.domains.journals.management_export import JOURNAL_CSV_FIELDS, StoredJournalPortrait
    from src.domains.journals.schemas import JournalEntryResponse

    assert set(JOURNAL_CSV_FIELDS) == set(JournalEntryResponse.model_fields)
    assert set(JournalEntryResponse.model_fields) == {
        "id",
        "theme",
        "level",
        "title",
        "content",
        "mood",
        "status",
        "source",
        "personality_code",
        "char_count",
        "confidence",
        "evidence_count",
        "contradiction_count",
        "injection_count",
        "last_injected_at",
        "created_at",
        "updated_at",
        "search_hints",
        "revision",
    }
    assert set(StoredJournalPortrait.model_fields) == {"full", "brief", "compiled_at", "sources"}
