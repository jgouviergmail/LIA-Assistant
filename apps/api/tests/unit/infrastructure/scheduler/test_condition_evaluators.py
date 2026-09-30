"""Condition evaluators (ADR-322) — facts with a stable identity, read on the record.

What must hold:

- the registry covers EXACTLY the domain's ``CONDITION_TYPES`` (ADR-085), and
  every type reads a section the ``routine_condition`` surface declares;
- each evaluator returns FACTS keyed by what they ARE, never by how they are
  displayed: a task keeps its key when its « days until due » moves, an event
  when « 09:00 tomorrow » becomes « 09:00 », a document when it is edited
  again, a forecast when its hour shifts within the same day;
- a calendar condition honours the window it publishes (``within_hours``)
  and announces what is coming up, never what already started;
- ``evaluate_condition`` never raises, opens the accounting and the
  consultation register around the read, files a consultation only for a
  source it actually OPENED, and names why a source could not be read.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.briefing.exceptions import ConnectorAccessError, ConnectorNotConfiguredError
from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    DocumentItem,
    DocumentsData,
    ForecastAlert,
    ForecastAlertKind,
    MailItem,
    MailsData,
    TaskItem,
    TasksData,
)
from src.domains.scheduled_actions.models import CONDITION_TYPES
from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES
from src.infrastructure.scheduler.condition_evaluators import (
    CONDITION_EVALUATORS,
    CONDITION_SECTIONS,
    CONSULTATION_SURFACE,
    ConditionVerdict,
    evaluate_condition,
)

pytestmark = pytest.mark.unit

_MODULE = "src.infrastructure.scheduler.condition_evaluators"
_FETCHERS = "src.domains.briefing.fetchers"
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), language="fr", timezone="Europe/Paris")


def _task(
    title: str, *, overdue: bool, task_id: str | None, days: int = -1, due: str | None = None
) -> TaskItem:
    return TaskItem(title=title, due_date_iso=due, days_until_due=days, overdue=overdue, id=task_id)


def _mail(
    subject: str, *, mail_id: str | None, sender: str = "Alice Martin", shown: str = "09:12"
) -> MailItem:
    return MailItem(
        sender_name=sender,
        sender_email="alice@example.com",
        subject=subject,
        received_local=shown,
        id=mail_id,
    )


def _event(
    title: str, start_at: datetime | None, *, event_id: str, shown: str = "14:00"
) -> AgendaEventItem:
    return AgendaEventItem(
        title=title,
        start_local=shown,
        end_local=None,
        location=None,
        id=event_id,
        start_at=start_at,
    )


@asynccontextmanager
async def _nothing(*_args: Any, **_kwargs: Any) -> AsyncIterator[list[Any]]:
    yield []


async def _evaluate(config: dict[str, Any], **patches: Any) -> tuple[ConditionVerdict, MagicMock]:
    """Run the REAL wrapper with the register and the accounting observed."""
    recorder = MagicMock()
    with (
        patch(f"{_MODULE}.record_surface_consultations", recorder),
        patch(f"{_MODULE}.out_of_turn_spend", MagicMock(side_effect=lambda *a, **k: _nothing())),
        patch(f"{_MODULE}.now_utc", return_value=NOW),
    ):
        for target, value in patches.items():
            patch(f"{_FETCHERS}.{target}", value).start()
        try:
            verdict = await evaluate_condition(
                _user(), config, run_id="routine_condition_test", session_id="scheduled_action_x"
            )
        finally:
            patch.stopall()
    return verdict, recorder


class TestTheRegistries:
    def test_every_condition_type_has_an_evaluator(self) -> None:
        # Both directions: a missing evaluator AND a stray one fail (ADR-085).
        assert set(CONDITION_EVALUATORS) == set(CONDITION_TYPES)

    def test_every_condition_type_reads_a_declared_section(self) -> None:
        declared = CONSULTATION_SURFACES[CONSULTATION_SURFACE].domains
        assert set(CONDITION_SECTIONS) == set(CONDITION_TYPES)
        assert set(CONDITION_SECTIONS.values()) <= set(declared)

    def test_the_surface_files_the_persons_own_standing_instruction(self) -> None:
        # Nobody schedules a check: the person asked LIA to watch, and every
        # read happens because of that instruction — what ``scheduled`` names.
        assert CONSULTATION_SURFACES[CONSULTATION_SURFACE].source == "scheduled"


class TestTasks:
    async def test_each_overdue_task_is_a_fact_of_its_own(self) -> None:
        data = TasksData(
            items=[
                _task("Facture", overdue=True, task_id="t1"),
                _task("Facture", overdue=True, task_id="t2"),
                _task("Courses", overdue=False, task_id="t3"),
            ],
            overdue_count=2,
        )
        fetch = AsyncMock(return_value=data)
        verdict, _ = await _evaluate({"type": "task_overdue"}, fetch_tasks=fetch)

        assert len(verdict.keys) == 2
        assert verdict.note_for(verdict.keys) == "Overdue tasks: Facture, Facture"
        # The newest overdue task is the one the card's oldest-first cut drops.
        assert fetch.await_args.kwargs["whole_page"] is True

    async def test_a_task_keeps_its_key_as_its_due_date_recedes(self) -> None:
        first = TasksData(
            items=[_task("Facture", overdue=True, task_id="t1", days=-1, due="2026-09-24")],
            overdue_count=1,
        )
        later = TasksData(
            items=[_task("Facture", overdue=True, task_id="t1", days=-2, due="2026-09-24")],
            overdue_count=1,
        )
        one, _ = await _evaluate(
            {"type": "task_overdue"}, fetch_tasks=AsyncMock(return_value=first)
        )
        two, _ = await _evaluate(
            {"type": "task_overdue"}, fetch_tasks=AsyncMock(return_value=later)
        )

        assert one.keys == two.keys

    async def test_a_task_overdue_again_after_a_new_due_date_is_a_new_fact(self) -> None:
        # Pushed back once, overdue again: the person has not been told about
        # THIS lateness, and the task id alone would have kept them silent.
        first = TasksData(
            items=[_task("Facture", overdue=True, task_id="t1", due="2026-09-20")],
            overdue_count=1,
        )
        again = TasksData(
            items=[_task("Facture", overdue=True, task_id="t1", due="2026-09-24")],
            overdue_count=1,
        )
        one, _ = await _evaluate(
            {"type": "task_overdue"}, fetch_tasks=AsyncMock(return_value=first)
        )
        two, _ = await _evaluate(
            {"type": "task_overdue"}, fetch_tasks=AsyncMock(return_value=again)
        )

        assert one.keys != two.keys

    async def test_no_overdue_task_is_no_fact(self) -> None:
        data = TasksData(items=[_task("Courses", overdue=False, task_id="t3")], overdue_count=0)
        verdict, _ = await _evaluate(
            {"type": "task_overdue"}, fetch_tasks=AsyncMock(return_value=data)
        )

        assert verdict.met is False
        assert verdict.error is None


class TestWeather:
    @staticmethod
    def _alert(
        kind: ForecastAlertKind, starts_at: datetime, shown: str, percent: int | None = 80
    ) -> ForecastAlert:
        return ForecastAlert(
            kind=kind, time=shown, starts_at=starts_at, precipitation_percent=percent
        )

    async def test_the_rule_read_is_the_published_one(self) -> None:
        # Horizon, strict threshold and kinds come from the settings and the
        # routine — never a figure typed in the evaluator (ADR-184).
        fetch = AsyncMock(return_value=None)
        await _evaluate(
            {"type": "weather_change", "kinds": ["snow", "rain"]}, fetch_forecast_alert=fetch
        )

        kwargs = fetch.await_args.kwargs
        rule = kwargs["rule"]
        assert rule.horizon == timedelta(hours=settings.scheduled_actions_weather_horizon_hours)
        assert (
            rule.min_precipitation_percent
            == settings.scheduled_actions_weather_min_precipitation_percent
        )
        assert rule.kinds == {ForecastAlertKind.SNOW, ForecastAlertKind.RAIN}
        assert kwargs["now"] == NOW

    async def test_no_kinds_stored_watches_every_kind(self) -> None:
        fetch = AsyncMock(return_value=None)
        await _evaluate({"type": "weather_change"}, fetch_forecast_alert=fetch)

        assert fetch.await_args.kwargs["rule"].kinds == frozenset(ForecastAlertKind)

    async def test_a_selection_of_a_shape_no_writer_produces_watches_every_kind(self) -> None:
        # Read forgivingly: « "rain" » must not become the letters r, a, i, n.
        fetch = AsyncMock(return_value=None)
        await _evaluate({"type": "weather_change", "kinds": "rain"}, fetch_forecast_alert=fetch)

        assert fetch.await_args.kwargs["rule"].kinds == frozenset(ForecastAlertKind)

    async def test_only_unknown_kinds_stored_is_never_met(self) -> None:
        # A config written by another release: nothing it names can be watched,
        # and an empty selection is not « every kind ».
        rain = self._alert(ForecastAlertKind.RAIN, NOW + timedelta(hours=1), "13:00")
        fetch = AsyncMock(return_value=rain)
        verdict, _ = await _evaluate(
            {"type": "weather_change", "kinds": ["hail"]}, fetch_forecast_alert=fetch
        )

        assert fetch.await_args.kwargs["rule"].kinds == frozenset()
        assert verdict.met is False
        assert verdict.error is None

    async def test_the_note_states_the_day_the_hour_the_chance_and_the_source(self) -> None:
        # « rain expected around 20:00 » alone let the run check TODAY at 20:00
        # and answer that nothing was changing.
        rain = self._alert(ForecastAlertKind.RAIN, NOW + timedelta(hours=2), "14:00")
        met, _ = await _evaluate(
            {"type": "weather_change", "kinds": ["rain"]},
            fetch_forecast_alert=AsyncMock(return_value=rain),
        )

        assert met.note_for(met.keys) == (
            "Weather alert: rain expected around 14:00 on 2026-09-25 (Europe/Paris), "
            "80% chance of precipitation (source: Google Weather)"
        )

    async def test_a_change_with_no_stated_chance_says_none(self) -> None:
        rain = self._alert(ForecastAlertKind.RAIN, NOW + timedelta(hours=2), "14:00", None)
        met, _ = await _evaluate(
            {"type": "weather_change"}, fetch_forecast_alert=AsyncMock(return_value=rain)
        )

        assert met.note_for(met.keys) == (
            "Weather alert: rain expected around 14:00 on 2026-09-25 (Europe/Paris) "
            "(source: Google Weather)"
        )

    async def test_the_day_is_the_persons_local_day(self) -> None:
        # 23:30 UTC is already the next day in Paris.
        late = self._alert(
            ForecastAlertKind.SNOW, datetime(2026, 9, 25, 23, 30, tzinfo=UTC), "01:30"
        )
        met, _ = await _evaluate(
            {"type": "weather_change"}, fetch_forecast_alert=AsyncMock(return_value=late)
        )

        assert "on 2026-09-26 (Europe/Paris)" in (met.note_for(met.keys) or "")

    async def test_a_forecast_moving_within_the_day_is_the_same_fact(self) -> None:
        at_three = self._alert(
            ForecastAlertKind.RAIN, datetime(2026, 9, 25, 13, 0, tzinfo=UTC), "15:00"
        )
        at_six = self._alert(
            ForecastAlertKind.RAIN, datetime(2026, 9, 25, 16, 0, tzinfo=UTC), "18:00", 60
        )
        one, _ = await _evaluate(
            {"type": "weather_change"}, fetch_forecast_alert=AsyncMock(return_value=at_three)
        )
        two, _ = await _evaluate(
            {"type": "weather_change"}, fetch_forecast_alert=AsyncMock(return_value=at_six)
        )

        assert one.keys == two.keys

    async def test_tomorrows_rain_at_the_same_hour_is_a_new_fact(self) -> None:
        # The old fingerprint read 'HH:MM' only: tomorrow's rain was deduped.
        today = self._alert(
            ForecastAlertKind.RAIN, datetime(2026, 9, 25, 13, 0, tzinfo=UTC), "15:00"
        )
        tomorrow = self._alert(
            ForecastAlertKind.RAIN, datetime(2026, 9, 26, 13, 0, tzinfo=UTC), "15:00"
        )
        one, _ = await _evaluate(
            {"type": "weather_change"}, fetch_forecast_alert=AsyncMock(return_value=today)
        )
        two, _ = await _evaluate(
            {"type": "weather_change"}, fetch_forecast_alert=AsyncMock(return_value=tomorrow)
        )

        assert one.keys != two.keys

    async def test_the_lean_forecast_read_is_the_one_used(self) -> None:
        # The card's full read would bill a city name, air quality and pollen
        # on every check — none of which a condition reads.
        full = AsyncMock()
        await _evaluate(
            {"type": "weather_change"},
            fetch_forecast_alert=AsyncMock(return_value=None),
            fetch_weather=full,
        )

        full.assert_not_awaited()


class TestMail:
    async def test_subject_and_sender_match_case_insensitively(self) -> None:
        mails = MailsData(items=[_mail("FACTURE mars", mail_id="m1")], total_unread_today=1)
        fetch = AsyncMock(return_value=mails)
        by_subject, _ = await _evaluate(
            {"type": "mail_match", "query": "facture"}, fetch_mails=fetch
        )
        by_sender, _ = await _evaluate({"type": "mail_match", "query": "alice"}, fetch_mails=fetch)
        miss, _ = await _evaluate({"type": "mail_match", "query": "licorne"}, fetch_mails=fetch)

        assert by_subject.met and by_sender.met
        assert miss.met is False

    async def test_two_mails_with_one_subject_are_two_facts(self) -> None:
        mails = MailsData(
            items=[_mail("Re: devis", mail_id="m1"), _mail("Re: devis", mail_id="m2")],
            total_unread_today=2,
        )
        verdict, _ = await _evaluate(
            {"type": "mail_match", "query": "devis"}, fetch_mails=AsyncMock(return_value=mails)
        )

        assert len(verdict.keys) == 2

    async def test_a_mail_with_no_id_is_never_keyed_on_its_display_time(self) -> None:
        # « 09:12 » becomes « yesterday 09:12 »: the same unread mail must not
        # read as new the next day.
        today = MailsData(items=[_mail("Devis", mail_id=None)], total_unread_today=1)
        tomorrow = MailsData(
            items=[_mail("Devis", mail_id=None, shown="hier 09:12")], total_unread_today=1
        )
        one, _ = await _evaluate(
            {"type": "mail_match", "query": "devis"}, fetch_mails=AsyncMock(return_value=today)
        )
        two, _ = await _evaluate(
            {"type": "mail_match", "query": "devis"}, fetch_mails=AsyncMock(return_value=tomorrow)
        )

        assert one.keys == two.keys


class TestDocuments:
    async def test_editing_a_document_again_is_not_a_new_fact(self) -> None:
        first = DocumentsData(items=[DocumentItem(name="Budget", modified_local="10:02", id="d1")])
        edited = DocumentsData(items=[DocumentItem(name="Budget", modified_local="10:12", id="d1")])
        one, _ = await _evaluate(
            {"type": "document_added"}, fetch_documents=AsyncMock(return_value=first)
        )
        two, _ = await _evaluate(
            {"type": "document_added"}, fetch_documents=AsyncMock(return_value=edited)
        )

        assert one.keys == two.keys
        assert one.note_for(one.keys) == "Recent documents: Budget"


class TestCalendar:
    async def test_the_published_window_is_the_window_read(self) -> None:
        fetch = AsyncMock(return_value=AgendaData(events=[]))
        await _evaluate({"type": "calendar_event", "within_hours": 6}, fetch_agenda=fetch)
        await _evaluate({"type": "calendar_event"}, fetch_agenda=fetch)

        windows = [call.kwargs["lookahead_hours"] for call in fetch.await_args_list]
        assert windows == [6, 4]

    async def test_an_event_that_already_started_is_not_coming_up(self) -> None:
        agenda = AgendaData(
            events=[
                _event("Standup", NOW - timedelta(minutes=10), event_id="e1"),
                _event("Comité", NOW + timedelta(hours=2), event_id="e2"),
            ]
        )
        verdict, _ = await _evaluate(
            {"type": "calendar_event"}, fetch_agenda=AsyncMock(return_value=agenda)
        )

        assert verdict.note_for(verdict.keys) == "Upcoming events: Comité (14:00)"

    async def test_the_title_filter_is_optional(self) -> None:
        agenda = AgendaData(
            events=[_event("Comité produit", NOW + timedelta(hours=1), event_id="e1")]
        )
        fetch = AsyncMock(return_value=agenda)
        any_event, _ = await _evaluate({"type": "calendar_event"}, fetch_agenda=fetch)
        matching, _ = await _evaluate(
            {"type": "calendar_event", "query": "comité"}, fetch_agenda=fetch
        )
        miss, _ = await _evaluate(
            {"type": "calendar_event", "query": "dentiste"}, fetch_agenda=fetch
        )

        assert any_event.met and matching.met
        assert miss.met is False

    async def test_midnight_rewording_the_start_does_not_make_it_new(self) -> None:
        start = NOW + timedelta(hours=3)
        before = AgendaData(events=[_event("Vol", start, event_id="e1", shown="09:00 demain")])
        after = AgendaData(events=[_event("Vol", start, event_id="e1", shown="09:00")])
        one, _ = await _evaluate(
            {"type": "calendar_event"}, fetch_agenda=AsyncMock(return_value=before)
        )
        two, _ = await _evaluate(
            {"type": "calendar_event"}, fetch_agenda=AsyncMock(return_value=after)
        )

        assert one.keys == two.keys

    async def test_an_event_with_no_readable_start_is_never_keyed_on_its_display(self) -> None:
        before = AgendaData(events=[_event("Vol", None, event_id="e1", shown="09:00 demain")])
        after = AgendaData(events=[_event("Vol", None, event_id="e1", shown="09:00")])
        one, _ = await _evaluate(
            {"type": "calendar_event"}, fetch_agenda=AsyncMock(return_value=before)
        )
        two, _ = await _evaluate(
            {"type": "calendar_event"}, fetch_agenda=AsyncMock(return_value=after)
        )

        assert one.keys == two.keys


class TestTheRecord:
    """Accounted, recorded, and never a crash."""

    async def test_an_opened_source_is_one_consultation_under_the_routine_surface(self) -> None:
        data = TasksData(items=[], overdue_count=0)
        _, recorder = await _evaluate(
            {"type": "task_overdue"}, fetch_tasks=AsyncMock(return_value=data)
        )

        recorder.assert_called_once()
        kwargs = recorder.call_args.kwargs
        assert kwargs["surface"] == CONSULTATION_SURFACE
        assert list(kwargs["opened"]) == ["tasks"]
        assert list(kwargs["failed"]) == []

    async def test_a_source_that_refused_is_named_as_failed(self) -> None:
        refusal = AsyncMock(side_effect=ConnectorAccessError("email", "network", "down"))
        verdict, recorder = await _evaluate(
            {"type": "mail_match", "query": "devis"}, fetch_mails=refusal
        )

        assert verdict.error == "unavailable"
        assert verdict.met is False
        assert list(recorder.call_args.kwargs["failed"]) == ["mails"]

    async def test_a_source_nobody_connected_was_never_opened(self) -> None:
        # No connector: nothing was asked, so nothing is filed — and the person
        # is told what to fix rather than « unavailable ».
        missing = AsyncMock(side_effect=ConnectorNotConfiguredError("tasks"))
        verdict, recorder = await _evaluate({"type": "task_overdue"}, fetch_tasks=missing)

        assert verdict.error == "not_configured"
        recorder.assert_not_called()

    async def test_an_unexpected_failure_never_escapes(self) -> None:
        crash = AsyncMock(side_effect=RuntimeError("boom"))
        verdict, _ = await _evaluate({"type": "task_overdue"}, fetch_tasks=crash)

        assert verdict.error == "unavailable"

    async def test_an_unknown_stored_type_reads_nothing(self) -> None:
        verdict, recorder = await _evaluate({"type": "moon_phase"})

        assert verdict.error == "unavailable"
        recorder.assert_not_called()

    async def test_the_read_is_accounted_on_the_routines_own_run(self) -> None:
        spend = MagicMock(side_effect=lambda *a, **k: _nothing())
        with (
            patch(f"{_MODULE}.record_surface_consultations", MagicMock()),
            patch(f"{_MODULE}.out_of_turn_spend", spend),
            patch(
                f"{_FETCHERS}.fetch_tasks",
                AsyncMock(return_value=TasksData(items=[], overdue_count=0)),
            ),
        ):
            user = _user()
            await evaluate_condition(
                user,
                {"type": "task_overdue"},
                run_id="routine_condition_r1",
                session_id="scheduled_action_r",
            )

        spend.assert_called_once_with("routine_condition_r1", user.id, "scheduled_action_r")
