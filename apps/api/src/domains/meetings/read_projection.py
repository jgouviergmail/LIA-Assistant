"""Private large content is explicit JSON fragments under a stable revision."""

import hashlib
from datetime import UTC, datetime

from src.core.exceptions import ResourceConflictError
from src.infrastructure.meeting_reads import MeetingReadPage, MeetingReadView, TemplateReadView

MEETING_CONTENT_FIELDS = {"report", "transcript", "template_snapshot"}
MEETING_WITHHELD_FIELDS = {"last_error_message"}
MEETING_LIMIT_FIELDS = {
    "segment_seconds",
    "segment_max_seconds",
    "segment_max_bytes",
    "max_duration_minutes",
    "silence_prompt_minutes",
}
MEETING_SUMMARY_FIELDS = {
    "id",
    "status",
    "stage",
    "title",
    "started_at",
    "stopped_at",
    "audio_duration_seconds",
    "participants_count",
    "action_items_count",
    "index_state",
    "stt_provider",
    "total_cost_eur",
    "last_error_code",
    "template_ref",
    "template_name",
    "template_selection",
    "source_meeting_id",
}
MEETING_DETAIL_FIELDS = {
    "id",
    "status",
    "stage",
    "started_at",
    "stopped_at",
    "last_segment_at",
    "client_timezone",
    "audio_format",
    "segment_count",
    "audio_duration_seconds",
    "audio_gaps",
    "audio_kept_until",
    "audio_purged_at",
    "location_lat",
    "location_lon",
    "location_label",
    "calendar_event_id",
    "stt_provider",
    "stt_model",
    "stt_detected_language",
    "stt_diarized",
    "stt_cost_eur",
    "synthesis_model",
    "synthesis_tokens_in",
    "synthesis_tokens_out",
    "synthesis_tokens_cache",
    "synthesis_cost_eur",
    "template_selection_usage",
    "total_cost_eur",
    "has_transcript",
    "report_is_edited",
    "report_edited_at",
    "index_state",
    "indexed_at",
    "email_sent_at",
    "last_error_code",
    "attempts",
    "max_attempts",
    "worker_stale",
    "template_ref",
    "template_name",
    "template_selection",
    "template_selection_reason",
    "source_meeting_id",
    "derived_count",
}


def content_page(
    view: MeetingReadView | TemplateReadView,
    text: str,
    offset: int,
    characters: int,
    expected_digest: str | None,
) -> MeetingReadPage:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if expected_digest is not None and expected_digest != digest:
        raise ResourceConflictError("meeting_content", detail={"error_code": "STALE_STATE"})
    chunk = text[offset : offset + characters]
    end = offset + len(chunk)
    return MeetingReadPage(
        view=view,
        observed_at=datetime.now(UTC),
        total=len(text),
        offset=offset,
        next_offset=end if chunk and end < len(text) else None,
        text=chunk,
        source_digest=digest,
        content_format="json_fragment",
    )
