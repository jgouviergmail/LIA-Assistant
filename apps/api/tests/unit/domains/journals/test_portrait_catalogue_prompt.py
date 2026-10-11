"""Only complete authorized sources receive portrait reference IDs in the prompt."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.journals.consolidation_service import _format_all_entries
from src.domains.journals.models import JournalEntry

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "level,confidence,contradictions,eligible",
    [
        ("L1", "high", 0, True),
        ("L2", "medium", 0, True),
        ("L0", "high", 0, False),
        ("L3", "low", 0, False),
        ("L1", "high", 1, False),
    ],
)
def test_journal_reference_is_offered_only_for_operational_unchallenged_content(
    level, confidence, contradictions, eligible
):
    entry = JournalEntry(
        id=uuid4(),
        user_id=uuid4(),
        theme="user_observations",
        title="Scoped preference",
        content="WHEN deleting an email DO ask before moving it to trash BECAUSE explicit request.",
        mood="reflective",
        status="active",
        source="conversation",
        char_count=90,
        created_at=datetime.now(UTC),
        injection_count=0,
        evidence_count=2,
        contradiction_count=contradictions,
        confidence=confidence,
        level=level,
        revision=1,
    )
    rendered = _format_all_entries([entry])
    assert ("portrait_item_id=" in rendered) is eligible
    assert entry.content in rendered  # Maintenance still sees every complete entry.
