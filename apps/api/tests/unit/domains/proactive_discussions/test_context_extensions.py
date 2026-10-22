"""Native dependencies and recurring-task evidence remain explicit."""

from datetime import UTC, datetime

import pytest

from src.domains.connectors.discussion_projections import task_evidence
from src.domains.proactive_discussions.policy import effective_sources
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey

pytestmark = pytest.mark.unit


def test_weather_requires_an_independent_location_opt_in():
    assert SourceKey.WEATHER not in effective_sources(
        DiscussionPolicy(enabled=True, sources=(SourceKey.WEATHER,)), frozenset(SourceKey)
    )


def test_native_task_recurrence_is_preserved_as_a_declaration_not_completion():
    item = task_evidence(
        {
            "id": "fiction",
            "title": "Fictional monthly task",
            "recurrence_pattern": {
                "pattern": {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": 15},
                "range": {"type": "noEnd", "startDate": "2026-01-15"},
            },
        },
        account="fiction",
        now=datetime(2026, 10, 20, tzinfo=UTC),
        chars=4000,
    )
    assert (
        item.native_recurrence is not None
        and item.native_recurrence.pattern.type == "absoluteMonthly"
    )
    assert item.assertion == "planned" and item.occurrence_state == "scheduled"


def test_research_can_return_an_offered_opaque_cursor():
    request = ResearchRequest(
        source=SourceKey.EMAILS, operation="recent", cursor="opaque-next-page"
    )
    assert request.cursor == "opaque-next-page"
