"""A known fact is read again by the read that can return it, for every source."""

import pytest

from src.domains.shared.discussion_catalogue import SOURCE_REGISTRY, reread_operation
from src.domains.shared.discussion_sources import SourceKey

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("source", "planned", "around_instant", "expected"),
    [
        # A native detail read returns a recurring series' master, never the occurrence.
        (SourceKey.CALENDAR, True, False, "history"),
        (SourceKey.CALENDAR, False, True, "history"),
        (SourceKey.TASKS, True, False, "detail"),
        (SourceKey.REMINDERS, True, True, "detail"),
        # A forecast is in no recent page.
        (SourceKey.WEATHER, True, False, "future"),
        (SourceKey.WEATHER, True, True, "future"),
        (SourceKey.WEATHER, False, False, "recent"),
        (SourceKey.WEATHER, False, True, "recent"),
        (SourceKey.HEALTH, False, True, "history"),
        (SourceKey.HEALTH, False, False, "recent"),
        (SourceKey.PORTRAIT, False, True, "recent"),
    ],
)
def test_the_read_that_finds_a_fact_again(source, planned, around_instant, expected):
    assert reread_operation(source, planned=planned, around_instant=around_instant) == expected


@pytest.mark.parametrize("source", list(SourceKey))
@pytest.mark.parametrize("planned", [True, False])
@pytest.mark.parametrize("around_instant", [True, False])
def test_every_source_answers_with_an_operation_it_declares(source, planned, around_instant):
    operation = reread_operation(source, planned=planned, around_instant=around_instant)
    assert operation in SOURCE_REGISTRY[source].operations
