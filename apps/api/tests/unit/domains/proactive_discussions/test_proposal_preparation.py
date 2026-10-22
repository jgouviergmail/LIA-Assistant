"""A proposal its evidence cannot carry is refused alone; the publication keeps the others."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from src.domains.proactive_discussions.context_store.preparation import (
    ProposalRefused,
    prepare_item,
    prepare_items,
)
from src.domains.proactive_discussions.context_store.schemas import ContextProposal
from src.domains.shared.discussion_sources import DiscussionEvidence

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)
OWNER = UUID(int=7)


def event(day: date, **changes: object) -> DiscussionEvidence:
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=9)
    return DiscussionEvidence.model_validate(
        {
            "source": "calendar",
            "source_account": "a",
            "object_id": day.isoformat(),
            "reference": f"calendar:{day}",
            "version": "v1",
            "observed_at": NOW,
            "occurred_at": start,
            "excerpt": "A fictional appointment",
            "assertion": "planned",
            **changes,
        }
    )


FIRST, SECOND = event(date(2026, 10, 22)), event(date(2026, 10, 23))
REFERENCES = {FIRST.reference: FIRST, SECOND.reference: SECOND}


def proposal(**changes: object) -> ContextProposal:
    return ContextProposal.model_validate(
        {
            "kind": "observation",
            "summary": "A fictional appointment is planned",
            "qualification": "planned",
            "anchor": FIRST.reference,
            "references": [FIRST.reference],
            **changes,
        }
    )


def prepare(*proposals: ContextProposal, topics: frozenset[str] = frozenset()):
    return prepare_items(
        OWNER,
        proposals,
        REFERENCES,
        allowed_topics=topics,
        generation=1,
        now=NOW,
        timezone="UTC",
    )


def test_each_refusal_is_named_and_the_supported_proposals_are_kept():
    supported = proposal()
    items, refused = prepare(
        supported,
        # A plan is not testimony: its evidence cannot carry "observed".
        proposal(anchor=SECOND.reference, references=[SECOND.reference], qualification="observed"),
        proposal(anchor="calendar:unread", references=["calendar:unread"]),
        proposal(
            anchor=SECOND.reference, references=[SECOND.reference], sensitive_topics=["health"]
        ),
    )
    assert [item.qualification for item in items] == ["planned"]
    assert refused == {
        "unsupported_qualification": 1,
        "inadmissible_reference": 1,
        "refused_topic": 1,
    }


def test_two_proposals_making_one_item_keep_the_first():
    first = proposal(summary="The first reading")
    items, refused = prepare(first, proposal(summary="A second reading of the same anchor"))
    assert [item.summary for item in items] == ["The first reading"]
    assert refused == {"duplicate_item": 1}


def test_a_pattern_over_two_subjects_is_refused_alone():
    one = event(date(2026, 10, 24), subject_id="person:a")
    two = event(date(2026, 10, 25), subject_id="person:b")
    items, refused = prepare_items(
        OWNER,
        (
            ContextProposal(
                kind="pattern",
                summary="A fictional routine shared by two people",
                # An unknown qualification claims nothing, so only the subjects decide.
                qualification="unknown",
                anchor=one.reference,
                references=(one.reference, two.reference),
            ),
            proposal(),
        ),
        {**REFERENCES, one.reference: one, two.reference: two},
        allowed_topics=frozenset(),
        generation=1,
        now=NOW,
        timezone="UTC",
    )
    assert len(items) == 1
    assert refused == {"mixed_subjects": 1}


def test_a_refusal_stays_a_value_error_for_every_caller_that_expects_one():
    with pytest.raises(ValueError) as caught:
        prepare_item(
            OWNER,
            proposal(qualification="observed"),
            REFERENCES,
            generation=1,
            revision=1,
            now=NOW,
            timezone="UTC",
        )
    assert isinstance(caught.value, ProposalRefused)
    assert caught.value.code == "unsupported_qualification"
