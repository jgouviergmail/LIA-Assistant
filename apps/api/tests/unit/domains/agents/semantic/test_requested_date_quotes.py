"""Quoted dates use the original server request context, never a textual prefix."""

from datetime import date

import msgpack
import pytest

from src.core.date_quotes import date_from_quote
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.analysis.query_intelligence_helpers import reconstruct_query_intelligence
from src.domains.agents.analysis.requested_outcomes import (
    GoalFieldExpectation,
    GoalRequirement,
    anchored_requirements,
)


def _goal(quote: str, expected: str, *, model_timezone: str | None = None) -> GoalRequirement:
    return GoalRequirement(
        domain="event",
        label="Event on quoted day",
        source_quote=quote,
        expected_fields=(
            GoalFieldExpectation(
                field="start_datetime",
                expected_value=expected,
                operator="on_date",
                source_quote=quote,
                reference_date="2099-01-01",
                reference_timezone=model_timezone,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("quote", "timezone", "expected"),
    [
        ("2026-10-08T00:30:00Z", "America/New_York", date(2026, 10, 7)),
        ("2026-10-08T00:30:00+00:00", "Pacific/Honolulu", date(2026, 10, 7)),
        ("2026-10-08T23:30:00-05:00", "Europe/Paris", date(2026, 10, 9)),
        ("2026-10-08t23:30:00z", "Asia/Tokyo", date(2026, 10, 9)),
        ("2026-10-08T00:30:00", "America/New_York", date(2026, 10, 8)),
        ("2026-10-08", "America/New_York", date(2026, 10, 8)),
        ("jeudi 8 octobre 2026", "Pacific/Honolulu", date(2026, 10, 8)),
    ],
)
def test_exact_quote_calendar_day_obeys_request_timezone(
    quote: str,
    timezone: str,
    expected: date,
) -> None:
    assert date_from_quote(quote, reference_timezone=timezone) == expected


@pytest.mark.parametrize(
    "quote",
    [
        "2026-10-08invalid",
        "2026-10-08Tbogus",
        "2026-10-08T25:00:00Z",
        "2026-10-08T00:30:00Zsuffix",
        "2026-02-30",
        "2026-10-08T00:30:00+01:99",
        "8 octobre 2026invalid",
        "8 octobre 2026 et un autre jour",
    ],
)
def test_malformed_or_longer_expression_cannot_be_accepted_by_a_date_prefix(quote: str) -> None:
    assert date_from_quote(quote, reference_timezone="Europe/Paris") is None
    assert (
        anchored_requirements(
            [_goal(quote, "2026-10-08")],
            quote,
            ["event"],
            reference_timezone="Europe/Paris",
        )
        == ()
    )


def test_wrong_timestamp_iso_prefix_is_rejected_and_converted_request_day_is_accepted() -> None:
    quote = "2026-10-08T00:30:00Z"
    assert (
        anchored_requirements(
            [_goal(quote, "2026-10-08")],
            quote,
            ["event"],
            reference_timezone="America/New_York",
        )
        == ()
    )
    accepted = anchored_requirements(
        [_goal(quote, "2026-10-07")],
        quote,
        ["event"],
        reference_timezone="America/New_York",
    )
    assert accepted[0].expected_fields[0].reference_timezone == "America/New_York"


def test_model_authored_timezone_is_replaced_or_cleared_before_validation() -> None:
    quote = "2026-10-08T00:30:00Z"
    forged = _goal(quote, "2026-10-07", model_timezone="Pacific/Honolulu")
    assert anchored_requirements([forged], quote, ["event"]) == ()
    assert (
        anchored_requirements(
            [forged],
            quote,
            ["event"],
            reference_timezone="Europe/Paris",
        )
        == ()
    )
    civil = _goal("2026-10-08", "2026-10-08", model_timezone="Pacific/Honolulu")
    accepted = anchored_requirements([civil], "2026-10-08", ["event"])
    assert accepted[0].expected_fields[0].reference_timezone is None
    assert accepted[0].expected_fields[0].reference_date is None


@pytest.mark.parametrize("timezone", [None, "Unknown/Zone", ""])
def test_timestamp_without_a_valid_server_timezone_has_no_calendar_day(
    timezone: str | None,
) -> None:
    assert date_from_quote("2026-10-08T00:30:00Z", reference_timezone=timezone) is None


def test_relative_day_and_timezone_survive_real_checkpoint_and_changed_resume_context() -> None:
    goals = anchored_requirements(
        [_goal("demain", "2026-10-07", model_timezone="Asia/Tokyo")],
        "demain",
        ["event"],
        reference_date=date(2026, 10, 6),
        reference_timezone="America/New_York",
    )
    original = QueryIntelligence(
        original_query="demain",
        english_query="tomorrow",
        immediate_intent="search",
        immediate_confidence=1,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="Quoted day",
        domains=["event"],
        requested_outcomes=goals,
    )
    checkpoint = msgpack.unpackb(msgpack.packb(original.to_serializable_dict()), raw=False)
    restored = reconstruct_query_intelligence(checkpoint)
    resumed = anchored_requirements(
        restored.requested_outcomes,
        "demain",
        ["event"],
        reference_date=date(2026, 10, 8),
        reference_timezone="Asia/Tokyo",
        trusted_checkpoint=True,
    )
    assert resumed == goals
    expectation = resumed[0].expected_fields[0]
    assert expectation.reference_date == "2026-10-06"
    assert expectation.reference_timezone == "America/New_York"
    assert expectation.expected_value == "2026-10-07"


def test_literal_entity_value_case_cannot_be_forged_by_lowercasing_the_model_query() -> None:
    goal = GoalRequirement(
        domain="contact",
        label="Quoted recipient",
        source_quote="Ada",
        expected_fields=(
            GoalFieldExpectation(field="name", expected_value="ada", source_quote="Ada"),
        ),
    )
    assert anchored_requirements([goal], "Ada", ["contact"]) == ()
