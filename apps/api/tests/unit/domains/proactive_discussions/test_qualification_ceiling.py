"""An interpreted summary cannot upgrade the authority of its evidence."""

from datetime import UTC, datetime

import pytest

from src.domains.proactive_discussions.context_store.schemas import ContextProposal
from src.domains.proactive_discussions.contextualization.proposals import validate_pattern_proposal
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "assertion,qualification",
    [
        ("planned", "observed"),
        ("planned", "reported"),
        ("inferred", "observed"),
        ("inferred", "reported"),
        ("unknown", "declared"),
    ],
)
def test_summary_never_upgrades_plan_or_interpretation_to_testimony(assertion, qualification):
    fact = DiscussionEvidence(
        reference="calendar:a",
        source=SourceKey.CALENDAR,
        object_id="a",
        version="1",
        observed_at=datetime.now(UTC),
        excerpt="Fictional planned appointment",
        assertion=assertion,
    )
    proposal = ContextProposal(
        kind="episode",
        summary="An appointment",
        qualification=qualification,
        anchor=fact.reference,
        references=(fact.reference,),
    )
    with pytest.raises(ValueError):
        validate_pattern_proposal(proposal, (fact,), timezone="UTC")


def test_native_cancelled_plan_can_support_a_positive_contradiction():
    fact = DiscussionEvidence(
        reference="calendar:a",
        source=SourceKey.CALENDAR,
        object_id="a",
        version="1",
        observed_at=datetime.now(UTC),
        excerpt="Cancelled appointment",
        assertion="planned",
        occurrence_state="cancelled",
    )
    proposal = ContextProposal(
        kind="observation",
        summary="The planned appointment was cancelled",
        qualification="contradicted",
        anchor=fact.reference,
        references=(fact.reference,),
    )
    validate_pattern_proposal(proposal, (fact,), timezone="UTC")
