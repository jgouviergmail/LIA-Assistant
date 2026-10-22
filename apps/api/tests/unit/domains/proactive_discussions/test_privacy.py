"""ADR-357: what makes a discussion context SMS-informed."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.proactive_discussions.context_store.preparation import proof_of
from src.domains.proactive_discussions.context_store.schemas import ContextItem
from src.domains.proactive_discussions.privacy import sms_in_context
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _fact(source: SourceKey, *, required: tuple[SourceKey, ...] = ()) -> DiscussionEvidence:
    return DiscussionEvidence(
        reference=f"{source.value}:fiction",
        source=source,
        object_id="fiction",
        version="v1",
        observed_at=NOW,
        excerpt="A fictional item",
        required_sources=required,
    )


def _derived_from(fact: DiscussionEvidence) -> ContextItem:
    return ContextItem(
        id=uuid4(),
        kind="observation",
        summary="A fictional observation",
        qualification="reported",
        revision=1,
        generation=1,
        proofs=(proof_of(fact, {}, now=NOW),),
    )


@pytest.mark.parametrize(
    ("facts", "knowledge", "expected"),
    [
        ((_fact(SourceKey.CALENDAR),), (), False),
        ((_fact(SourceKey.CALENDAR), _fact(SourceKey.SMS)), (), True),
        ((_fact(SourceKey.MEMORIES, required=(SourceKey.SMS,)),), (), True),
        ((), (_derived_from(_fact(SourceKey.SMS)),), True),
        ((), (_derived_from(_fact(SourceKey.CALENDAR)),), False),
    ],
    ids=["no-sms", "sms-fact", "fact-depending-on-sms", "sms-derived-item", "plain-item"],
)
def test_any_sms_read_or_derived_makes_the_context_private(
    facts: tuple[DiscussionEvidence, ...], knowledge: tuple[ContextItem, ...], expected: bool
) -> None:
    assert sms_in_context(facts, knowledge) is expected
