"""People to get back to: starred, quiet past the CRM's own line, the longest silence first."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.readers.relations import (
    QUIET_AFTER_DAYS,
    quiet_relations,
    relation_drafts,
)
from src.domains.relations.schemas import IdentityConfidence, RelationSummary

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)


def person(name: str, *, days_ago: int | None, favorite: bool = True) -> RelationSummary:
    return RelationSummary(
        display_name=name,
        identity_confidence=IdentityConfidence.EXACT,
        open_loops_count=0,
        calls_count=0,
        last_interaction_at=None if days_ago is None else NOW - timedelta(days=days_ago),
        is_favorite=favorite,
    )


def test_only_starred_people_past_the_line_the_longest_silence_first() -> None:
    quiet = quiet_relations(
        [
            person("Recent", days_ago=10),
            person("Quiet", days_ago=QUIET_AFTER_DAYS + 5),
            person("Very quiet", days_ago=QUIET_AFTER_DAYS + 60),
            person("Not starred", days_ago=400, favorite=False),
            person("Never", days_ago=None),
        ],
        now=NOW,
    )
    assert [relation.name for relation in quiet] == ["Very quiet", "Quiet"]


def test_a_quiet_person_may_come_back_a_month_later_not_tomorrow() -> None:
    [today] = relation_drafts(quiet_relations([person("Sam", days_ago=100)], now=NOW), now=NOW)
    [tomorrow] = relation_drafts(quiet_relations([person("Sam", days_ago=101)], now=NOW), now=NOW)
    [next_month] = relation_drafts(quiet_relations([person("Sam", days_ago=130)], now=NOW), now=NOW)
    assert today.key == tomorrow.key != next_month.key
    assert today.text == "No exchange with Sam, someone the listener starred, for 100 days"
    assert (today.kind, today.sensitivity) == (FactKind.RELATION, Sensitivity.PERSONAL)
