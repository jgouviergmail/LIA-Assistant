"""SMS evidence keeps the source's date and identity uncertainty."""

from datetime import timedelta
from uuid import UUID

import pytest

from src.domains.shared.discussion_sources import SourceKey
from src.domains.sms.discussion_source import sms_evidence
from src.domains.sms.read_schemas import SmsView
from tests.unit.domains.proactive_discussions.test_source_authority import NOW, request

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("date_kind", ["captured", "unknown"])
def test_capture_time_does_not_become_received_event(date_kind: str) -> None:
    row = SmsView(
        id=UUID(int=10),
        sender="+33600000000",
        display_name="+33600000000",
        body="Fictional message",
        received_at=NOW - timedelta(hours=1),
        date_kind=date_kind,
        origin="iphone",
    )
    result = sms_evidence(row, request(SourceKey.SMS))
    assert result.occurred_at is None
    assert result.category == date_kind
    assert result.assertion == "reported"


def test_message_version_covers_unclipped_body_and_literal_sender() -> None:
    row = SmsView(
        id=UUID(int=10),
        sender="+33600000000",
        display_name="Untrusted resolved name",
        body="Message A",
        received_at=NOW,
        date_kind="received",
        origin="iphone",
    )
    scope = request(SourceKey.SMS).model_copy(update={"item_max_chars": 3})
    first = sms_evidence(row, scope)
    changed = sms_evidence(row.model_copy(update={"body": "Message B"}), scope)
    assert first.version != changed.version
    assert first.subject_id == changed.subject_id
    assert first.occurred_at == NOW and first.excerpt_truncated
    assert "Untrusted resolved name" not in first.excerpt
    assert first.usage_nuance and "identity" in first.usage_nuance


def test_sender_equivalence_reuses_native_archive_policy() -> None:
    row = SmsView(
        id=UUID(int=10),
        sender="+33 6 00 00 00 00",
        display_name="Literal",
        body="Fictional message",
        received_at=NOW,
        date_kind="received",
        origin="iphone",
    )
    scope = request(SourceKey.SMS)
    first = sms_evidence(row, scope)
    second = sms_evidence(row.model_copy(update={"sender": "+33600000000"}), scope)
    assert first.subject_id == second.subject_id
