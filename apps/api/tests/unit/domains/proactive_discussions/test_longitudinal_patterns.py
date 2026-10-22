"""A schedule is not attendance; unknown history is never an isolated visit."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from src.domains.proactive_discussions.context_store.admission import observation_key
from src.domains.proactive_discussions.context_store.preparation import prepare_item
from src.domains.proactive_discussions.context_store.schemas import ContextProposal
from src.domains.proactive_discussions.contextualization.patterns import qualify_pattern
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey, SourceSnapshot

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 20, tzinfo=UTC)


def test_one_plain_appointment_cannot_be_persisted_as_a_declared_monthly_pattern() -> None:
    item = event(date(2026, 9, 20))
    proposal = ContextProposal(
        kind="pattern",
        summary="Fictional monthly follow-up",
        qualification="declared",
        anchor=item.reference,
        references=(item.reference,),
    )
    with pytest.raises(ValueError, match="recurrence"):
        prepare_item(
            UUID(int=1),
            proposal,
            {item.reference: item},
            generation=1,
            revision=1,
            now=NOW,
            timezone="UTC",
        )


def test_multi_person_episode_preserves_separate_subjects_instead_of_merging_them() -> None:
    first, second = event(date(2026, 9, 20), subject_id="person:a"), event(
        date(2026, 9, 21), subject_id="person:b"
    )
    proposal = ContextProposal(
        kind="episode",
        summary="Fictional shared preparation involving two people",
        qualification="planned",
        anchor=first.reference,
        references=(first.reference, second.reference),
    )
    item = prepare_item(
        UUID(int=1),
        proposal,
        {first.reference: first, second.reference: second},
        generation=1,
        revision=1,
        now=NOW,
        timezone="UTC",
    )
    assert {proof.subject_id for proof in item.proofs} == {"person:a", "person:b"}


def event(day: date, **changes: object) -> DiscussionEvidence:
    return DiscussionEvidence.model_validate(
        {
            "source": "calendar",
            "source_account": "a",
            "object_id": day.isoformat(),
            "reference": f"calendar:{day}",
            "version": "v1",
            "observed_at": NOW,
            "occurred_at": datetime.combine(day, datetime.min.time(), UTC),
            "excerpt": "Fictional appointment",
            "assertion": "planned",
            "subject_id": "self",
            **changes,
        }
    )


def coverage(
    items: tuple[DiscussionEvidence, ...], *, complete: bool = True
) -> tuple[SourceSnapshot, ...]:
    return (
        SourceSnapshot(
            source=SourceKey.CALENDAR,
            owner_id=UUID(int=1),
            status="ok" if complete else "truncated",
            read_at=NOW,
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=NOW + timedelta(days=1),
            complete=complete,
            items=items,
        ),
    )


def test_one_event_with_unknown_history_is_not_an_isolated_or_regular_visit() -> None:
    item = event(date(2026, 9, 20))
    result = qualify_pattern((item,), coverage=(), timezone="UTC")
    assert result.basis == "insufficient" and result.frequency == "unknown"
    assert result.completion == "not_established"


def test_civil_month_variation_is_recognized_without_inventing_attendance_or_a_rule() -> None:
    items = tuple(event(day) for day in (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)))
    result = qualify_pattern(items, coverage=coverage(items), timezone="UTC")
    assert result.basis == "observed" and result.frequency == "monthly"
    assert result.count == 3 and result.completion == "not_established"
    assert (
        qualify_pattern(items, coverage=coverage(items, complete=False), timezone="UTC").basis
        == "possible"
    )


def test_duplicate_reads_and_other_people_do_not_prove_a_personal_pattern() -> None:
    item = event(date(2026, 9, 20))
    assert qualify_pattern((item, item, item), coverage=(), timezone="UTC").count == 1
    items = (item, event(date(2026, 8, 20), subject_id="child"), event(date(2026, 7, 20)))
    assert qualify_pattern(items, coverage=coverage(items), timezone="UTC").basis == "insufficient"


def test_declared_monthly_schedule_is_distinct_from_observed_or_cancelled_occurrences() -> None:
    item = event(date(2026, 9, 20), recurrence_rule="RRULE:FREQ=MONTHLY;INTERVAL=1", series_id="s")
    result = qualify_pattern((item,), coverage=(), timezone="UTC")
    assert result.basis == "declared" and result.frequency == "monthly"
    assert result.completion == "not_established"
    cancelled = item.model_copy(update={"occurrence_state": "cancelled"})
    assert qualify_pattern((cancelled,), coverage=(), timezone="UTC").basis == "insufficient"


def test_series_original_instant_identifies_moved_exceptions_and_all_day_dates() -> None:
    original = datetime(2026, 9, 20, 9, tzinfo=UTC)
    item = event(date(2026, 9, 20), original_start=original, series_id="s")
    moved = item.model_copy(
        update={
            "object_id": "different-provider-instance-id",
            "occurred_at": original + timedelta(days=1),
        }
    )
    assert observation_key(item) == observation_key(moved)
    one = event(
        date(2026, 9, 20),
        occurred_at=None,
        original_date=date(2026, 9, 20),
        planned_date=date(2026, 9, 20),
        series_id="s",
        object_id="same-uid",
    )
    two = event(
        date(2026, 10, 20),
        occurred_at=None,
        original_date=date(2026, 10, 20),
        planned_date=date(2026, 10, 20),
        series_id="s",
        object_id="same-uid",
    )
    assert observation_key(one) != observation_key(two)
