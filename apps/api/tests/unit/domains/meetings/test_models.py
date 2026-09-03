"""Unit tests for the meetings models (ADR-258).

Pins the lifecycle vocabulary, the name/value trap of ``native_enum=False``
columns (raw predicates must use the member NAME), and the database-level
"one recording per user" contract.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Enum as SAEnum

from src.domains.meetings.models import (
    ACTIVE_RECORDING_STATUS_SQL,
    Meeting,
    MeetingAudioFormat,
    MeetingIndexState,
    MeetingPreference,
    MeetingStage,
    MeetingStatus,
    MeetingSttEnginePreference,
    MeetingSttProvider,
    MeetingTemplate,
)

pytestmark = pytest.mark.unit


def test_lifecycle_vocabulary_is_exactly_the_documented_one() -> None:
    assert {s.value for s in MeetingStatus} == {
        "recording",
        "interrupted",
        "stopped",
        "processing",
        "ready",
        "failed",
    }
    assert {s.value for s in MeetingStage} == {
        "normalizing",
        "transcribing",
        "synthesizing",
        "indexing",
    }
    assert {f.value for f in MeetingAudioFormat} == {"pcm_s16le_16", "webm_opus", "ogg_opus"}
    assert {p.value for p in MeetingSttProvider} == {"elevenlabs", "openai", "local"}
    assert {p.value for p in MeetingSttEnginePreference} == {"auto", "remote", "local"}
    assert {s.value for s in MeetingIndexState} == {"pending", "indexed", "error", "disabled"}


def test_enum_columns_store_member_names_so_predicates_use_names() -> None:
    # native_enum=False stores 'RECORDING', not 'recording' — the raw-SQL
    # predicate of the partial unique index must say the same thing.
    status_type = Meeting.__table__.c.status.type
    assert isinstance(status_type, SAEnum)
    assert status_type.native_enum is False
    assert ACTIVE_RECORDING_STATUS_SQL == "status = 'RECORDING'"
    assert MeetingStatus.RECORDING.name == "RECORDING"


def test_one_live_recording_per_user_is_a_database_contract() -> None:
    indexes = {index.name: index for index in Meeting.__table__.indexes}
    unique = indexes["uq_meetings_one_recording_per_user"]
    assert unique.unique is True
    assert [column.name for column in unique.columns] == ["user_id"]
    assert str(unique.dialect_options["postgresql"]["where"]) == ACTIVE_RECORDING_STATUS_SQL


def test_reaper_scans_have_their_indexes() -> None:
    names = {index.name for index in Meeting.__table__.indexes}
    assert {"ix_meetings_status_lease", "ix_meetings_status_last_segment"} <= names


def test_rag_document_link_survives_document_deletion() -> None:
    fk = next(fk for fk in Meeting.__table__.c.rag_document_id.foreign_keys)
    assert fk.ondelete == "SET NULL"
    user_fk = next(fk for fk in Meeting.__table__.c.user_id.foreign_keys)
    assert user_fk.ondelete == "CASCADE"


def test_templates_and_preferences_are_per_user() -> None:
    template_indexes = {index.name: index for index in MeetingTemplate.__table__.indexes}
    default_index = template_indexes["uq_meeting_templates_one_default_per_user"]
    assert default_index.unique is True
    assert MeetingPreference.__table__.c.user_id.unique is True
    assert MeetingPreference.__table__.c.keep_audio_hours.default.arg == 0
