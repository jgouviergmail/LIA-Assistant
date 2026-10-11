"""Private content reads are explicitly paged and cannot cross source revisions."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"view": "detail"},
        {"view": "list", "meeting_id": str(uuid4())},
        {"view": "active", "offset": 1},
        {"view": "report", "meeting_id": str(uuid4()), "offset": 1},
        {"view": "generated_report", "meeting_id": str(uuid4()), "offset": 1},
        {"view": "list", "limit": True},
        {"view": "list", "user_id": str(uuid4())},
    ],
)
def test_invalid_read_selections_are_refused(payload: object) -> None:
    from src.infrastructure.meeting_reads import MeetingReadInput

    with pytest.raises(ValidationError):
        MeetingReadInput.model_validate(payload)


def test_utf8_content_pages_are_bounded_explicit_and_lossless() -> None:
    from src.domains.meetings.read_projection import content_page

    text = '{"text":"' + "réunion 中文🎙️" * 1700 + '"}'
    first = content_page("report", text, 0, 4000, None)
    assert first.text == text[:4000] and first.next_offset == 4000
    assert first.content_format == "json_fragment" and first.total == len(text)
    assert len(first.model_dump_json().encode("utf-8")) < 64000
    second = content_page("report", text, 4000, 4000, first.source_digest)
    assert first.text + second.text == text[:8000]


def test_changed_content_never_continues_an_old_revision() -> None:
    from src.core.exceptions import ResourceConflictError
    from src.domains.meetings.read_projection import content_page

    first = content_page("transcript", "original words", 0, 5, None)
    with pytest.raises(ResourceConflictError):
        content_page("transcript", "edited words", 5, 5, first.source_digest)


def test_new_detail_fields_require_explicit_content_or_metadata_classification() -> None:
    from src.domains.meetings.read_projection import (
        MEETING_CONTENT_FIELDS,
        MEETING_DETAIL_FIELDS,
        MEETING_WITHHELD_FIELDS,
    )
    from src.domains.meetings.schemas import MeetingDetailResponse

    assert (
        set(MeetingDetailResponse.model_fields)
        == MEETING_DETAIL_FIELDS | MEETING_CONTENT_FIELDS | MEETING_WITHHELD_FIELDS
    )
    assert not MEETING_DETAIL_FIELDS & MEETING_CONTENT_FIELDS
    assert "last_error_message" in MEETING_WITHHELD_FIELDS


def test_new_summary_fields_require_review_before_they_enter_llm_context() -> None:
    from src.domains.meetings.read_projection import MEETING_SUMMARY_FIELDS
    from src.domains.meetings.schemas import MeetingSummary

    assert set(MeetingSummary.model_fields) == MEETING_SUMMARY_FIELDS


def test_read_tools_are_registered_and_offered_to_both_execution_modes() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_read_catalogue import (
        MEETING_READ_MANIFEST,
        MEETING_TEMPLATE_READ_MANIFEST,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    names = {"get_lia_meetings_tool", "get_lia_meeting_templates_tool"}
    assert names <= set(APPLICATION_TOOL_NAMES)
    assert names <= {operation.tool_name for operation in NATIVE_OPERATIONS}
    for manifest in (MEETING_READ_MANIFEST, MEETING_TEMPLATE_READ_MANIFEST):
        assert manifest.execution_modes == {"pipeline", "react"}
        assert manifest.mutation_policy == "read"


def test_meeting_limits_are_an_explicit_readonly_unpaginated_view() -> None:
    from src.infrastructure.meeting_reads import MeetingReadInput

    assert MeetingReadInput(view="limits").meeting_id is None
    with pytest.raises(ValidationError):
        MeetingReadInput(view="limits", offset=1)
    with pytest.raises(ValidationError):
        MeetingReadInput(view="limits", meeting_id=uuid4())


def test_new_published_meeting_limits_require_explicit_context_classification() -> None:
    from src.domains.meetings.read_projection import MEETING_LIMIT_FIELDS
    from src.domains.meetings.schemas import MeetingLimits

    assert set(MeetingLimits.model_fields) == MEETING_LIMIT_FIELDS
