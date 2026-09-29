"""Bounded plans preserve local dates, limits, permissions and normal validation."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from tests.unit.domains.agents.services.test_jev_consultation import intelligence

pytestmark = pytest.mark.unit


def candidates(query, domain="event", **changes):
    from src.domains.agents.services.planner.jev_bounded_consultation import bounded_paths

    qi = replace(
        intelligence(),
        english_query=query,
        original_query=query,
        primary_domain=domain,
        domains=[domain],
        **changes,
    )
    return bounded_paths(qi, "Europe/Paris", datetime(2026, 3, 28, 23, 30, tzinfo=UTC))


def test_day_bounds_follow_local_midnights_across_spring_dst():
    paths = candidates("Show my appointments today", has_temporal_reference=True)
    params = dict(paths["event_today"].parameters)
    assert params["time_min"] == "2026-03-29T00:00:00+01:00"
    assert params["time_max"] == "2026-03-30T00:00:00+02:00"
    assert "days_ahead" not in params
    assert paths["event_today"].description


def test_autumn_dst_and_local_year_rollover_are_calendar_arithmetic():
    from src.domains.agents.services.planner.jev_bounded_consultation import bounded_paths

    qi = replace(intelligence(), primary_domain="event", domains=["event"])
    autumn = bounded_paths(qi, "Europe/Paris", datetime(2026, 10, 25, 12, tzinfo=UTC))
    assert dict(autumn["event_today"].parameters)["time_min"].endswith("+02:00")
    assert dict(autumn["event_today"].parameters)["time_max"].endswith("+01:00")
    year = bounded_paths(qi, "Pacific/Kiritimati", datetime(2026, 12, 31, 20, tzinfo=UTC))
    assert dict(year["event_tomorrow"].parameters)["time_min"].startswith("2027-01-02")


@pytest.mark.parametrize("timezone", ["Invalid/Timezone", "", "../Europe/Paris"])
def test_invalid_timezone_does_not_guess_a_date(timezone):
    from src.domains.agents.services.planner.jev_bounded_consultation import bounded_paths

    qi = replace(intelligence(), primary_domain="event", domains=["event"])
    assert bounded_paths(qi, timezone, datetime.now(UTC)) == {}


def test_explicit_count_keeps_unread_filter_and_code_owned_integer():
    paths = candidates("Show 5 unread emails", "email")
    assert dict(paths["email_unread"].parameters) == {"query": "is:unread", "max_results": 5}
    assert "5" in paths["email_unread"].description


@pytest.mark.parametrize(
    "query",
    [
        "Show -5 unread emails",
        "Show 2.5 unread emails",
        "Show 5 or 10 emails",
        "Show 0 emails",
        "Show 100000 emails",
        "Emails from 2026",
        "Show five emails",
    ],
)
def test_ambiguous_or_unsupported_quantities_do_not_make_candidates(query):
    assert candidates(query, "email") == {}


def test_domain_cap_is_not_silently_clamped():
    with patch("src.domains.agents.services.planner.jev_bounded_consultation.settings") as settings:
        settings.emails_tool_default_max_results = 3
        assert candidates("Show 5 emails", "email") == {}


def test_no_unsupported_reminder_count_or_task_deadline_parameters():
    assert candidates("List 5 reminders", "reminder") == {}
    assert candidates("List 5 tasks due tomorrow", "task", has_temporal_reference=True) == {}


def test_generated_candidates_validate_against_real_tool_schemas():
    import importlib

    for domain, query, module in [
        ("event", "Show 5 appointments tomorrow", "calendar_tools"),
        ("email", "Show 5 emails", "emails_tools"),
        ("task", "List 5 tasks", "tasks_tools"),
        ("file", "List 5 files", "drive_tools"),
        ("contact", "List 5 contacts", "google_contacts_tools"),
    ]:
        paths = candidates(query, domain)
        assert paths
        for candidate in paths.values():
            schema = getattr(
                importlib.import_module("src.domains.agents.tools." + module), candidate.tool
            ).tool_call_schema
            parameters = dict(candidate.parameters)
            assert set(parameters) <= set(schema.model_fields)
            schema.model_validate(parameters)


async def test_count_uses_separate_switch_and_keeps_the_complete_request():
    from src.domains.agents.services.planner import jev_consultation as module
    from src.domains.llm_config.jev_registry import JevUsage
    from tests.unit.domains.agents.services.test_jev_consultation import attempt, invoke

    qi = replace(intelligence(), english_query="Show 5 unread emails")
    result, native = await invoke(module, qi, attempt("email_unread"))
    assert result and result.plan
    assert result.plan.steps[0].parameters == {"query": "is:unread", "max_results": 5}
    assert native.await_count == 1
    assert native.call_args.kwargs["usage"] == JevUsage.CONSULTATION_BOUNDED
    assert native.call_args.kwargs["state"]["intelligence"]["original_query"] == qi.original_query
    assert not result.plan.metadata.get("skip_semantic_validation")


@pytest.mark.parametrize("outcome", ["disabled", "timeout", "quota_exceeded", "invalid_response"])
async def test_bounded_failure_never_makes_a_second_native_attempt(outcome):
    from src.domains.agents.services.planner import jev_consultation as module
    from src.infrastructure.llm.decision_types import DecisionAttempt
    from tests.unit.domains.agents.services.test_jev_consultation import invoke

    result, native = await invoke(
        module,
        replace(intelligence(), english_query="Show 5 emails"),
        DecisionAttempt(outcome=outcome),
    )
    assert result is None
    assert native.await_count == 1


async def test_bounded_path_cannot_reintroduce_a_forbidden_tool():
    from src.domains.agents.services.planner import jev_consultation as module
    from tests.unit.domains.agents.services.test_jev_consultation import attempt, invoke

    result, native = await invoke(
        module,
        replace(intelligence(), english_query="Show 5 emails"),
        attempt("email_recent"),
        allowed=False,
    )
    assert result is None
    native.assert_not_awaited()
