"""Provider DTO projections retain longitudinal meaning and discard unrelated payload trees."""

from datetime import UTC, date, datetime

import pytest

from src.domains.connectors.discussion_projections import (
    calendar_evidence,
    contact_evidence,
    email_evidence,
    task_evidence,
)
from src.domains.proactive_discussions.contextualization.patterns import qualify_pattern

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


def test_graph_monthly_declaration_keeps_its_native_schema_without_inventing_an_rrule() -> None:
    raw = {
        "id": "graph-monthly",
        "summary": "Fictional monthly appointment",
        "start": {"dateTime": "2026-10-21T09:00:00Z"},
        "end": {"dateTime": "2026-10-21T10:00:00Z"},
        "recurrence_pattern": {
            "pattern": {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": 21},
            "range": {"type": "noEnd", "startDate": "2026-01-21"},
        },
    }
    fact = calendar_evidence(raw, account="fictional-graph", now=NOW, chars=4000)
    assert fact.native_recurrence is not None and fact.recurrence_rule is None
    pattern = qualify_pattern((fact,), coverage=(), timezone="UTC")
    assert pattern.basis == "declared" and pattern.frequency == "monthly"


def test_moved_calendar_exception_keeps_original_instant_and_never_claims_attendance() -> None:
    item = calendar_evidence(
        {
            "id": "instance-new",
            "summary": "Fictional doctor appointment",
            "recurringEventId": "series-1",
            "originalStartTime": {"dateTime": "2026-10-19T09:00:00+02:00"},
            "start": {"dateTime": "2026-10-20T10:00:00+02:00"},
            "end": {"dateTime": "2026-10-20T11:00:00+02:00"},
            "recurrence": ["RRULE:FREQ=MONTHLY"],
            "status": "confirmed",
            "payload": {"secret": "never include"},
        },
        account="google:fictional-account:calendar-1",
        now=NOW,
        chars=4000,
    )
    assert item.series_id == "series-1" and item.original_start == datetime(
        2026, 10, 19, 7, tzinfo=UTC
    )
    assert item.assertion == "planned" and item.occurrence_state == "scheduled"
    assert item.recurrence_rule == "RRULE:FREQ=MONTHLY" and "secret" not in item.excerpt


def test_all_day_calendar_and_task_due_are_civil_dates_without_fabricated_midnight_events() -> None:
    event = calendar_evidence(
        {
            "id": "day",
            "summary": "Fictional trip",
            "start": {"date": "2026-10-21"},
            "end": {"date": "2026-10-22"},
        },
        account="fictional",
        now=NOW,
        chars=4000,
    )
    task = task_evidence(
        {
            "id": "task",
            "title": "Fictional task",
            "due": "2026-10-21T00:00:00Z",
            "status": "completed",
        },
        account="fictional",
        now=NOW,
        chars=4000,
    )
    assert event.planned_date == date(2026, 10, 21) and event.occurred_at is None
    assert task.planned_date == date(2026, 10, 21) and task.occurred_at is None
    assert task.occurrence_state == "reported_complete" and task.assertion == "reported"


def test_email_only_projects_readable_content_without_smtp_or_attachments() -> None:
    item = email_evidence(
        {
            "id": "mail",
            "subject": "Fictional recital",
            "from": "Alice <fictional@example.test>",
            "internalDate": "1792483200000",
            "body": "The recital starts Friday",
            "snippet": "Recital",
            "payload": {"body": {"data": "base64-secret"}},
            "attachments": [{"secret": "attachment"}],
        },
        account="fictional",
        now=NOW,
        chars=4000,
    )
    assert (
        "recital starts Friday" in item.excerpt
        and "base64" not in item.excerpt
        and "attachment" not in item.excerpt
    )
    assert item.assertion == "reported" and item.recorded_at is not None


def test_contacts_preserve_partial_birthday_and_do_not_merge_homonyms() -> None:
    data = {
        "resourceName": "people/1",
        "names": [{"displayName": "Fictional Alice"}],
        "birthdays": [{"date": {"month": 10, "day": 24}}],
        "photos": [{"url": "private-image"}],
    }
    first = contact_evidence(data, account="fictional", now=NOW, chars=4000)
    second = contact_evidence(
        {**data, "resourceName": "people/2"}, account="fictional", now=NOW, chars=4000
    )
    assert first.subject_id != second.subject_id and "private-image" not in first.excerpt
    assert '"month":10' in first.excerpt and first.occurred_at is None
