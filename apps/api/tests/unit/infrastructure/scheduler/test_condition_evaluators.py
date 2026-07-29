"""Condition evaluators (N-07 phase 1) — registry completeness and verdicts.

What must hold:
- the registry covers EXACTLY the domain's CONDITION_TYPES (ADR-085: a new
  type without an evaluator must refuse to boot — pinned both ways here);
- each evaluator turns its fetcher payload into met/fingerprint/note, and
  the fingerprint identifies the FACT (same facts ⇒ same fingerprint, new
  facts ⇒ new fingerprint) so the executor's ledger can dedup;
- ``evaluate_condition`` NEVER raises: provider failures and unknown stored
  types read as "not met" (retried at the next tick).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    ForecastAlert,
    ForecastAlertKind,
    MailItem,
    MailsData,
    TaskItem,
    TasksData,
)
from src.domains.scheduled_actions.models import CONDITION_TYPES
from src.infrastructure.scheduler.condition_evaluators import (
    CONDITION_EVALUATORS,
    evaluate_condition,
)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), language="fr", timezone="Europe/Paris")


def _task(title: str, *, overdue: bool) -> TaskItem:
    return TaskItem(title=title, due_date_iso=None, days_until_due=None, overdue=overdue)


@pytest.mark.unit
def test_registry_covers_exactly_the_condition_types() -> None:
    # Both directions: a missing evaluator AND a stray one fail (ADR-085).
    assert set(CONDITION_EVALUATORS.keys()) == set(CONDITION_TYPES)


@pytest.mark.unit
async def test_task_overdue_fingerprints_the_overdue_set() -> None:
    data = TasksData(
        items=[_task("Facture", overdue=True), _task("Courses", overdue=False)],
        overdue_count=1,
    )
    with patch("src.domains.briefing.fetchers.fetch_tasks", AsyncMock(return_value=data)):
        first = await evaluate_condition(_user(), {"type": "task_overdue"})
        second = await evaluate_condition(_user(), {"type": "task_overdue"})

    assert first.met is True
    assert "Facture" in (first.note or "")
    # Same facts ⇒ same fingerprint (the executor dedups on it)…
    assert first.fingerprint == second.fingerprint

    # …and a NEW overdue task is a new fact.
    grown = TasksData(
        items=[_task("Facture", overdue=True), _task("Impôts", overdue=True)],
        overdue_count=2,
    )
    with patch("src.domains.briefing.fetchers.fetch_tasks", AsyncMock(return_value=grown)):
        third = await evaluate_condition(_user(), {"type": "task_overdue"})
    assert third.fingerprint != first.fingerprint


@pytest.mark.unit
async def test_task_overdue_not_met_without_overdue_tasks() -> None:
    data = TasksData(items=[_task("Courses", overdue=False)], overdue_count=0)
    with patch("src.domains.briefing.fetchers.fetch_tasks", AsyncMock(return_value=data)):
        verdict = await evaluate_condition(_user(), {"type": "task_overdue"})
    assert verdict.met is False
    assert verdict.fingerprint == ""


@pytest.mark.unit
async def test_weather_change_filters_on_configured_kinds() -> None:
    weather = SimpleNamespace(
        forecast_alert=ForecastAlert(kind=ForecastAlertKind.RAIN, time="18:00")
    )
    with patch("src.domains.briefing.fetchers.fetch_weather", AsyncMock(return_value=weather)):
        met = await evaluate_condition(_user(), {"type": "weather_change", "kinds": ["rain"]})
        filtered = await evaluate_condition(_user(), {"type": "weather_change", "kinds": ["snow"]})

    assert met.met is True
    assert "rain" in (met.note or "")
    assert filtered.met is False


@pytest.mark.unit
async def test_mail_match_matches_subject_and_sender_case_insensitively() -> None:
    mails = MailsData(
        items=[
            MailItem(
                sender_name="Alice Martin",
                sender_email="alice@example.com",
                subject="FACTURE mars",
                received_local="09:12",
            )
        ],
        total_unread_today=1,
    )
    with patch("src.domains.briefing.fetchers.fetch_mails", AsyncMock(return_value=mails)):
        by_subject = await evaluate_condition(_user(), {"type": "mail_match", "query": "facture"})
        by_sender = await evaluate_condition(_user(), {"type": "mail_match", "query": "alice"})
        miss = await evaluate_condition(_user(), {"type": "mail_match", "query": "licorne"})

    assert by_subject.met is True
    assert by_sender.met is True
    assert miss.met is False


@pytest.mark.unit
async def test_calendar_event_optionally_filters_on_title() -> None:
    agenda = AgendaData(
        events=[
            AgendaEventItem(
                title="Comité produit", start_local="14:00", end_local=None, location=None
            )
        ]
    )
    with patch("src.domains.briefing.fetchers.fetch_agenda", AsyncMock(return_value=agenda)):
        any_event = await evaluate_condition(_user(), {"type": "calendar_event"})
        matching = await evaluate_condition(_user(), {"type": "calendar_event", "query": "comité"})
        miss = await evaluate_condition(_user(), {"type": "calendar_event", "query": "dentiste"})

    assert any_event.met is True
    assert matching.met is True
    assert miss.met is False


@pytest.mark.unit
async def test_evaluation_never_raises() -> None:
    # Provider failure → not met (retried next tick), never an exception.
    with patch(
        "src.domains.briefing.fetchers.fetch_tasks",
        AsyncMock(side_effect=ConnectionError("gmail down")),
    ):
        verdict = await evaluate_condition(_user(), {"type": "task_overdue"})
    assert verdict.met is False

    # Unknown stored type (config from another release) → not met, no crash.
    unknown = await evaluate_condition(_user(), {"type": "moon_phase"})
    assert unknown.met is False
